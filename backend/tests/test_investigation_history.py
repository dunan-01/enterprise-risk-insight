"""
AI 调查网络历史加载测试。

验证分析完成后，调查网络仍然可以查看。
"""

import sys
from pathlib import Path

# 添加 backend 目录到 sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.analysis_service import load_latest_analysis, _find_task_id_for_company


def test_load_latest_analysis():
    """测试 load_latest_analysis 函数。"""
    print("=" * 60)
    print("Testing load_latest_analysis")
    print("=" * 60)

    # 测试有历史分析的企业
    companies_with_analysis = ['C004', 'C005', 'C006', 'C007', 'C009', 'C010']

    for cid in companies_with_analysis:
        try:
            result = load_latest_analysis(cid)
            task_id = result.get('task_id')
            status = result.get('status')
            risk_level = result.get('risk_level')
            print(f"✓ {cid}: task_id={task_id}, status={status}, risk={risk_level}")
        except Exception as e:
            print(f"✗ {cid}: {e}")

    print()


def test_find_task_id():
    """测试 _find_task_id_for_company 函数。"""
    print("=" * 60)
    print("Testing _find_task_id_for_company")
    print("=" * 60)

    # 测试所有企业
    companies = ['C001', 'C002', 'C003', 'C004', 'C005', 'C006', 'C007', 'C008', 'C009', 'C010']

    for cid in companies:
        task_id = _find_task_id_for_company(cid)
        status = "✓" if task_id else "⚠"
        print(f"{status} {cid}: task_id={task_id}")

    print()


def test_investigation_network_api():
    """测试调查网络 API。"""
    import urllib.request
    import json

    print("=" * 60)
    print("Testing Investigation Network API")
    print("=" * 60)

    base_url = "http://localhost:8000"

    # 测试有任务的企业
    companies_with_tasks = ['C006', 'C009', 'C010']

    for cid in companies_with_tasks:
        try:
            # 获取最新分析
            with urllib.request.urlopen(f"{base_url}/api/companies/{cid}/analysis/latest", timeout=10) as resp:
                data = json.loads(resp.read().decode())
                task_id = data.get('task_id')
                if task_id:
                    # 获取调查网络
                    with urllib.request.urlopen(f"{base_url}/api/analysis/tasks/{task_id}/investigation-network", timeout=10) as net_resp:
                        net_data = json.loads(net_resp.read().decode())
                        nodes = len(net_data.get('nodes', []))
                        edges = len(net_data.get('edges', []))
                        print(f"✓ {cid}: task_id={task_id}, nodes={nodes}, edges={edges}")
                else:
                    print(f"⚠ {cid}: no task_id in analysis result")
        except Exception as e:
            print(f"✗ {cid}: {e}")

    print()


if __name__ == "__main__":
    test_load_latest_analysis()
    test_find_task_id()
    test_investigation_network_api()

    print("=" * 60)
    print("✓ All tests completed!")
    print("=" * 60)
