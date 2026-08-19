import sys
import json
from pathlib import Path


# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 让 Python 可以 import src
sys.path.insert(0, str(PROJECT_ROOT))


from src.risk_tools import (
    search_company,
    get_company_profile,
    get_business_events,
    get_judicial_events,
    get_company_relations,
)


def output(data):
    print(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        )
    )


def main():
    if len(sys.argv) < 3:
        output({
            "error": "参数不足",
            "usage": "python risk_bridge.py <action> <value>"
        })
        sys.exit(1)

    action = sys.argv[1]
    value = sys.argv[2]

    try:

        if action == "search_company":
            result = search_company(value)

        elif action == "get_company_profile":
            result = get_company_profile(value)

        elif action == "get_business_events":
            result = get_business_events(value)

        elif action == "get_judicial_events":
            result = get_judicial_events(value)

        elif action == "get_company_relations":
            result = get_company_relations(value)

        else:
            result = {
                "error": f"未知 action：{action}"
            }

        output(result)

    except Exception as e:
        output({
            "error": str(e),
            "action": action,
            "value": value
        })
        sys.exit(1)


if __name__ == "__main__":
    main()