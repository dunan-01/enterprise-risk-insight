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
# Tool 6：根据 Evidence ID 查询原始事实（V1.4 新增）
# ============================================================

def get_business_event_by_id(evidence_id: str) -> Optional[Dict[str, Any]]:
    """
    根据 evidence_id（Bxxx）查询 business_events 原始记录。

    返回 dict 或 None（不存在时）。
    """
    evidence_id = evidence_id.strip().upper()
    if not evidence_id.startswith("B"):
        return None

    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT be.*, c.company_name
            FROM business_events AS be
            JOIN companies AS c ON be.company_id = c.company_id
            WHERE be.event_id = ?
            """,
            (evidence_id,),
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def get_judicial_event_by_id(evidence_id: str) -> Optional[Dict[str, Any]]:
    """
    根据 evidence_id（Jxxx）查询 judicial_events 原始记录。

    返回 dict 或 None（不存在时）。
    """
    evidence_id = evidence_id.strip().upper()
    if not evidence_id.startswith("J"):
        return None

    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT je.*, c.company_name
            FROM judicial_events AS je
            JOIN companies AS c ON je.company_id = c.company_id
            WHERE je.event_id = ?
            """,
            (evidence_id,),
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def get_relation_by_id(evidence_id: str) -> Optional[Dict[str, Any]]:
    """
    根据 evidence_id（Rxxx）查询 relations 原始记录。

    返回 dict 或 None（不存在时）。
    """
    evidence_id = evidence_id.strip().upper()
    if not evidence_id.startswith("R"):
        return None

    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT
                r.*,
                cf.company_name AS from_company_name,
                ct.company_name AS to_company_name
            FROM relations AS r
            JOIN companies AS cf ON r.from_company_id = cf.company_id
            JOIN companies AS ct ON r.to_company_id = ct.company_id
            WHERE r.relation_id = ?
            """,
            (evidence_id,),
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


# ============================================================
# Tool 7：查询企业舆情事件（P/F/H 新增）
# ============================================================

def get_public_opinion_events(company_id: str) -> List[Dict[str, Any]]:
    """
    查询企业所有舆情事件。按发布时间从新到旧排序。
    """

    company_id = company_id.strip().upper()

    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM public_opinion_events
            WHERE company_id = ?
            ORDER BY publish_date DESC, event_id
            """,
            (company_id,),
        ).fetchall()

        return rows_to_dicts(rows)

    finally:
        conn.close()


def get_financial_reports(company_id: str) -> List[Dict[str, Any]]:
    """
    查询企业所有财务报告。按期间排序。

    附加确定性计算指标（安全除法，分母为 0 或 None 时返回 None）：
    - debt_ratio: total_liabilities / total_assets（资产负债率）
    - current_ratio: current_assets / current_liabilities（流动比率）
    - net_margin: net_profit / revenue（净利率）
    - revenue_yoy: (current_revenue - previous_revenue) / previous_revenue（营业收入同比增长率）
    - profit_yoy: (current_profit - previous_profit) / previous_profit（净利润同比增长率）
    """

    company_id = company_id.strip().upper()

    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM financial_reports
            WHERE company_id = ?
            ORDER BY period ASC, report_id
            """,
            (company_id,),
        ).fetchall()

        reports = rows_to_dicts(rows)

        # 附加计算指标
        for i, report in enumerate(reports):
            # 安全除法辅助函数
            def _safe_div(
                numerator: Optional[float], denominator: Optional[float]
            ) -> Optional[float]:
                if numerator is None or denominator is None:
                    return None
                if denominator == 0:
                    return None
                return numerator / denominator

            report["debt_ratio"] = _safe_div(
                report.get("total_liabilities"), report.get("total_assets")
            )
            report["current_ratio"] = _safe_div(
                report.get("current_assets"), report.get("current_liabilities")
            )
            report["net_margin"] = _safe_div(
                report.get("net_profit"), report.get("revenue")
            )

            # 同比指标：第一期没有同比数据
            if i == 0:
                report["revenue_yoy"] = None
                report["profit_yoy"] = None
            else:
                prev = reports[i - 1]
                prev_revenue = prev.get("revenue")
                curr_revenue = report.get("revenue")
                if prev_revenue is None or curr_revenue is None:
                    report["revenue_yoy"] = None
                elif prev_revenue == 0:
                    report["revenue_yoy"] = None
                else:
                    report["revenue_yoy"] = (curr_revenue - prev_revenue) / prev_revenue

                prev_profit = prev.get("net_profit")
                curr_profit = report.get("net_profit")
                if prev_profit is None or curr_profit is None:
                    report["profit_yoy"] = None
                elif prev_profit == 0:
                    report["profit_yoy"] = None
                else:
                    report["profit_yoy"] = (curr_profit - prev_profit) / prev_profit

        return reports

    finally:
        conn.close()


def get_recruitment_events(company_id: str) -> List[Dict[str, Any]]:
    """
    查询企业所有招聘事件。按发布时间从新到旧排序。
    """

    company_id = company_id.strip().upper()

    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM recruitment_events
            WHERE company_id = ?
            ORDER BY publish_date DESC, event_id
            """,
            (company_id,),
        ).fetchall()

        return rows_to_dicts(rows)

    finally:
        conn.close()


