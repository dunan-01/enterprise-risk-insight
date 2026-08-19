import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "risk.db"


def get_connection():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"找不到数据库文件：{DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_company_profile(conn, company_id):
    cursor = conn.execute(
        """
        SELECT *
        FROM companies
        WHERE company_id = ?
        """,
        (company_id,),
    )
    return cursor.fetchone()


def get_business_events(conn, company_id):
    cursor = conn.execute(
        """
        SELECT *
        FROM business_events
        WHERE company_id = ?
        ORDER BY event_date DESC
        """,
        (company_id,),
    )
    return cursor.fetchall()


def get_judicial_events(conn, company_id):
    cursor = conn.execute(
        """
        SELECT *
        FROM judicial_events
        WHERE company_id = ?
        ORDER BY filing_date DESC
        """,
        (company_id,),
    )
    return cursor.fetchall()


def get_company_relations(conn, company_id):
    cursor = conn.execute(
        """
        SELECT
            r.*,
            cf.company_name AS from_company_name,
            ct.company_name AS to_company_name
        FROM relations r
        JOIN companies cf
            ON r.from_company_id = cf.company_id
        JOIN companies ct
            ON r.to_company_id = ct.company_id
        WHERE r.from_company_id = ?
           OR r.to_company_id = ?
        ORDER BY r.relation_id
        """,
        (company_id, company_id),
    )
    return cursor.fetchall()


def print_company_profile(company):
    print("\n" + "=" * 70)
    print("企业基本信息")
    print("=" * 70)

    print(f"企业ID：      {company['company_id']}")
    print(f"企业名称：    {company['company_name']}")
    print(f"信用代码：    {company['credit_code'] or '-'}")
    print(f"法定代表人：  {company['legal_rep'] or '-'}")
    print(f"注册资本：    {company['reg_capital'] or '-'} 万元")
    print(f"实缴资本：    {company['paid_capital'] or '-'} 万元")
    print(f"成立日期：    {company['established_date'] or '-'}")
    print(f"企业类型：    {company['company_type'] or '-'}")
    print(f"所属行业：    {company['industry'] or '-'}")
    print(f"经营状态：    {company['business_status'] or '-'}")
    print(f"注册地址：    {company['reg_address'] or '-'}")
    print(f"经营范围：    {company['business_scope'] or '-'}")


def print_business_events(events):
    print("\n" + "=" * 70)
    print(f"经营事件，共 {len(events)} 条")
    print("=" * 70)

    if not events:
        print("暂无经营事件")
        return

    for event in events:
        print(
            f"\n[{event['event_id']}] "
            f"{event['event_type']} | "
            f"{event['event_date'] or '-'}"
        )

        if event["old_value"] or event["new_value"]:
            print(
                f"  变更：{event['old_value'] or '-'}"
                f" → {event['new_value'] or '-'}"
            )

        if event["detail"]:
            print(f"  详情：{event['detail']}")

        if event["penalty_amount"] is not None:
            print(f"  处罚金额：{event['penalty_amount']:,.2f} 元")

        print(f"  状态：{event['status'] or '-'}")
        print(f"  来源：{event['source'] or '-'}")


def print_judicial_events(events):
    print("\n" + "=" * 70)
    print(f"司法事件，共 {len(events)} 条")
    print("=" * 70)

    if not events:
        print("暂无司法事件")
        return

    for event in events:
        print(
            f"\n[{event['event_id']}] "
            f"{event['case_type']} | "
            f"{event['filing_date'] or '-'}"
        )

        print(f"  案号：{event['case_number'] or '-'}")
        print(f"  法院：{event['court'] or '-'}")
        print(f"  案由：{event['cause'] or '-'}")
        print(f"  企业角色：{event['role'] or '-'}")

        if event["amount"] is not None:
            print(f"  涉案金额：{event['amount']:,.2f} 元")

        print(f"  案件状态：{event['status'] or '-'}")

        if event["result"]:
            print(f"  结果：{event['result']}")

        print(f"  来源：{event['source'] or '-'}")


def print_relations(relations, company_id):
    print("\n" + "=" * 70)
    print(f"企业关系，共 {len(relations)} 条")
    print("=" * 70)

    if not relations:
        print("暂无企业关联关系")
        return

    for relation in relations:
        if relation["from_company_id"] == company_id:
            direction = "→"
            other_id = relation["to_company_id"]
            other_name = relation["to_company_name"]
        else:
            direction = "←"
            other_id = relation["from_company_id"]
            other_name = relation["from_company_name"]

        print(
            f"\n[{relation['relation_id']}] "
            f"{company_id} {direction} "
            f"{other_id} {other_name}"
        )

        print(f"  关系类型：{relation['relation_type']}")

        if relation["equity_ratio"] is not None:
            print(
                f"  股权比例："
                f"{relation['equity_ratio'] * 100:.2f}%"
            )

        if relation["amount"] is not None:
            print(f"  涉及金额：{relation['amount']:,.2f} 元")

        if relation["relation_detail"]:
            print(f"  详情：{relation['relation_detail']}")

        print(f"  状态：{relation['status'] or '-'}")


def analyze_company(company_id):
    company_id = company_id.strip().upper()

    conn = get_connection()

    try:
        company = get_company_profile(conn, company_id)

        if company is None:
            print(f"\n未找到企业：{company_id}")
            return

        business_events = get_business_events(conn, company_id)
        judicial_events = get_judicial_events(conn, company_id)
        relations = get_company_relations(conn, company_id)

        print_company_profile(company)
        print_business_events(business_events)
        print_judicial_events(judicial_events)
        print_relations(relations, company_id)

        print("\n" + "=" * 70)
        print("查询完成")
        print("=" * 70)

    finally:
        conn.close()


def main():
    if len(sys.argv) < 2:
        print("用法：")
        print("  python demo.py C001")
        print("")
        print("示例：")
        print("  python demo.py C002")
        print("  python demo.py C007")
        sys.exit(1)

    company_id = sys.argv[1]
    analyze_company(company_id)


if __name__ == "__main__":
    main()