"""
企业关联风险智能洞察系统 —— 公共依赖与工具函数。

职责：
- 将项目 src/ 目录加入 sys.path，以便复用 src/risk_tools.py 的查询函数；
- 集中 re-export risk_tools 的 6 个查询函数（API 层唯一的数据访问入口，不写 SQL）；
- 提供 company_id 规范化、企业存在性检查、统一错误码构造等通用工具。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

# ------------------------------------------------------------
# 路径设置：项目根 / src 目录加入 sys.path，供下方 import 使用
# ------------------------------------------------------------

BACKEND_ROOT = Path(__file__).resolve().parents[1]  # backend/
PROJECT_ROOT = BACKEND_ROOT.parent                  # 项目根目录（risk/）
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# noqa: E402 —— 必须在完成 sys.path 设置之后导入
from risk_tools import (  # noqa: E402
    get_business_events,
    get_company_profile,
    get_company_relations,
    get_company_snapshot,
    get_evidence_by_id,
    get_judicial_events,
    search_company,
)

__all__ = [
    "BACKEND_ROOT",
    "PROJECT_ROOT",
    "SRC_DIR",
    "search_company",
    "get_company_profile",
    "get_business_events",
    "get_judicial_events",
    "get_company_relations",
    "get_company_snapshot",
    "get_evidence_by_id",
    "normalize_company_id",
    "company_exists",
    "error_detail",
]

# ------------------------------------------------------------
# 统一错误码
# ------------------------------------------------------------

ERROR_COMPANY_NOT_FOUND = "COMPANY_NOT_FOUND"
ERROR_INTERNAL = "INTERNAL_ERROR"
ERROR_INVALID_KEYWORD = "INVALID_KEYWORD"
ERROR_ANALYSIS_FAILED = "ANALYSIS_FAILED"
ERROR_INVALID_REQUEST = "INVALID_REQUEST"
ERROR_ANALYSIS_NOT_FOUND = "ANALYSIS_NOT_FOUND"
ERROR_TASK_NOT_FOUND = "TASK_NOT_FOUND"
ERROR_TASK_CONFLICT = "TASK_CONFLICT"  # 已有活跃任务
ERROR_EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"
ERROR_TASK_ALREADY_COMPLETED = "TASK_ALREADY_COMPLETED"
ERROR_TASK_ALREADY_FINISHED = "TASK_ALREADY_FINISHED"


def error_detail(code: str, message: str) -> Dict[str, str]:
    """构造统一错误体：{"code": str, "message": str}。"""
    return {"code": code, "message": message}


def normalize_company_id(company_id: str) -> str:
    """
    规范化企业 ID：去首尾空白并转大写。

    与 risk_tools 内部行为保持一致（strip + upper）。
    """
    return company_id.strip().upper()


def company_exists(company_id: str) -> bool:
    """
    判断企业是否存在。

    复用 risk_tools.get_company_profile（返回 None 表示不存在），
    不在 API 层直接查询数据库。
    """
    return get_company_profile(company_id) is not None
