"""
Comprehensive Risk Fusion Engine (V2.4.1)

融合 own_risk 和 relationship_exposure，
生成最终企业风险判断（comprehensive_risk）。

公式：comprehensive_score = max(own_score, exposure_score) + case_bonus

四种 Case：
  A: 双重风险（own high + exposure high）
  B: 传染风险（own low + high risk transmission source）
  C: 孤立风险（own high + exposure low）
  D: 低风险（both low）
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# 配置加载
# ------------------------------------------------------------

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "comprehensive_risk.yaml"


def load_comprehensive_config(
    config_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """加载 comprehensive_risk.yaml 配置文件。

    参数：
        config_path: 配置文件路径，None 时使用默认路径。

    返回：
        完整配置 dict。

    异常：
        FileNotFoundError: 配置文件不存在。
        yaml.YAMLError: YAML 解析失败。
        ValueError: 缺少必要字段。
    """
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Comprehensive Risk 配置文件不存在：{path}")

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    required_keys = [
        "version", "fusion_strategy", "high_threshold",
        "case_bonuses", "comprehensive_levels", "hard_rule_override",
    ]
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Comprehensive Risk 配置文件缺少必要字段：{key}")

    return config


def get_comprehensive_config_hash(config: Dict[str, Any]) -> str:
    """计算配置文件的 hash，用于版本追溯。

    参数：
        config: 配置 dict。

    返回：
        配置的 SHA256 前 16 位 hex 字符串。
    """
    config_str = yaml.dump(config, sort_keys=True, allow_unicode=True)
    return hashlib.sha256(config_str.encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------
# Case 判定
# ------------------------------------------------------------

def _has_risk_transmission_source(
    contributions: List[Dict[str, Any]],
    high_threshold: int,
) -> bool:
    """检查是否存在风险传染通道。

    传染通道 = 存在关联企业 own_score >= high_threshold 且 transmitted_score > 0。

    参数：
        contributions: company_contributions 列表。
        high_threshold: own_score 的高阈值。

    返回：
        True/False。
    """
    for contrib in contributions:
        if contrib.get("own_score", 0) >= high_threshold and contrib.get("transmitted_score", 0) > 0:
            return True
    return False


def classify_case(
    own_score: int,
    exposure_score: int,
    contributions: List[Dict[str, Any]],
    high_threshold: Dict[str, int],
) -> str:
    """判定风险 Case。

    参数：
        own_score: 自身风险分。
        exposure_score: 传导风险分。
        contributions: company_contributions 列表。
        high_threshold: {"own_score": int, "exposure_score": int}

    返回：
        "A" | "B" | "C" | "D"
    """
    own_is_high = own_score >= high_threshold.get("own_score", 50)

    exposure_is_high = (
        exposure_score >= high_threshold.get("exposure_score", 50)
        or _has_risk_transmission_source(contributions, high_threshold.get("own_score", 50))
    )

    if own_is_high and exposure_is_high:
        return "A"
    elif not own_is_high and exposure_is_high:
        return "B"
    elif own_is_high and not exposure_is_high:
        return "C"
    else:
        return "D"


# ------------------------------------------------------------
# 硬规则覆盖
# ------------------------------------------------------------

def _check_hard_rule_override(
    hard_rule_hits: List[str],
    override_rules: List[str],
    enabled: bool,
) -> bool:
    """检查是否触发硬规则覆盖。

    参数：
        hard_rule_hits: own_risk 命中的硬规则 ID 列表。
        override_rules: 需要触发覆盖的硬规则 ID 列表。
        enabled: 是否启用硬规则覆盖。

    返回：
        True（触发覆盖）/ False。
    """
    if not enabled:
        return False
    for rule_id in hard_rule_hits:
        if rule_id in override_rules:
            return True
    return False


# ------------------------------------------------------------
# 等级映射
# ------------------------------------------------------------

def _score_to_level(
    score: int,
    levels: List[Dict[str, Any]],
) -> str:
    """将分数映射到风险等级。

    参数：
        score: 综合风险分。
        levels: 等级阈值列表。

    返回：
        风险等级字符串。
    """
    for level_def in levels:
        if level_def["min_score"] <= score <= level_def["max_score"]:
            return level_def["level"]
    # 兜底：取最后一个等级
    if levels:
        return levels[-1]["level"]
    return "低风险"


# ------------------------------------------------------------
# Explanation 生成
# ------------------------------------------------------------

def _generate_explanation(
    case: str,
    case_label: str,
    own_score: int,
    own_level: str,
    exposure_score: int,
    exposure_level: str,
    comprehensive_level: str,
    contributions: List[Dict[str, Any]],
) -> str:
    """生成自然语言解释。

    参数：
        case: Case 分类。
        case_label: Case 标签。
        own_score: 自身风险分。
        own_level: 自身风险等级。
        exposure_score: 传导风险分。
        exposure_level: 传导风险等级。
        comprehensive_level: 综合风险等级。
        contributions: company_contributions 列表。

    返回：
        解释字符串。
    """
    if case == "A":
        return (
            f"企业自身风险{own_level}({own_score}分)，"
            f"且关联企业风险传导{exposure_level}({exposure_score}分)，"
            f"综合判定为{comprehensive_level}。"
        )
    elif case == "B":
        # 找到最大的传染来源
        source = max(contributions, key=lambda c: c.get("transmitted_score", 0)) if contributions else None
        if source:
            return (
                f"企业自身风险{own_level}({own_score}分)，"
                f"但因关联企业{source.get('company_name') or source.get('company_id', '')}"
                f"({source.get('company_id', '')}, {source.get('own_score', 0)}分)的传导，"
                f"承受{exposure_level}({exposure_score}分)传染风险，"
                f"综合判定为{comprehensive_level}。"
            )
        else:
            return (
                f"企业自身风险{own_level}({own_score}分)，"
                f"但因关联企业风险传导，综合判定为{comprehensive_level}。"
            )
    elif case == "C":
        return (
            f"企业自身风险极高({own_score}分，{own_level})，"
            f"关联企业风险传导{exposure_level}({exposure_score}分)。"
            f"风险集中在企业自身经营/财务/司法问题。"
        )
    else:  # Case D
        return (
            f"企业自身风险{own_level}({own_score}分)，"
            f"关联企业风险传导{exposure_level}({exposure_score}分)，"
            f"综合判定为{comprehensive_level}。"
        )


# ------------------------------------------------------------
# 主入口
# ------------------------------------------------------------

def compute_comprehensive_risk(
    own_risk: Dict[str, Any],
    relationship_exposure: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """计算综合风险。

    参数：
        own_risk: {
            "score": int,
            "level": str,
            "hard_rule_hits": List[str]  # 命中的硬规则 ID 列表
        }
        relationship_exposure: {
            "score": int,
            "level": str,
            "company_contributions": List[Dict]  # 各关联企业贡献
        }
        config: 传导配置 dict，None 时自动加载。

    返回：
        ComprehensiveRiskOutput 结构。
    """
    if config is None:
        config = load_comprehensive_config()

    # 提取输入
    own_score = max(0, own_risk.get("score", 0))
    own_level = own_risk.get("level", "低风险")
    hard_rule_hits = own_risk.get("hard_rule_hits", [])

    exposure_score = max(0, relationship_exposure.get("score", 0))
    exposure_level = relationship_exposure.get("level", "低风险")
    contributions = relationship_exposure.get("company_contributions", [])

    # 配置参数
    high_threshold = config.get("high_threshold", {"own_score": 50, "exposure_score": 50})
    case_bonuses = config.get("case_bonuses", {})
    case_labels = config.get("case_labels", {})
    comprehensive_levels = config.get("comprehensive_levels", [])
    hard_rule_config = config.get("hard_rule_override", {})

    # 1. Case 判定
    case = classify_case(own_score, exposure_score, contributions, high_threshold)
    case_label = case_labels.get(case, "未知")

    # 2. 硬规则覆盖检查
    has_hard_rule_override = _check_hard_rule_override(
        hard_rule_hits,
        hard_rule_config.get("rules", []),
        hard_rule_config.get("enabled", True),
    )

    # 3. 计算综合分数
    if has_hard_rule_override:
        # 硬规则覆盖：使用 own_risk 的分数和等级
        comprehensive_score = own_score
        comprehensive_level = own_level
        max_component = "own"
        case_bonus = 0
    else:
        # 正常融合
        max_component_score = max(own_score, exposure_score)
        max_component = "own" if own_score >= exposure_score else "exposure"

        # Case bonus
        if case == "A":
            case_bonus = case_bonuses.get("A_both_high", 20)
        elif case == "B":
            case_bonus = case_bonuses.get("B_low_own_high_exposure", 10)
        elif case == "C":
            case_bonus = case_bonuses.get("C_high_own_low_exposure", 0)
        else:
            case_bonus = case_bonuses.get("D_both_low", 0)

        comprehensive_score = max_component_score + case_bonus
        comprehensive_level = _score_to_level(comprehensive_score, comprehensive_levels)

    # 4. 生成 explanation
    explanation = _generate_explanation(
        case, case_label,
        own_score, own_level,
        exposure_score, exposure_level,
        comprehensive_level,
        contributions,
    )

    # 5. 构建 fusion_trace
    formula_parts = [f"max({own_score}, {exposure_score})"]
    if not has_hard_rule_override and case_bonus > 0:
        formula_parts.append(f"+ {case_bonus}")
    formula_str = " + ".join(formula_parts) if len(formula_parts) > 1 else formula_parts[0]
    if not has_hard_rule_override:
        formula_str += f" = {comprehensive_score}"
    else:
        formula_str = f"hard_rule_override({own_score}) = {comprehensive_score}"

    fusion_trace = {
        "own_score": own_score,
        "exposure_score": exposure_score,
        "case_bonus": case_bonus if not has_hard_rule_override else 0,
        "max_component": max_component,
        "formula": formula_str,
        "has_hard_rule_override": has_hard_rule_override,
    }

    # 6. 构建输出
    return {
        "score": comprehensive_score,
        "level": comprehensive_level,
        "case": case,
        "case_label": case_label,
        "explanation": explanation,
        "fusion_trace": fusion_trace,
        "version": config.get("version", "1.0.0"),
        "config_hash": get_comprehensive_config_hash(config),
    }
