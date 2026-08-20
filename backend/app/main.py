"""
企业关联风险智能洞察系统 —— FastAPI 应用入口。

- 创建 FastAPI 实例，注册 CORS 中间件（允许所有来源 *）
- 注册 /api 路由与 /health 健康检查
- 全局异常兜底：未预期异常统一返回 500 INTERNAL_ERROR，不抛裸异常
- 请求体校验失败（Pydantic RequestValidationError）统一返回
  400 + {"detail": {"code": "INVALID_REQUEST", "message": ...}}
- 支持两种启动方式（默认端口 8000，可用环境变量 PORT 覆盖）：
    1. cd backend && .venv/bin/python -m app.main
    2. cd backend && .venv/bin/uvicorn app.main:app --port 8000

V1.1 新增功能：
- 企业关联关系网络图 API（BFS 遍历）
- AI 风险报告 PDF 导出
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import router
from .deps import ERROR_INTERNAL, ERROR_INVALID_REQUEST, error_detail
from .models import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("risk-api")

app = FastAPI(
    title="企业关联风险智能洞察系统 API",
    description=(
        "第一阶段：只读查询接口，封装 src/risk_tools.py 查询函数。"
        "第二阶段：POST /api/analysis 风险分析接口，真实调用 Risk Harness"
        "（opencode headless）完成企业风险调查。"
        "第四阶段（V1.1）：企业关联关系网络图 API、AI 风险报告 PDF 导出。"
    ),
    version="1.1.0",
)

# CORS：允许所有来源，为后续前端联调准备
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    请求体/参数校验失败 → 400 + 统一错误格式。

    覆盖 POST /api/analysis 的 company_id 缺失 / 为空等情况。
    """
    errors = exc.errors()
    first = errors[0] if errors else {}
    loc = ".".join(str(p) for p in first.get("loc", []))
    msg = first.get("msg", "参数校验失败")
    return JSONResponse(
        status_code=400,
        content={
            "detail": error_detail(
                ERROR_INVALID_REQUEST, f"请求参数非法：{loc} {msg}"
            )
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    全局兜底异常处理。

    路由中主动抛出的 HTTPException 由 FastAPI 自带处理器处理，
    不会走到这里；此处仅兜底未预期异常，统一返回 500 INTERNAL_ERROR。
    """
    if isinstance(exc, HTTPException):
        # 防御性处理：避免业务错误被误转为 500
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    logger.exception(
        "未处理异常: %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": error_detail(ERROR_INTERNAL, f"服务器内部错误：{exc}")},
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="健康检查",
)
def health() -> HealthResponse:
    """服务健康检查。"""
    return HealthResponse(status="ok")


def _default_port() -> int:
    """读取 PORT 环境变量，默认 8000。"""
    try:
        return int(os.environ.get("PORT", "8000"))
    except ValueError:
        return 8000


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=_default_port(), reload=False)
