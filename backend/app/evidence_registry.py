"""
企业关联风险智能洞察系统 —— Evidence Registry 服务层（V2.0）。

统一证据注册中心，负责：
1. 根据 risk.db 自动加载 business_events、judicial_events、relations
2. 生成 EvidenceRecord 统一数据结构
3. 支持 GET /api/evidence/{evidence_id} 查询
4. 确保报告中的所有 Bxxx/Jxxx/Rxxx 全部经过 Evidence Registry

设计原则：
- 不修改 Risk Harness
- 不修改风险分析逻辑
- 不改变已有报告
- 兼容已有 runs/web/*/report_final.md 和 analysis_result.json
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

# ------------------------------------------------------------
# 数据库路径
# ------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "risk.db"


def _get_connection() -> sqlite3.Connection:
    """创建 SQLite 数据库连接。"""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"找不到数据库文件：{DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    """SQLite Row 转为普通 dict。"""
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    """SQLite Rows 转为 List[dict]。"""
    return [dict(row) for row in rows]


# ------------------------------------------------------------
# EvidenceRecord 数据模型
# ------------------------------------------------------------


class EvidenceRecord:
    """统一证据记录数据结构。

    Attributes:
        id: 证据编号（Bxxx/Jxxx/Rxxx）
        type: 证据类型（business/judicial/relation）
        company_id: 所属企业ID
        company_name: 所属企业名称
        title: 证据标题（人类可读）
        description: 证据描述
        source_table: 数据来源表（business_events/judicial_events/relations）
        data: 原始记录数据
    """

    def __init__(
        self,
        id: str,
        type: str,
        company_id: str,
        company_name: str,
        title: str,
        description: str,
        source_table: str,
        data: Dict[str, Any],
    ):
        self.id = id
        self.type = type
        self.company_id = company_id
        self.company_name = company_name
        self.title = title
        self.description = description
        self.source_table = source_table
        self.data = data

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于 API 响应）。"""
        result = {
            "evidence_id": self.id,
            "evidence_type": self.type,
            "company_id": self.company_id,
            "company_name": self.company_name,
            "title": self.title,
            "description": self.description,
            "source_table": self.source_table,
            "data": self.data,
            "source": self.data.get("source", "simulated"),
        }

        # 关系类型额外字段
        if self.type == "relation":
            result["from_company_id"] = self.data.get("from_company_id")
            result["from_company_name"] = self.data.get("from_company_name")
            result["to_company_id"] = self.data.get("to_company_id")
            result["to_company_name"] = self.data.get("to_company_name")
        else:
            result["from_company_id"] = None
            result["from_company_name"] = None
            result["to_company_id"] = None
            result["to_company_name"] = None

        return result


# ------------------------------------------------------------
# Evidence Registry 核心类
# ------------------------------------------------------------


