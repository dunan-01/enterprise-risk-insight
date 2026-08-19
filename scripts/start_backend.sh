#!/bin/bash
# 启动后端服务（FastAPI + uvicorn）
# 默认端口：8000

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"
PORT="${PORT:-8000}"

echo "=========================================="
echo " 企业关联风险智能洞察系统 - 后端启动"
echo "=========================================="

# 检查虚拟环境
if [ ! -f "$VENV_PYTHON" ]; then
    echo "错误：找不到 Python 虚拟环境 $VENV_PYTHON"
    echo "请先创建虚拟环境："
    echo "  cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

# 检查依赖
echo "检查后端依赖..."
"$VENV_PYTHON" -c "import fastapi, uvicorn" 2>/dev/null || {
    echo "安装后端依赖..."
    "$VENV_PYTHON" -m pip install -r "$BACKEND_DIR/requirements.txt" -q
}

# 杀掉已有进程
lsof -ti:$PORT 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

echo "启动后端服务 (端口: $PORT)..."
cd "$BACKEND_DIR"
"$VENV_PYTHON" -m app.main &
BACKEND_PID=$!

# 等待启动
sleep 3

# 健康检查
if curl -s "http://localhost:$PORT/health" | grep -q '"status":"ok"'; then
    echo "✓ 后端启动成功！"
    echo "  地址: http://localhost:$PORT"
    echo "  文档: http://localhost:$PORT/docs"
    echo "  PID: $BACKEND_PID"
else
    echo "✗ 后端启动失败，请检查日志"
    exit 1
fi
