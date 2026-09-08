"""
企业关联风险智能洞察系统 —— 确定性 Risk Rule Engine。

核心设计原则：
  - AI Agent 负责「发现风险事实」并绑定 Evidence ID；
  - 本模块负责「确定性评分和等级认定」；
  - 同一 Evidence 不得被同一规则重复计分；
  - 所有评分结果可追溯到具体规则和 Evidence；
  - LLM 不允许直接修改 risk_score 或 risk_level。
  - V2.2: Evidence Provenance — 区分目标企业自身风险与关联企业风险暴露。

流程（V2.2）：
  风险事实（evidence_ids + raw_data + provenance）
  → 按 provenance 分离 own / related
  → 规则匹配（逐条 evidence 逐条 rule）
  → 风险项列表（triggered_rules）
  → 分数计算（去重 + 维度权重）
  → 硬规则检查（force_level override）
  → 风险等级确定
  → 输出结构化认定结果（own_risk + relationship_exposure + comprehensive_risk）
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

logger = logging.getLogger("risk-api")

# ------------------------------------------------------------
# 路径常量
# ------------------------------------------------------------

BACKEND_ROOT = Path(__file__).resolve().parents[1]  # backend/
PROJECT_ROOT = BACKEND_ROOT.parent                  # 项目根目录
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "risk_rules.yaml"
DEFAULT_TRANSMISSION_CONFIG_PATH = PROJECT_ROOT / "config" / "risk_transmission.yaml"


# ------------------------------------------------------------
# 配置加载
# ------------------------------------------------------------

def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """加载 risk_rules.yaml 配置文件。

    参数：
        config_path: 配置文件路径，None 时使用默认路径。

    返回：
        完整配置 dict。

    异常：
        FileNotFoundError: 配置文件不存在。
        yaml.YAMLError: YAML 解析失败。
    """
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Risk Rule Engine 配置文件不存在：{path}")

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 基本校验
    required_keys = ["risk_levels", "dimension_weights", "rules", "hard_rules"]
    for key in required_keys:
        if key not in config:
            raise ValueError(f"配置文件缺少必要字段：{key}")

    return config


# ------------------------------------------------------------
# 条件求值（安全沙箱）
# ------------------------------------------------------------

def _eval_condition(condition: str, context: Dict[str, Any]) -> bool:
    """在安全沙箱中求值条件表达式。

    只允许访问 context 中的变量，禁止执行任意代码。

    参数：
        condition: Python 条件表达式字符串。
        context: 变量上下文（evidence_data, extra 等）。

    返回：
        True/False。
    """
    try:
        # 只允许安全的内置函数
        safe_builtins = {
            "True": True,
            "False": False,
            "None": None,
            "len": len,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "isinstance": isinstance,
            "hasattr": hasattr,
            "getattr": getattr,
        }
        result = eval(condition, {"__builtins__": safe_builtins}, context)  # noqa: S307
        return bool(result)
    except Exception as exc:
        logger.debug(
            "规则条件求值失败: condition=%s error=%s",
            condition[:80], str(exc)[:100],
        )
        return False


# ------------------------------------------------------------
# Evidence Provenance: 关系图构建与路径查找（V2.2）
# ------------------------------------------------------------

def build_relation_graph(all_relations: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """从数据库 relations 构建无向邻接表。

    参数：
        all_relations: 数据库中所有 relation 记录列表。
            每条记录必须包含：relation_id, from_company_id, to_company_id, relation_type

    返回：
        邻接表 {company_id: [{neighbor, relation_id, relation_type, raw_relation}, ...]}
    """
    graph: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for rel in all_relations:
        fid = rel.get("from_company_id", "")
        tid = rel.get("to_company_id", "")
        if not fid or not tid:
            continue
        entry = {
            "neighbor": tid,
            "relation_id": rel.get("relation_id", ""),
            "relation_type": rel.get("relation_type", ""),
            "raw_relation": rel,
        }
        graph[fid].append(entry)
        # 无向图：反向也添加
        reverse_entry = {
            "neighbor": fid,
            "relation_id": rel.get("relation_id", ""),
            "relation_type": rel.get("relation_type", ""),
            "raw_relation": rel,
        }
        graph[tid].append(reverse_entry)
    return dict(graph)


def find_shortest_path(
    graph: Dict[str, List[Dict[str, Any]]],
    source: str,
    target: str,
) -> Optional[Dict[str, Any]]:
    """BFS 查找 source → target 的最短路径。

    返回：
        None（不可达）或：
        {
            "path": ["C004", "C005", "C006", "C007"],
            "depth": 3,
            "relation_ids": ["R005", "R006", "R007"],
            "relation_types": ["股权", "对外投资", "股权"],
        }
    """
    if source == target:
        return {"path": [source], "depth": 0, "relation_ids": [], "relation_types": []}

    visited = {source}
    queue = deque([(source, [source], [], [])])

    while queue:
        current, path, rel_ids, rel_types = queue.popleft()
        for neighbor_entry in graph.get(current, []):
            neighbor = neighbor_entry["neighbor"]
            if neighbor in visited:
                continue
            new_path = path + [neighbor]
            new_rel_ids = rel_ids + [neighbor_entry["relation_id"]]
            new_rel_types = rel_types + [neighbor_entry["relation_type"]]
            if neighbor == target:
                return {
                    "path": new_path,
                    "depth": len(new_path) - 1,
                    "relation_ids": new_rel_ids,
                    "relation_types": new_rel_types,
                }
            visited.add(neighbor)
            queue.append((neighbor, new_path, new_rel_ids, new_rel_types))

    return None  # 不可达


def compute_provenance(
    evidence_facts: List[Dict[str, Any]],
    target_company_id: str,
    all_relations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """为每条 evidence 计算 provenance（归属来源）。

    参数：
        evidence_facts: 原始 evidence 列表（含 evidence_id, evidence_type, data, company_id）。
        target_company_id: 目标企业 ID。
        all_relations: 数据库中所有 relation 记录。

    返回：
        带 provenance 的 evidence 列表。每条新增：
        - owner_company_id: 该 evidence 所属企业
        - target_company_id: 分析目标企业
        - is_target_company: bool
        - relation_depth: int（0=自身，N=经过 N 跳关系）
        - relation_path: List[str]（如 ["C004", "C005", "C006", "C007"]）
        - relation_ids: List[str]（如 ["R005", "R006", "R007"]）
        - relation_types: List[str]（如 ["股权", "对外投资", "股权"]）
        - target_role_in_relation: Optional[str]（如 "guarantor", "shareholder"）
    """
    graph = build_relation_graph(all_relations)

    # 预计算目标企业到所有可达企业的最短路径
    shortest_paths: Dict[str, Optional[Dict[str, Any]]] = {}
    all_companies = set()
    for fact in evidence_facts:
        cid = fact.get("company_id", "")
        if cid:
            all_companies.add(cid)

    for cid in all_companies:
        if cid == target_company_id:
            shortest_paths[cid] = {
                "path": [cid],
                "depth": 0,
                "relation_ids": [],
                "relation_types": [],
            }
        else:
            shortest_paths[cid] = find_shortest_path(graph, target_company_id, cid)

    result = []
    for fact in evidence_facts:
        owner_cid = fact.get("company_id", "")
        provenance = {
            "owner_company_id": owner_cid,
            "target_company_id": target_company_id,
            "is_target_company": (owner_cid == target_company_id),
        }

        path_info = shortest_paths.get(owner_cid)
        if path_info is None:
            # 不可达：设为深度 -1（孤儿 evidence）
            provenance["relation_depth"] = -1
            provenance["relation_path"] = [target_company_id, owner_cid] if owner_cid else []
            provenance["relation_ids"] = []
            provenance["relation_types"] = []
        else:
            provenance["relation_depth"] = path_info["depth"]
            provenance["relation_path"] = path_info["path"]
            provenance["relation_ids"] = path_info["relation_ids"]
            provenance["relation_types"] = path_info["relation_types"]

        # 推断目标企业在关系链末端的角色
        provenance["target_role_in_relation"] = _infer_target_role(
            provenance, fact, target_company_id, all_relations,
        )

        result.append({**fact, **provenance})

    return result


def _infer_target_role(
    provenance: Dict[str, Any],
    fact: Dict[str, Any],
    target_company_id: str,
    all_relations: List[Dict[str, Any]],
) -> Optional[str]:
    """推断目标企业在关系链末端的角色。

    返回：
        "guarantor" | "guaranteed_party" | "shareholder" | "investee" |
        "investor" | "common_shareholder" | "common_legal_rep" | None
    """
    if provenance["is_target_company"]:
        return None  # 自身 evidence 不需要角色

    # 找到路径末端的直接关系（target → ... → owner 的最后一跳）
    path = provenance.get("relation_path", [])
    relation_ids = provenance.get("relation_ids", [])
    if len(path) < 2 or not relation_ids:
        return None

    # 查找最后一跳的关系记录
    last_rel_id = relation_ids[-1]
    for rel in all_relations:
        if rel.get("relation_id") == last_rel_id:
            rel_type = rel.get("relation_type", "")
            from_cid = rel.get("from_company_id", "")
            to_cid = rel.get("to_company_id", "")

            if rel_type == "担保":
                if from_cid == target_company_id:
                    return "guarantor"  # 目标企业是担保方
                else:
                    return "guaranteed_party"  # 目标企业是被担保方
            elif rel_type == "股权":
                if from_cid == target_company_id:
                    return "shareholder"  # 目标企业是股东
                else:
                    return "investee"  # 目标企业是被投资方
            elif rel_type == "对外投资":
                if from_cid == target_company_id:
                    return "investor"
                else:
                    return "investee"
            elif rel_type == "共同股东":
                return "common_shareholder"
            elif rel_type == "共同法人":
                return "common_legal_rep"
            break

    return None


# ------------------------------------------------------------
# 主引擎类
# ------------------------------------------------------------

class RiskRuleEngine:
    """确定性风险规则引擎。

    输入：
        AI 调查产生的结构化风险事实（evidence_ids + 从数据库查询的原始数据）。

    输出：
        {
            "risk_score": int,               # 总风险分（0-100+）
            "risk_level": str,               # 风险等级（低风险/中风险/中高风险/高风险）
            "triggered_rules": [             # 触发的规则列表
                {
                    "rule_id": str,          # 规则ID
                    "rule_name": str,        # 规则名称
                    "dimension": str,        # 所属维度
                    "evidence_id": str,      # 关联的 Evidence ID
                    "score": int,            # 该规则分值
                    "severity": str,         # 严重程度
                    "description": str,      # 风险解释
                }
            ],
            "hard_rule_hits": [              # 触发的硬规则
                {
                    "rule_id": str,
                    "reason": str,
                    "force_level": str,
                }
            ],
            "dimension_scores": {            # 各维度得分
                "business": float,
                "judicial": float,
                "relationship": float,
                "public_opinion": float,
                "financial": float,
                "recruitment": float,
            },
            "evidence_ids": List[str],       # 参与评分的 Evidence IDs
            "total_evidence_count": int,     # 参与评分的 Evidence 总数
        }
    """

    def __init__(self, config: Dict[str, Any]):
        """初始化引擎。

        参数：
            config: 从 risk_rules.yaml 加载的配置 dict。
        """
        self.risk_levels = config["risk_levels"]
        self.dimension_weights = config["dimension_weights"]
        self.rules = config["rules"]
        self.hard_rules = config["hard_rules"]
        self._total_weight = sum(self.dimension_weights.values())

    def evaluate(
        self,
        evidence_facts: List[Dict[str, Any]],
        extra: Optional[Dict[str, Any]] = None,
        related_company_profiles: Optional[List[Dict[str, Any]]] = None,
        all_relations: Optional[List[Dict[str, Any]]] = None,
        transmission_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """执行确定性风险评估（V2.3A: 消除 company-level 规则重复计分）。

        V2.3B.2: 新增可选参数 related_company_profiles / all_relations /
        transmission_config，用于计算 relationship_exposure。

        参数：
            evidence_facts: AI 调查产生的风险事实列表（含 provenance 字段）。
            extra: 额外上下文信息（预计算指标等）。
            related_company_profiles: 关联企业 Own Risk Profile 列表（V2.3B.2）。
            all_relations: 全量关系数据（V2.3B.2）。
            transmission_config: 传导配置（V2.3B.2）。

        返回：
            结构化评估结果 dict（含 own_risk + relationship_exposure）。
        """
        extra = extra or {}

        # --------------------------------------------------------
        # 1. 分类规则：evidence-level vs company-level
        # --------------------------------------------------------
        evidence_level_rules = []  # condition 使用 evidence_data
        company_level_rules = []   # condition 仅使用 extra

        for rule in self.rules:
            condition = rule.get("condition", "")
            # 如果 condition 中不引用 evidence_data，则视为 company-level
            if "evidence_data" not in condition:
                company_level_rules.append(rule)
            else:
                evidence_level_rules.append(rule)

        # --------------------------------------------------------
        # 2. Evidence-level 规则：逐条 evidence 匹配
        # --------------------------------------------------------
        all_triggered_rules: List[Dict[str, Any]] = []
        evidence_scored_pairs: Set[Tuple[str, str]] = set()  # (evidence_id, rule_id)
        # V2.3A.1: max_hits 按 (rule_id, owner_company_id) 计数，避免跨公司共享配额
        rule_hit_counts: Dict[Tuple[str, str], int] = {}

        for fact in evidence_facts:
            evidence_id = fact.get("evidence_id", "")
            evidence_data = fact.get("data", {})
            owner_company_id = fact.get("owner_company_id", "")

            context = {
                "evidence_data": evidence_data,
                "extra": extra,
            }

            for rule in evidence_level_rules:
                rule_id = rule["id"]
                evidence_types = rule.get("evidence_types", [])

                # 类型过滤
                if evidence_types:
                    prefix = evidence_id[:1] if evidence_id else ""
                    if prefix not in evidence_types:
                        continue

                pair = (evidence_id, rule_id)
                if pair in evidence_scored_pairs:
                    continue

                # V2.3A.1: max_hits 上限检查（per owner_company_id）
                max_hits = rule.get("max_hits")
                if max_hits is not None:
                    hit_key = (rule_id, owner_company_id)
                    current_hits = rule_hit_counts.get(hit_key, 0)
                    if current_hits >= max_hits:
                        continue

                if _eval_condition(rule["condition"], context):
                    evidence_scored_pairs.add(pair)
                    hit_key = (rule_id, owner_company_id)
                    rule_hit_counts[hit_key] = rule_hit_counts.get(hit_key, 0) + 1
                    all_triggered_rules.append({
                        "rule_id": rule_id,
                        "rule_name": rule["name"],
                        "dimension": rule["dimension"],
                        "evidence_id": evidence_id,
                        "score": rule["score"],
                        "severity": rule["severity"],
                        "description": rule.get("description", ""),
                        "is_target_company": fact.get("is_target_company", True),
                        "owner_company_id": owner_company_id,
                        "relation_depth": fact.get("relation_depth", 0),
                        "hit_count": rule_hit_counts[hit_key],
                        "max_hits": max_hits,
                    })

        # --------------------------------------------------------
        # 3. Company-level 规则：每个 (owner_company_id, rule_id) 只评估一次
        # --------------------------------------------------------
        company_scored_pairs: Set[Tuple[str, str]] = set()  # (owner_company_id, rule_id)

        # 按 owner_company_id 分组 evidence
        company_evidence_map: Dict[str, List[Dict[str, Any]]] = {}
        for fact in evidence_facts:
            owner = fact.get("owner_company_id", "")
            company_evidence_map.setdefault(owner, []).append(fact)

        for owner_cid, company_facts in company_evidence_map.items():
            # 收集该公司的所有 evidence_ids
            company_evidence_ids = [f.get("evidence_id", "") for f in company_facts]
            # 取该公司的 is_target_company 标记
            is_target = any(f.get("is_target_company", True) for f in company_facts)
            rel_depth = company_facts[0].get("relation_depth", 0) if company_facts else 0

            # V2.3A: Company-level 规则（使用 extra）仅对目标企业自身评估
            # 因为 extra 中的指标（debt_ratio, consecutive_loss_years 等）
            # 是从目标企业财务数据计算的，不适用于关联企业
            if not is_target:
                continue

            for rule in company_level_rules:
                rule_id = rule["id"]
                evidence_types = rule.get("evidence_types", [])

                # 类型过滤：检查该公司是否有匹配类型的 evidence
                if evidence_types:
                    has_matching_type = any(
                        eid[:1] in evidence_types
                        for eid in company_evidence_ids
                        if eid
                    )
                    if not has_matching_type:
                        continue

                pair = (owner_cid, rule_id)
                if pair in company_scored_pairs:
                    continue

                # 用 extra 求值（company-level 规则只依赖 extra）
                context = {"evidence_data": {}, "extra": extra}

                if _eval_condition(rule["condition"], context):
                    company_scored_pairs.add(pair)
                    # 该公司所有匹配类型的 evidence 都作为支撑证据
                    supporting_eids = [
                        eid for eid in company_evidence_ids
                        if eid and (not evidence_types or eid[:1] in evidence_types)
                    ]
                    # 取第一条作为代表 evidence_id（company-level 规则无单一 evidence 对应）
                    primary_eid = supporting_eids[0] if supporting_eids else ""
                    all_triggered_rules.append({
                        "rule_id": rule_id,
                        "rule_name": rule["name"],
                        "dimension": rule["dimension"],
                        "evidence_id": primary_eid,
                        "score": rule["score"],
                        "severity": rule["severity"],
                        "description": rule.get("description", ""),
                        "is_target_company": is_target,
                        "owner_company_id": owner_cid,
                        "relation_depth": rel_depth,
                        # V2.3A: company-level 规则记录所有支撑证据
                        "supporting_evidence_ids": supporting_eids,
                        "hit_count": 1,  # 公司级规则每个公司只命中一次
                    })

        # --------------------------------------------------------
        # 2. 按 provenance 分离 own / related triggered rules
        # --------------------------------------------------------
        own_triggered = [r for r in all_triggered_rules if r.get("is_target_company", True)]
        related_triggered = [r for r in all_triggered_rules if not r.get("is_target_company", True)]

        # --------------------------------------------------------
        # 3. 分别计算 own / related 的分数
        # --------------------------------------------------------
        own_score = sum(r["score"] for r in own_triggered)
        related_score = sum(r["score"] for r in related_triggered)

        # --------------------------------------------------------
        # 4. 分别计算维度得分
        # --------------------------------------------------------
        own_dimension_scores = self._compute_dimension_scores(own_triggered, own_score)
        related_dimension_scores = self._compute_dimension_scores(related_triggered, related_score)

        # --------------------------------------------------------
        # 5. 硬规则检查（仅基于 own evidence + extra）
        # --------------------------------------------------------
        hard_rule_hits: List[Dict[str, Any]] = []
        force_level: Optional[str] = None
        max_severity_order = 0
        severity_order = {"低风险": 0, "中风险": 1, "中高风险": 2, "高风险": 3}

        for hr in self.hard_rules:
            if _eval_condition(hr["condition"], {"extra": extra}):
                hard_rule_hits.append({
                    "rule_id": hr["id"],
                    "reason": hr["reason"],
                    "force_level": hr["force_level"],
                })
                order = severity_order.get(hr["force_level"], -1)
                if order > max_severity_order:
                    max_severity_order = order
                    force_level = hr["force_level"]

        # --------------------------------------------------------
        # 6. 风险等级确定
        # --------------------------------------------------------
        own_level = force_level if force_level else self._calculate_level(own_score)
        related_level = self._calculate_level(related_score)

        # --------------------------------------------------------
        # 7. 组装结果
        # --------------------------------------------------------
        own_evidence_ids = list(dict.fromkeys(
            r["evidence_id"] for r in own_triggered
        ))
        related_evidence_ids = list(dict.fromkeys(
            r["evidence_id"] for r in related_triggered
        ))

        # comprehensive_risk: 本阶段不伪造公式
        comprehensive_score = None
        comprehensive_level = None

        return {
            # V2.1 兼容字段（保留，值等于 own_risk）
            "risk_score": own_score,
            "risk_level": own_level,
            "triggered_rules": own_triggered,  # V2.1 兼容：只返回 own triggered
            "hard_rule_hits": hard_rule_hits,
            "dimension_scores": own_dimension_scores,
            "evidence_ids": own_evidence_ids,
            "total_evidence_count": len(evidence_facts),

            # V2.2 新增：分离结构
            "own_risk": {
                "score": own_score,
                "level": own_level,
                "triggered_rules": own_triggered,
                "dimension_scores": own_dimension_scores,
                "evidence_ids": own_evidence_ids,
                "evidence_count": sum(1 for f in evidence_facts if f.get("is_target_company", True)),
            },

            # V2.3B.2: relationship_exposure 使用 compute_relationship_exposure() 计算
            # 当 related_company_profiles 未提供时，保持 NOT_CALIBRATED 占位
            "relationship_exposure": self._build_relationship_exposure(
                related_company_profiles or [],
                all_relations or [],
                transmission_config,
            ),

            "comprehensive_risk": {
                "score": comprehensive_score,
                "level": comprehensive_level,
                "status": "NOT_CALIBRATED",
            },
        }

    def _compute_dimension_scores(
        self,
        triggered_rules: List[Dict[str, Any]],
        total_score: int,
    ) -> Dict[str, float]:
        """计算维度得分（归一化权重）。"""
        dimension_scores: Dict[str, float] = {dim: 0.0 for dim in self.dimension_weights}

        for triggered in triggered_rules:
            dim = triggered["dimension"]
            if dim in dimension_scores:
                dimension_scores[dim] += triggered["score"]

        if self._total_weight > 0 and total_score > 0:
            for dim in dimension_scores:
                raw = dimension_scores[dim]
                if raw > 0:
                    weight = self.dimension_weights.get(dim, 0)
                    dimension_scores[dim] = round(
                        (weight / self._total_weight) * total_score, 2
                    )

        return dimension_scores

    def _calculate_level(self, score: int) -> str:
        """根据分数确定风险等级。"""
        for level_def in self.risk_levels:
            if level_def["min_score"] <= score <= level_def["max_score"]:
                return level_def["level"]
        # 超出最高区间时，返回最高风险等级
        return self.risk_levels[-1]["level"]

    def _build_relationship_exposure(
        self,
        related_company_profiles: List[Dict[str, Any]],
        all_relations: List[Dict[str, Any]],
        transmission_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """构建 relationship_exposure 结构（V2.3B.2）。

        当提供了 related_company_profiles 和 all_relations 时，
        使用 compute_relationship_exposure() 计算传导分数。
        否则返回 NOT_CALIBRATED 占位结构。

        参数：
            related_company_profiles: 关联企业 Own Risk Profile 列表。
            all_relations: 全量关系数据。
            transmission_config: 传导配置（None 时自动加载）。

        返回：
            relationship_exposure 结构化 dict。
        """
        if not related_company_profiles:
            return {
                "status": "NOT_CALIBRATED",
                "score": None,
                "level": None,
                "level_status": "NOT_CALIBRATED",
                "related_company_profiles": [],
                "company_contributions": [],
                "transmission_version": None,
                "transmission_config_hash": None,
            }

        # 加载传导配置
        if transmission_config is None:
            try:
                transmission_config = load_transmission_config()
            except Exception as exc:
                logger.warning(
                    "[RuleEngine] Risk Transmission 配置加载失败: %s", exc
                )
                return {
                    "status": "NOT_CALIBRATED",
                    "score": None,
                    "level": None,
                    "level_status": "NOT_CALIBRATED",
                    "related_company_profiles": related_company_profiles,
                    "company_contributions": [],
                    "transmission_version": None,
                    "transmission_config_hash": None,
                }

        # 计算 relationship exposure
        exposure = compute_relationship_exposure(
            target_company_id="",  # 此处不使用 target_company_id
            related_company_profiles=related_company_profiles,
            all_relations=all_relations,
            transmission_config=transmission_config,
        )

        # 附加 related_company_profiles（供前端展示）
        exposure["related_company_profiles"] = related_company_profiles

        return exposure

    def evaluate_company_own_risk(
        self,
        company_id: str,
        evidence_facts: List[Dict[str, Any]],
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """计算指定企业的 Own Risk（V2.3B.1）。

        无论该企业是主分析目标还是关联企业，
        都使用完全相同的 Risk Rule Engine 逻辑。

        参数：
            company_id: 要评估的企业ID。
            evidence_facts: 该企业的风险事实列表（is_target_company 应均为 True）。
            extra: 该企业自身的预计算指标。

        返回：
            own_risk 结构化结果 dict。
        """
        # 确保所有 evidence 都标记为 is_target_company=True
        # 因为这是在计算该企业自己的 Own Risk
        normalized_facts = []
        for fact in evidence_facts:
            f = dict(fact)
            f["is_target_company"] = True
            f["owner_company_id"] = company_id
            f["target_company_id"] = company_id
            f["relation_depth"] = 0
            f["relation_path"] = [company_id]
            f["relation_ids"] = []
            f["relation_types"] = []
            f["target_role_in_relation"] = None
            normalized_facts.append(f)

        result = self.evaluate(normalized_facts, extra or {})
        return result["own_risk"]


# ============================================================
# V2.3B.2: Risk Transmission 引擎
# ============================================================

DEFAULT_TRANSMISSION_CONFIG_PATH = PROJECT_ROOT / "config" / "risk_transmission.yaml"


def load_transmission_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """加载 risk_transmission.yaml 配置文件。

    参数：
        config_path: 配置文件路径，None 时使用默认路径。

    返回：
        完整配置 dict。

    异常：
        FileNotFoundError: 配置文件不存在。
        yaml.YAMLError: YAML 解析失败。
    """
    path = config_path or DEFAULT_TRANSMISSION_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Risk Transmission 配置文件不存在：{path}")

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


def get_transmission_config_hash(config: Dict[str, Any]) -> str:
    """计算配置文件的 hash，用于版本追溯。

    参数：
        config: 传导配置 dict。

    返回：
        16 字符的 sha256 hash 前缀。
    """
    import hashlib
    config_str = yaml.dump(config, sort_keys=True, allow_unicode=True)
    return hashlib.sha256(config_str.encode("utf-8")).hexdigest()[:16]


def find_all_paths(
    graph: Dict[str, List[Dict[str, Any]]],
    source: str,
    target: str,
    max_depth: int = 4,
) -> List[Dict[str, Any]]:
    """DFS 查找 source → target 的所有简单路径（无环）。

    返回所有路径列表，按深度升序排列。每条路径结构：
    {
        "path": ["C004", "C005", "C006", "C007"],
        "depth": 3,
        "relation_ids": ["R005", "R006", "R007"],
        "relation_types": ["股权", "对外投资", "股权"],
    }

    参数：
        graph: 无向邻接表。
        source: 起始企业 ID。
        target: 目标企业 ID。
        max_depth: 最大搜索深度（防止组合爆炸）。
    """
    if source == target:
        return [{
            "path": [source],
            "depth": 0,
            "relation_ids": [],
            "relation_types": [],
        }]

    results: List[Dict[str, Any]] = []
    visited = {source}

    def _dfs(current: str, path: List[str], rel_ids: List[str], rel_types: List[str]) -> None:
        if len(path) > max_depth + 1:
            return
        for neighbor_entry in graph.get(current, []):
            neighbor = neighbor_entry["neighbor"]
            if neighbor in visited:
                continue
            new_path = path + [neighbor]
            new_rel_ids = rel_ids + [neighbor_entry["relation_id"]]
            new_rel_types = rel_types + [neighbor_entry["relation_type"]]
            if neighbor == target:
                results.append({
                    "path": new_path,
                    "depth": len(new_path) - 1,
                    "relation_ids": new_rel_ids,
                    "relation_types": new_rel_types,
                })
                continue
            visited.add(neighbor)
            _dfs(neighbor, new_path, new_rel_ids, new_rel_types)
            visited.discard(neighbor)

    _dfs(source, [source], [], [])

    # 按深度升序排列
    results.sort(key=lambda p: p["depth"])
    return results


def _infer_target_role_for_path(
    path_info: Dict[str, Any],
    target_company_id: str,
    all_relations: List[Dict[str, Any]],
) -> Optional[str]:
    """根据路径推断目标企业在关系链中的角色。

    使用路径第一跳（target → next company）推断目标角色。

    返回：
        "guarantor" | "guaranteed_party" | "shareholder" | "investee" |
        "investor" | "common_shareholder" | "common_legal_rep" | None
    """
    path = path_info.get("path", [])
    relation_ids = path_info.get("relation_ids", [])

    if len(path) < 2 or not relation_ids:
        return None

    # 使用第一跳的关系推断角色
    first_rel_id = relation_ids[0]
    for rel in all_relations:
        if rel.get("relation_id") == first_rel_id:
            rel_type = rel.get("relation_type", "")
            from_cid = rel.get("from_company_id", "")
            to_cid = rel.get("to_company_id", "")

            if rel_type == "担保":
                if from_cid == target_company_id:
                    return "guarantor"
                else:
                    return "guaranteed_party"
            elif rel_type == "股权":
                if from_cid == target_company_id:
                    return "shareholder"
                else:
                    return "investee"
            elif rel_type == "对外投资":
                if from_cid == target_company_id:
                    return "investor"
                else:
                    return "investee"
            elif rel_type == "共同股东":
                return "common_shareholder"
            elif rel_type == "共同法人":
                return "common_legal_rep"
            break

    return None


def compute_path_transmission(
    own_score: int,
    path_info: Dict[str, Any],
    transmission_config: Dict[str, Any],
    all_relations: List[Dict[str, Any]],
    target_company_id: str,
) -> Dict[str, Any]:
    """计算单条路径的风险传导结果。

    公式：
        transmitted_score = own_score × relation_type_factor × target_role_factor × depth_factor

    参数：
        own_score: 关联企业 own risk score。
        path_info: 路径信息 (path, depth, relation_ids, relation_types)。
        transmission_config: 传导配置。
        all_relations: 全量关系数据（用于推断 target_role）。
        target_company_id: 目标企业ID。

    返回：
        PathTransmission 结构化 dict。
    """
    # 零风险零传导
    if own_score == 0 and transmission_config.get("zero_risk_zero_transmission", True):
        return {
            "path": path_info["path"],
            "depth": path_info["depth"],
            "relation_ids": path_info["relation_ids"],
            "relation_types": path_info["relation_types"],
            "target_role": None,
            "transmission_strength": 0.0,
            "transmitted_score": 0,
            "transmission_factors": {
                "relation_type_factor": 0.0,
                "target_role_factor": 0.0,
                "depth_factor": 0.0,
            },
            "transmission_reasons": ["own_score=0，零风险零传导"],
        }

    # 1. relation_type_factor: 取路径最后一个 relation_type
    relation_types = path_info.get("relation_types", [])
    last_rel_type = relation_types[-1] if relation_types else ""
    rt_factor_map = transmission_config.get("relation_type_factor", {})
    rt_factor = rt_factor_map.get(last_rel_type, 0.5)  # 默认 0.5

    # 2. target_role_factor: 使用第一跳推断角色
    target_role = _infer_target_role_for_path(path_info, target_company_id, all_relations)
    tr_factor_map = transmission_config.get("target_role_factor", {})
    tr_factor = tr_factor_map.get(target_role, 0.5) if target_role else 0.5

    # 3. depth_factor
    depth = path_info.get("depth", 1)
    depth_map = transmission_config.get("depth_factor", {})
    depth_factor = depth_map.get(depth, depth_map.get("default", 0.2))

    # 4. 计算传导分数
    transmission_strength = rt_factor * tr_factor * depth_factor
    transmitted_score = int(round(own_score * transmission_strength))

    # 5. 传导原因（确定性，不能由 LLM 判断）
    reasons = []
    reasons.append(f"关联企业 own_score={own_score}")
    reasons.append(f"路径: {' → '.join(path_info['path'])}")
    reasons.append(f"路径深度={depth}，depth_factor={depth_factor}")
    reasons.append(f"最终关系类型={last_rel_type}，relation_type_factor={rt_factor}")
    if target_role:
        reasons.append(f"目标角色={target_role}，target_role_factor={tr_factor}")
    reasons.append(f"transmitted_score={own_score} × {rt_factor} × {tr_factor} × {depth_factor} = {transmitted_score}")

    return {
        "path": path_info["path"],
        "depth": path_info["depth"],
        "relation_ids": path_info["relation_ids"],
        "relation_types": path_info["relation_types"],
        "target_role": target_role,
        "relation_type_factor": rt_factor,
        "target_role_factor": tr_factor,
        "depth_factor": depth_factor,
        "transmission_strength": round(transmission_strength, 4),
        "transmitted_score": transmitted_score,
        "transmission_factors": {
            "relation_type_factor": rt_factor,
            "target_role_factor": tr_factor,
            "depth_factor": depth_factor,
        },
        "transmission_reasons": reasons,
    }


def compute_company_exposure_contribution(
    company_id: str,
    own_score: int,
    own_level: str,
    company_name: str,
    all_path_transmissions: List[Dict[str, Any]],
    all_paths: List[Dict[str, Any]],
    transmission_config: Dict[str, Any],
) -> Dict[str, Any]:
    """计算单个关联企业的 Company Exposure Contribution。

    策略：同一关联企业取 strongest effective path 的 transmitted_score 作为贡献。
    保留 all_paths 供审计。

    参数：
        company_id: 关联企业ID。
        own_score: 关联企业 own risk score。
        own_level: 关联企业 own risk level。
        company_name: 关联企业名称。
        all_path_transmissions: 所有路径的传导计算结果。
        all_paths: 所有路径信息。
        transmission_config: 传导配置。

    返回：
        CompanyExposureContribution 结构化 dict。
    """
    # 取 strongest path（transmitted_score 最大的路径）
    strongest = None
    if all_path_transmissions:
        strongest = max(all_path_transmissions, key=lambda t: t["transmitted_score"])

    transmitted_score = strongest["transmitted_score"] if strongest else 0
    transmission_factors = strongest["transmission_factors"] if strongest else {}
    transmission_reasons = strongest["transmission_reasons"] if strongest else []

    return {
        "company_id": company_id,
        "company_name": company_name,
        "own_score": own_score,
        "own_level": own_level,
        "strongest_path": {
            "path": strongest["path"] if strongest else [],
            "depth": strongest["depth"] if strongest else 0,
            "relation_ids": strongest["relation_ids"] if strongest else [],
            "relation_types": strongest["relation_types"] if strongest else [],
            "transmitted_score": strongest["transmitted_score"] if strongest else 0,
            "transmission_factors": strongest["transmission_factors"] if strongest else {},
        } if strongest else None,
        "transmitted_score": transmitted_score,
        "transmission_factors": transmission_factors,
        "all_paths": all_paths,
        "all_path_transmissions": all_path_transmissions,
        "transmission_reasons": transmission_reasons,
    }


def compute_relationship_exposure(
    target_company_id: str,
    related_company_profiles: List[Dict[str, Any]],
    all_relations: List[Dict[str, Any]],
    transmission_config: Dict[str, Any],
) -> Dict[str, Any]:
    """计算目标企业的 Relationship Exposure。

    参数：
        target_company_id: 目标企业ID。
        related_company_profiles: 所有关联企业的 Own Risk Profile。
        all_relations: 全量关系数据。
        transmission_config: 传导配置。

    返回：
        Relationship Exposure 结构化 dict：
        {
            "status": "CALIBRATED_V1",
            "score": int,
            "level": str | None,
            "level_status": "CALIBRATED" | "NOT_CALIBRATED",
            "company_contributions": [...],
            "transmission_version": str,
            "transmission_config_hash": str,
        }
    """
    version = transmission_config.get("version", "1.0.0")
    config_hash = get_transmission_config_hash(transmission_config)

    # 构建关系图（用于自动查找路径）
    graph = build_relation_graph(all_relations)

    # 为每个关联企业计算传导贡献
    company_contributions: List[Dict[str, Any]] = []

    for profile in related_company_profiles:
        company_id = profile["company_id"]
        own_score = profile.get("own_score", 0)
        own_level = profile.get("own_level", "低风险")
        company_name = profile.get("company_name", "")
        all_paths = profile.get("all_paths", [])

        # V2.3B.2: 如果 profile 没有 all_paths，自动从关系图中查找
        if not all_paths and target_company_id and company_id:
            all_paths = find_all_paths(graph, target_company_id, company_id)

        # 对每条路径计算传导
        path_transmissions: List[Dict[str, Any]] = []
        for path_info in all_paths:
            pt = compute_path_transmission(
                own_score=own_score,
                path_info=path_info,
                transmission_config=transmission_config,
                all_relations=all_relations,
                target_company_id=target_company_id,
            )
            path_transmissions.append(pt)

        # 计算 company exposure contribution
        contribution = compute_company_exposure_contribution(
            company_id=company_id,
            own_score=own_score,
            own_level=own_level,
            company_name=company_name,
            all_path_transmissions=path_transmissions,
            all_paths=all_paths,
            transmission_config=transmission_config,
        )
        company_contributions.append(contribution)

    # 聚合：取所有 company contribution 的 max（保守策略，避免多路径重复放大）
    if company_contributions:
        exposure_score = max(c["transmitted_score"] for c in company_contributions)
    else:
        exposure_score = 0

    # 确定 exposure level（使用独立阈值）
    exposure_levels = transmission_config.get("exposure_levels", [])
    exposure_level = None
    level_status = "NOT_CALIBRATED"
    for level_def in exposure_levels:
        if level_def["min_score"] <= exposure_score <= level_def["max_score"]:
            exposure_level = level_def["level"]
            level_status = "CALIBRATED"
            break

    return {
        "status": "CALIBRATED_V1",
        "score": exposure_score,
        "level": exposure_level,
        "level_status": level_status,
        "company_contributions": company_contributions,
        "transmission_version": version,
        "transmission_config_hash": config_hash,
    }


# ------------------------------------------------------------
# V2.3B.1: 关联企业 Risk Profile 构建
# ------------------------------------------------------------

def build_company_evidence_and_extra(
    company_id: str,
    deps_module: Any,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """为指定企业构建 Risk Rule Engine 输入（V2.3B.1）。

    从 DB 加载该企业自身的 B/J/P/F/H evidence，
    并从该企业自己的 financial reports 计算 extra 指标。

    参数：
        company_id: 企业ID。
        deps_module: 数据访问模块（提供 get_* 函数）。

    返回：
        (evidence_facts, extra)
    """
    evidence_facts: List[Dict[str, Any]] = []

    # 加载该企业的所有 evidence
    def _load_events(table_name: str, evidence_type: str, eid_prefix: str,
                     data_builder: Any) -> None:
        try:
            getter = getattr(deps_module, f"get_{table_name}", None)
            if getter:
                events = getter(company_id)
                for ev in events:
                    eid = ev.get("event_id") or ev.get("report_id", "")
                    evidence_facts.append({
                        "evidence_id": f"{eid_prefix}{eid}",
                        "evidence_type": evidence_type,
                        "data": data_builder(ev),
                        "company_id": company_id,
                    })
        except Exception:
            pass

    _load_events("business_events", "business", "B",
                 lambda ev: {"event_type": ev.get("event_type", ""), "description": ev.get("detail", "")})
    _load_events("judicial_events", "judicial", "J",
                 lambda ev: {"case_type": ev.get("case_type", ""), "role": ev.get("role", ""), "amount": ev.get("amount")})
    _load_events("public_opinion_events", "public_opinion", "P",
                 lambda ev: {"sentiment": ev.get("sentiment", ""), "verification_status": ev.get("verification_status", "")})
    _load_events("financial_reports", "financial", "F",
                 lambda ev: {"audit_opinion": ev.get("audit_opinion", ""), "period": ev.get("period", "")})
    _load_events("recruitment_events", "recruitment", "H",
                 lambda ev: {"position_type": ev.get("position_category", ""), "position_name": ev.get("position_name", "")})

    # 构建 extra（从该企业自己的财务数据）
    extra: Dict[str, Any] = {}

    profile = deps_module.get_company_profile(company_id)
    if profile:
        extra["business_status"] = profile.get("business_status", "")

    try:
        financial_reports = deps_module.get_financial_reports(company_id)
        if financial_reports:
            latest = financial_reports[-1]
            # debt_ratio: 从 total_liabilities/total_assets 计算（DB 不存储此字段）
            total_liabilities = latest.get("total_liabilities")
            total_assets = latest.get("total_assets")
            if total_liabilities is not None and total_assets is not None and total_assets > 0:
                extra["debt_ratio"] = total_liabilities / total_assets
            else:
                extra["debt_ratio"] = latest.get("debt_ratio")
            extra["latest_operating_cash_flow"] = latest.get("operating_cash_flow")
            extra["revenue_yoy"] = latest.get("revenue_yoy")
            extra["profit_yoy"] = latest.get("profit_yoy")

            consecutive_loss = 0
            for report in reversed(financial_reports):
                net_profit = report.get("net_profit")
                if net_profit is not None and net_profit < 0:
                    consecutive_loss += 1
                else:
                    break
            extra["consecutive_loss_years"] = consecutive_loss
    except Exception:
        pass

    try:
        recruitment = deps_module.get_recruitment_events(company_id)
        extra["recruitment_count"] = len(recruitment)
    except Exception:
        pass

    try:
        judicial_events = deps_module.get_judicial_events(company_id)
        extra["has_bankruptcy_case"] = any(
            je.get("case_type") == "破产案件" for je in judicial_events
        )
        extra["has_dishonest_execution"] = any(
            je.get("case_type") == "失信被执行人" for je in judicial_events
        )
    except Exception:
        pass

    return evidence_facts, extra


def build_related_company_profiles(
    target_company_id: str,
    related_company_ids: List[str],
    evidence_facts: List[Dict[str, Any]],
    all_relations: List[Dict[str, Any]],
    engine: RiskRuleEngine,
    deps_module: Any,
) -> List[Dict[str, Any]]:
    """为每个关联企业构建 Own Risk Profile（V2.3B.1 → V2.3B.2 增强）。

    每个关联企业使用自己的 B/J/P/F/H evidence 和自己的财务数据，
    通过同一套 Risk Rule Engine 计算 own risk。

    V2.3B.2 变更：
    1. 即使关联企业没有 evidence，也生成 profile（own_score=0, own_level="低风险"）
    2. 路径信息使用 find_all_paths() 重新计算（不再从 provenance 提取）
    3. 添加 multi_path 语义支持（all_paths 字段）

    参数：
        target_company_id: 目标企业ID。
        related_company_ids: 关联企业ID列表。
        evidence_facts: 所有 evidence（含 provenance）。
        all_relations: 全量关系数据。
        engine: RiskRuleEngine 实例。
        deps_module: 数据访问模块。

    返回：
        List[RelatedCompanyRiskProfile]
    """
    # 构建关系图
    graph = build_relation_graph(all_relations)

    profiles: List[Dict[str, Any]] = []
    scored_companies: Set[str] = set()  # 防止重复计算

    for company_id in related_company_ids:
        if company_id in scored_companies:
            continue
        scored_companies.add(company_id)

        # 计算该关联企业的 Own Risk（使用自己的数据）
        own_score = 0
        own_level = "低风险"
        triggered_rules: List[Dict[str, Any]] = []
        dimension_scores: Dict[str, float] = {}
        evidence_ids: List[str] = []
        evidence_count = 0
        hard_rule_hits: List[Dict[str, Any]] = []

        try:
            company_evidence, company_extra = build_company_evidence_and_extra(
                company_id, deps_module
            )
            own_risk = engine.evaluate_company_own_risk(
                company_id, company_evidence, company_extra
            )
            own_score = own_risk["score"]
            own_level = own_risk["level"]
            triggered_rules = own_risk["triggered_rules"]
            dimension_scores = own_risk["dimension_scores"]
            evidence_ids = own_risk["evidence_ids"]
            evidence_count = own_risk["evidence_count"]
            hard_rule_hits = own_risk.get("hard_rule_hits", [])
        except Exception as exc:
            logger.warning(
                "[RuleEngine] 关联企业 %s Own Risk 计算失败: %s", company_id, exc
            )
            # 即使计算失败，仍然生成 profile（own_score=0）

        # 使用 find_all_paths 查找所有路径
        all_paths = find_all_paths(graph, target_company_id, company_id)

        # 取最短路径的元数据作为 profile 的路径信息
        relation_path = [target_company_id]
        relation_ids: List[str] = []
        relation_types: List[str] = []
        relation_depth = 0

        if all_paths:
            shortest = all_paths[0]  # find_all_paths 已按深度排序
            relation_path = shortest["path"]
            relation_ids = shortest["relation_ids"]
            relation_types = shortest["relation_types"]
            relation_depth = shortest["depth"]

        # 推断目标角色（使用最短路径）
        target_role = None
        if relation_ids:
            shortest_info = {
                "path": relation_path,
                "depth": relation_depth,
                "relation_ids": relation_ids,
                "relation_types": relation_types,
            }
            target_role = _infer_target_role_for_path(
                shortest_info, target_company_id, all_relations
            )

        # 获取企业名称
        company_name = ""
        try:
            profile = deps_module.get_company_profile(company_id)
            if profile:
                company_name = profile.get("company_name", "")
        except Exception:
            pass

        profile = {
            "company_id": company_id,
            "company_name": company_name,
            "own_score": own_score,
            "own_level": own_level,
            "triggered_rules": triggered_rules,
            "dimension_scores": dimension_scores,
            "evidence_ids": evidence_ids,
            "evidence_count": evidence_count,
            "hard_rule_hits": hard_rule_hits,
            "relation_depth": relation_depth,
            "relation_path": relation_path,
            "relation_ids": relation_ids,
            "relation_types": relation_types,
            "target_role_in_relation": target_role,
            "all_paths": all_paths,  # V2.3B.2: 多路径支持
        }
        profiles.append(profile)

    # 按 own_score 降序排列（最危险的排前面）
    profiles.sort(key=lambda p: p["own_score"], reverse=True)

    return profiles


# ------------------------------------------------------------
# 便捷函数
# ------------------------------------------------------------

_default_engine: Optional[RiskRuleEngine] = None


def get_engine(config_path: Optional[Path] = None) -> RiskRuleEngine:
    """获取全局 RiskRuleEngine 单例（懒加载）。"""
    global _default_engine
    if _default_engine is None:
        config = load_config(config_path)
        _default_engine = RiskRuleEngine(config)
    return _default_engine


def evaluate_risk(
    evidence_facts: List[Dict[str, Any]],
    extra: Optional[Dict[str, Any]] = None,
    config_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """便捷函数：执行风险评估。

    等同于 get_engine(config_path).evaluate(evidence_facts, extra)。
    """
    engine = get_engine(config_path)
    return engine.evaluate(evidence_facts, extra)