# ============================================================
# Tool 8：根据 Evidence ID 查询 P/F/H 原始记录
# ============================================================

def get_public_opinion_event_by_id(evidence_id: str) -> Optional[Dict[str, Any]]:
    """
    根据 evidence_id（Pxxx）查询 public_opinion_events 原始记录。

    返回 dict 或 None（不存在时）。
    """
    evidence_id = evidence_id.strip().upper()
    if not evidence_id.startswith("P"):
        return None

    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT pe.*, c.company_name
            FROM public_opinion_events AS pe
            JOIN companies AS c ON pe.company_id = c.company_id
            WHERE pe.event_id = ?
            """,
            (evidence_id,),
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def get_financial_report_by_id(evidence_id: str) -> Optional[Dict[str, Any]]:
    """
    根据 evidence_id（Fxxx）查询 financial_reports 原始记录。

    返回 dict 或 None（不存在时）。
    """
    evidence_id = evidence_id.strip().upper()
    if not evidence_id.startswith("F"):
        return None

    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT fr.*, c.company_name
            FROM financial_reports AS fr
            JOIN companies AS c ON fr.company_id = c.company_id
            WHERE fr.report_id = ?
            """,
            (evidence_id,),
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def get_recruitment_event_by_id(evidence_id: str) -> Optional[Dict[str, Any]]:
    """
    根据 evidence_id（Hxxx）查询 recruitment_events 原始记录。

    返回 dict 或 None（不存在时）。
    """
    evidence_id = evidence_id.strip().upper()
    if not evidence_id.startswith("H"):
        return None

    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT re.*, c.company_name
            FROM recruitment_events AS re
            JOIN companies AS c ON re.company_id = c.company_id
            WHERE re.event_id = ?
            """,
            (evidence_id,),
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def get_evidence_by_id(evidence_id: str) -> Optional[Dict[str, Any]]:
    """
    根据 Evidence ID 查询确定性原始事实。

    支持六类 Evidence：
    - Bxxx → business_events（工商/经营事件）
    - Jxxx → judicial_events（司法事件）
    - Rxxx → relations（企业关系）
    - Pxxx → public_opinion_events（舆情事件）
    - Fxxx → financial_reports（财务报告）
    - Hxxx → recruitment_events（招聘事件）

    返回统一外层结构：
    {
        "evidence_id": "J008",
        "evidence_type": "judicial",
        "company_id": "C007",
        "company_name": "xxx",
        "data": { ... 原始记录 ... },
        "source": "simulated"
    }

    如果 Evidence 不存在，返回 None。

    注意：本函数只做确定性数据库查询，
    不计算风险分数、不判断风险等级、不调用 LLM。
    """
    evidence_id = evidence_id.strip().upper()
    if not evidence_id:
        return None

    prefix = evidence_id[:1] if evidence_id else ""

    if prefix == "B":
        row = get_business_event_by_id(evidence_id)
        if row is None:
            return None
        company_name = row.pop("company_name", None)
        return {
            "evidence_id": evidence_id,
            "evidence_type": "business",
            "company_id": row.get("company_id"),
            "company_name": company_name,
            "data": row,
            "source": row.get("source", "simulated"),
        }

    elif prefix == "J":
        row = get_judicial_event_by_id(evidence_id)
        if row is None:
            return None
        company_name = row.pop("company_name", None)
        return {
            "evidence_id": evidence_id,
            "evidence_type": "judicial",
            "company_id": row.get("company_id"),
            "company_name": company_name,
            "data": row,
            "source": row.get("source", "simulated"),
        }

    elif prefix == "R":
        row = get_relation_by_id(evidence_id)
        if row is None:
            return None
        from_name = row.pop("from_company_name", None)
        to_name = row.pop("to_company_name", None)
        # 关系记录没有单一 company_id，用 from 作为主企业
        return {
            "evidence_id": evidence_id,
            "evidence_type": "relation",
            "company_id": row.get("from_company_id"),
            "company_name": from_name,
            "from_company_id": row.get("from_company_id"),
            "from_company_name": from_name,
            "to_company_id": row.get("to_company_id"),
            "to_company_name": to_name,
            "data": row,
            "source": row.get("source", "simulated"),
        }

    elif prefix == "P":
        row = get_public_opinion_event_by_id(evidence_id)
        if row is None:
            return None
        company_name = row.pop("company_name", None)
        return {
            "evidence_id": evidence_id,
            "evidence_type": "public_opinion",
            "company_id": row.get("company_id"),
            "company_name": company_name,
            "data": row,
            "source": row.get("source", "simulated"),
        }

    elif prefix == "F":
        row = get_financial_report_by_id(evidence_id)
        if row is None:
            return None
        company_name = row.pop("company_name", None)
        return {
            "evidence_id": evidence_id,
            "evidence_type": "financial",
            "company_id": row.get("company_id"),
            "company_name": company_name,
            "data": row,
            "source": row.get("source", "simulated"),
        }

    elif prefix == "H":
        row = get_recruitment_event_by_id(evidence_id)
        if row is None:
            return None
        company_name = row.pop("company_name", None)
        return {
            "evidence_id": evidence_id,
            "evidence_type": "recruitment",
            "company_id": row.get("company_id"),
            "company_name": company_name,
            "data": row,
            "source": row.get("source", "simulated"),
        }

    return None


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