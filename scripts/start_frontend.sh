#!/bin/bash
# 启动前端开发服务（Vite）
# 默认端口：5173

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
PORT="${PORT:-5173}"

echo "=========================================="
echo " 企业关联风险智能洞察系统 - 前端启动"
echo "=========================================="

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo "错误：找不到 Node.js"
    echo "请先安装 Node.js (https://nodejs.org/)"
    exit 1
fi

# 检查 node_modules
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "安装前端依赖..."
    cd "$FRONTEND_DIR"
    npm install
fi

# 杀掉已有进程
lsof -ti:$PORT 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

echo "启动前端开发服务 (端口: $PORT)..."
cd "$FRONTEND_DIR"
npx vite --port $PORT --host &
FRONTEND_PID=$!

# 等待启动
sleep 5

# 健康检查
if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/" | grep -q "200"; then
    echo "✓ 前端启动成功！"
    echo "  地址: http://localhost:$PORT"
    echo "  PID: $FRONTEND_PID"
else
    echo "✗ 前端启动失败，请检查日志"
    exit 1
fi
