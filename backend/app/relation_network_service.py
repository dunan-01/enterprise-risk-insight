"""
企业关联关系网络遍历服务。

从目标企业开始，使用 BFS 遍历所有关联企业，
构建完整的关系网络图。
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any, Dict, List, Set

# 复用 src/risk_tools.py 的查询函数
import sys
from pathlib import Path

# 添加 src 到 sys.path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from risk_tools import get_company_profile, get_company_relations

logger = logging.getLogger("risk-api")

# 安全限制：最大节点数
MAX_NODES = 100


def build_relation_network(
    company_id: str, max_nodes: int = MAX_NODES
) -> Dict[str, Any]:
    """
    构建指定企业的完整关联关系网络。

    从目标企业开始，BFS 遍历所有关联企业，
    直到没有新的关联企业或达到安全限制。

    Args:
        company_id: 目标企业ID
        max_nodes: 最大节点数限制

    Returns:
        {
            "root_company_id": str,
            "nodes": [...],
            "edges": [...],
            "truncated": bool
        }

    Raises:
        ValueError: 当目标企业不存在时
    """
    company_id = company_id.strip().upper()

    # 检查目标企业是否存在
    profile = get_company_profile(company_id)
    if profile is None:
        raise ValueError(f"企业 {company_id} 不存在")

    # 初始化
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    visited_companies: Set[str] = set()
    visited_relations: Set[str] = set()
    queue: deque = deque()

    # 添加根节点
    root_node = {
        "company_id": company_id,
        "company_name": profile.get("company_name", ""),
        "industry": profile.get("industry"),
        "business_status": profile.get("business_status"),
        "depth": 0,
    }
    nodes.append(root_node)
    visited_companies.add(company_id)
    queue.append((company_id, 0))

    truncated = False

    # BFS 遍历
    while queue and len(nodes) < max_nodes:
        current_id, depth = queue.popleft()

        # 获取当前企业的一跳关系
        try:
            relations = get_company_relations(current_id)
        except Exception as exc:
            logger.warning("获取企业 %s 关联关系失败: %s", current_id, exc)
            continue

        for rel in relations:
            relation_id = rel.get("relation_id")
            from_id = rel.get("from_company_id")
            to_id = rel.get("to_company_id")

            # 边去重
            if relation_id in visited_relations:
                continue
            visited_relations.add(relation_id)

            # 添加边
            edge = {
                "relation_id": relation_id,
                "source": from_id,
                "target": to_id,
                "relation_type": rel.get("relation_type"),
                "equity_ratio": rel.get("equity_ratio"),
                "amount": rel.get("amount"),
                "status": rel.get("status"),
            }
            edges.append(edge)

            # 处理目标节点
            target_id = to_id if from_id == current_id else from_id
            if target_id not in visited_companies:
                if len(nodes) >= max_nodes:
                    truncated = True
                    break

                # 获取目标企业信息
                try:
                    target_profile = get_company_profile(target_id)
                except Exception as exc:
                    logger.warning(
                        "获取企业 %s 基本信息失败: %s", target_id, exc
                    )
                    continue

                if target_profile:
                    node = {
                        "company_id": target_id,
                        "company_name": target_profile.get("company_name", ""),
                        "industry": target_profile.get("industry"),
                        "business_status": target_profile.get("business_status"),
                        "depth": depth + 1,
                    }
                    nodes.append(node)
                    visited_companies.add(target_id)
                    queue.append((target_id, depth + 1))

        if truncated:
            break

    return {
        "root_company_id": company_id,
        "nodes": nodes,
        "edges": edges,
        "truncated": truncated,
    }