class EvidenceRegistry:
    """Evidence Registry 单例。

    负责从 risk.db 加载所有证据记录，并提供统一的查询接口。
    """

    _instance: Optional["EvidenceRegistry"] = None

    def __new__(cls) -> "EvidenceRegistry":
        """单例模式。"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache: Dict[str, EvidenceRecord] = {}
            cls._instance._loaded = False
        return cls._instance

    def _ensure_loaded(self) -> None:
        """确保证据数据已加载。"""
        if not self._loaded:
            self._load_all_evidence()
            self._loaded = True

    def _load_all_evidence(self) -> None:
        """从 risk.db 加载所有证据记录。"""
        conn = _get_connection()
        try:
            # 加载 business_events
            self._load_business_events(conn)
            # 加载 judicial_events
            self._load_judicial_events(conn)
            # 加载 relations
            self._load_relations(conn)
        finally:
            conn.close()

    def _load_business_events(self, conn: sqlite3.Connection) -> None:
        """加载 business_events 表的证据记录。"""
        rows = conn.execute(
            """
            SELECT be.*, c.company_name
            FROM business_events AS be
            JOIN companies AS c ON be.company_id = c.company_id
            ORDER BY be.event_id
            """
        ).fetchall()

        for row in rows:
            data = _row_to_dict(row)
            company_name = data.pop("company_name", "")
            event_id = data.get("event_id", "")

            # 生成标题和描述
            title = self._generate_business_title(data)
            description = self._generate_business_description(data)

            record = EvidenceRecord(
                id=event_id,
                type="business",
                company_id=data.get("company_id", ""),
                company_name=company_name,
                title=title,
                description=description,
                source_table="business_events",
                data=data,
            )
            self._cache[event_id] = record

    def _load_judicial_events(self, conn: sqlite3.Connection) -> None:
        """加载 judicial_events 表的证据记录。"""
        rows = conn.execute(
            """
            SELECT je.*, c.company_name
            FROM judicial_events AS je
            JOIN companies AS c ON je.company_id = c.company_id
            ORDER BY je.event_id
            """
        ).fetchall()

        for row in rows:
            data = _row_to_dict(row)
            company_name = data.pop("company_name", "")
            event_id = data.get("event_id", "")

            # 生成标题和描述
            title = self._generate_judicial_title(data)
            description = self._generate_judicial_description(data)

            record = EvidenceRecord(
                id=event_id,
                type="judicial",
                company_id=data.get("company_id", ""),
                company_name=company_name,
                title=title,
                description=description,
                source_table="judicial_events",
                data=data,
            )
            self._cache[event_id] = record

    def _load_relations(self, conn: sqlite3.Connection) -> None:
        """加载 relations 表的证据记录。"""
        rows = conn.execute(
            """
            SELECT
                r.*,
                cf.company_name AS from_company_name,
                ct.company_name AS to_company_name
            FROM relations AS r
            JOIN companies AS cf ON r.from_company_id = cf.company_id
            JOIN companies AS ct ON r.to_company_id = ct.company_id
            ORDER BY r.relation_id
            """
        ).fetchall()

        for row in rows:
            data = _row_to_dict(row)
            from_name = data.pop("from_company_name", "")
            to_name = data.pop("to_company_name", "")
            relation_id = data.get("relation_id", "")

            # 设置公司名称
            data["from_company_name"] = from_name
            data["to_company_name"] = to_name

            # 生成标题和描述
            title = self._generate_relation_title(data, from_name, to_name)
            description = self._generate_relation_description(data, from_name, to_name)

            record = EvidenceRecord(
                id=relation_id,
                type="relation",
                company_id=data.get("from_company_id", ""),
                company_name=from_name,
                title=title,
                description=description,
                source_table="relations",
                data=data,
            )
            self._cache[relation_id] = record

    # ------------------------------------------------------------
    # 标题和描述生成器
    # ------------------------------------------------------------

    def _generate_business_title(self, data: Dict[str, Any]) -> str:
        """生成工商事件标题。"""
        event_type = data.get("event_type", "未知事件")
        return f"{event_type}"

    def _generate_business_description(self, data: Dict[str, Any]) -> str:
        """生成工商事件描述。"""
        parts = []
        if data.get("event_date"):
            parts.append(f"日期: {data['event_date']}")
        if data.get("old_value") and data.get("new_value"):
            parts.append(f"{data['old_value']} → {data['new_value']}")
        elif data.get("new_value"):
            parts.append(f"变更为: {data['new_value']}")
        if data.get("detail"):
            parts.append(data["detail"])
        return "；".join(parts) if parts else data.get("event_type", "")

    def _generate_judicial_title(self, data: Dict[str, Any]) -> str:
        """生成司法事件标题。"""
        case_type = data.get("case_type", "未知案件")
        role = data.get("role", "")
        if role:
            return f"{case_type}（{role}）"
        return f"{case_type}"

    def _generate_judicial_description(self, data: Dict[str, Any]) -> str:
        """生成司法事件描述。"""
        parts = []
        if data.get("case_number"):
            parts.append(f"案号: {data['case_number']}")
        if data.get("court"):
            parts.append(f"法院: {data['court']}")
        if data.get("amount"):
            parts.append(f"金额: ¥{data['amount']:,.0f}")
        if data.get("filing_date"):
            parts.append(f"立案: {data['filing_date']}")
        if data.get("status"):
            parts.append(f"状态: {data['status']}")
        return "；".join(parts) if parts else data.get("case_type", "")

    def _generate_relation_title(
        self, data: Dict[str, Any], from_name: str, to_name: str
    ) -> str:
        """生成关系标题。"""
        relation_type = data.get("relation_type", "关联关系")
        return f"{relation_type}: {from_name} → {to_name}"

    def _generate_relation_description(
        self, data: Dict[str, Any], from_name: str, to_name: str
    ) -> str:
        """生成关系描述。"""
        parts = []
        if data.get("equity_ratio"):
            parts.append(f"股权比例: {data['equity_ratio'] * 100:.1f}%")
        if data.get("amount"):
            parts.append(f"金额: ¥{data['amount']:,.0f}")
        if data.get("relation_detail"):
            parts.append(data["relation_detail"])
        if data.get("start_date"):
            parts.append(f"起始: {data['start_date']}")
        return "；".join(parts) if parts else data.get("relation_type", "")

    # ------------------------------------------------------------
    # 公共查询接口
    # ------------------------------------------------------------

    def get_evidence(self, evidence_id: str) -> Optional[EvidenceRecord]:
        """根据 Evidence ID 查询证据记录。

        Args:
            evidence_id: 证据编号（Bxxx/Jxxx/Rxxx）

        Returns:
            EvidenceRecord 或 None（不存在时）
        """
        self._ensure_loaded()
        eid = evidence_id.strip().upper()
        return self._cache.get(eid)

    def get_evidence_dict(self, evidence_id: str) -> Optional[Dict[str, Any]]:
        """根据 Evidence ID 查询证据记录（字典格式）。

        Args:
            evidence_id: 证据编号（Bxxx/Jxxx/Rxxx）

        Returns:
            字典格式的证据记录或 None（不存在时）
        """
        record = self.get_evidence(evidence_id)
        if record is None:
            return None
        return record.to_dict()

    def list_all_evidence_ids(self) -> List[str]:
        """列出所有证据 ID。"""
        self._ensure_loaded()
        return sorted(self._cache.keys())

    def get_evidence_by_company(self, company_id: str) -> List[EvidenceRecord]:
        """获取指定企业的所有证据记录。"""
        self._ensure_loaded()
        cid = company_id.strip().upper()
        return [r for r in self._cache.values() if r.company_id == cid]

    def reload(self) -> None:
        """重新加载证据数据（用于数据更新后）。"""
        self._cache.clear()
        self._loaded = False
        self._ensure_loaded()


# ------------------------------------------------------------
# 便捷函数
# ------------------------------------------------------------


def get_evidence_by_id(evidence_id: str) -> Optional[Dict[str, Any]]:
    """根据 Evidence ID 查询证据记录（字典格式）。

    这是主要的查询入口，供 api.py 调用。

    Args:
        evidence_id: 证据编号（Bxxx/Jxxx/Rxxx）

    Returns:
        字典格式的证据记录或 None（不存在时）
    """
    registry = EvidenceRegistry()
    return registry.get_evidence_dict(evidence_id)


def get_all_evidence_ids() -> List[str]:
    """列出所有证据 ID。"""
    registry = EvidenceRegistry()
    return registry.list_all_evidence_ids()


def reload_evidence_registry() -> None:
    """重新加载证据数据。"""
    registry = EvidenceRegistry()
    registry.reload()


# ------------------------------------------------------------
# 本地测试
# ------------------------------------------------------------

if __name__ == "__main__":
    import json

    # 测试所有证据 ID
    all_ids = get_all_evidence_ids()
    print(f"Total evidence IDs: {len(all_ids)}")
    print(f"IDs: {all_ids[:20]}...")  # 只显示前20个

    # 测试特定证据
    test_ids = ["B009", "B010", "B011", "J007", "R006", "R010"]
    for eid in test_ids:
        result = get_evidence_by_id(eid)
        if result:
            print(f"\n{eid}:")
            print(f"  type: {result['evidence_type']}")
            print(f"  company_id: {result['company_id']}")
            print(f"  company_name: {result['company_name']}")
            print(f"  title: {result['title']}")
        else:
            print(f"\n{eid}: NOT FOUND")
