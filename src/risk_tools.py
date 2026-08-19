import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


# ------------------------------------------------------------
# 数据库路径
#
# 项目结构默认：
#
# enterprise-risk-harness/
# ├── risk.db
# └── src/
#     └── risk_tools.py
# ------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "risk.db"


def get_connection() -> sqlite3.Connection:
    """
    创建 SQLite 数据库连接。
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"找不到数据库文件：{DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    """
    SQLite Row 转为普通 dict。
    这样后续可以直接交给 Agent / JSON 使用。
    """
    if row is None:
        return None

    return dict(row)


def rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    """
    SQLite Rows 转为 List[dict]。
    """
    return [dict(row) for row in rows]


# ============================================================
# Tool 1：搜索企业
# ============================================================

def search_company(keyword: str) -> List[Dict[str, Any]]:
    """
    根据企业ID、企业名称或统一社会信用代码搜索企业。

    示例：
        search_company("C001")
        search_company("华辰")
        search_company("SYN-C001")
    """

    keyword = keyword.strip()

    if not keyword:
        return []

    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT
                company_id,
                company_name,
                credit_code,
                legal_rep,
                industry,
                business_status,
                data_type
            FROM companies
            WHERE company_id = ?
               OR credit_code = ?
               OR company_name LIKE ?
            ORDER BY company_id
            """,
            (
                keyword.upper(),
                keyword,
                f"%{keyword}%",
            ),
        ).fetchall()

        return rows_to_dicts(rows)

    finally:
        conn.close()


# ============================================================
# Tool 2：查询企业基本信息
# ============================================================

def get_company_profile(company_id: str) -> Optional[Dict[str, Any]]:
    """
    查询指定企业完整基本信息。

    参数：
        company_id: 企业ID，例如 C001

    返回：
        dict
        如果企业不存在则返回 None
    """

    company_id = company_id.strip().upper()

    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT *
            FROM companies
            WHERE company_id = ?
            """,
            (company_id,),
        ).fetchone()

        return row_to_dict(row)

    finally:
        conn.close()


# ============================================================
# Tool 3：查询企业经营事件
# ============================================================

def get_business_events(company_id: str) -> List[Dict[str, Any]]:
    """
    查询企业所有经营事件。

    包括：
    - 法定代表人变更
    - 股东变更
    - 经营异常
    - 行政处罚
    - 地址变更
    - 注册资本变更
    等。

    按事件时间从新到旧排序。
    """

    company_id = company_id.strip().upper()

    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM business_events
            WHERE company_id = ?
            ORDER BY event_date DESC, event_id
            """,
            (company_id,),
        ).fetchall()

        return rows_to_dicts(rows)

    finally:
        conn.close()


# ============================================================
# Tool 4：查询企业司法事件
# ============================================================

def get_judicial_events(company_id: str) -> List[Dict[str, Any]]:
    """
    查询企业所有司法事件。

    包括：
    - 被执行人
    - 失信被执行人
    - 限制消费令
    - 裁判文书
    - 开庭公告
    - 股权冻结
    等。

    注意：
    role 字段非常重要，
    Agent 后续需要根据原告、被告、被执行人等角色进行判断。
    """

    company_id = company_id.strip().upper()

    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM judicial_events
            WHERE company_id = ?
            ORDER BY filing_date DESC, event_id
            """,
            (company_id,),
        ).fetchall()

        return rows_to_dicts(rows)

    finally:
        conn.close()


# ============================================================
# Tool 5：查询企业关联关系
# ============================================================

def get_company_relations(company_id: str) -> List[Dict[str, Any]]:
    """
    查询指定企业所有直接关联关系。

    同时查询：
    - 企业作为关系发起方的关系
    - 企业作为关系接收方的关系

    返回结果中额外附带：
    - from_company_name
    - to_company_name

    注意：
    这里只查询一跳关系。
    后续 Agent 是否继续调查关联企业，
    由 Agent 自己决定。
    """

    company_id = company_id.strip().upper()

    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT
                r.*,
                cf.company_name AS from_company_name,
                ct.company_name AS to_company_name
            FROM relations AS r

            JOIN companies AS cf
              ON r.from_company_id = cf.company_id

            JOIN companies AS ct
              ON r.to_company_id = ct.company_id

            WHERE r.from_company_id = ?
               OR r.to_company_id = ?

            ORDER BY r.relation_id
            """,
            (company_id, company_id),
        ).fetchall()

        return rows_to_dicts(rows)

    finally:
        conn.close()


# ============================================================
# 辅助 Tool：一次获取企业自身全部信息
# ============================================================

def get_company_snapshot(company_id: str) -> Dict[str, Any]:
    """
    获取企业自身的一次性数据快照。

    注意：
    这里只包含目标企业自身数据和一跳关系，
    不会自动继续调查关联企业。

    这点很重要：
    后续我们希望由 Agent 自己决定：
    “是否需要继续调查 C002 / C003 / C009？”
    """

    company_id = company_id.strip().upper()

    profile = get_company_profile(company_id)

    if profile is None:
        return {
            "found": False,
            "company_id": company_id,
            "message": f"未找到企业 {company_id}",
        }

    return {
        "found": True,
        "company_id": company_id,
        "profile": profile,
        "business_events": get_business_events(company_id),
        "judicial_events": get_judicial_events(company_id),
        "relations": get_company_relations(company_id),
    }


# ============================================================
# 本地测试
# ============================================================

if __name__ == "__main__":
    import json

    result = get_company_snapshot("C001")

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )