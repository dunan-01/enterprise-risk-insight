#!/bin/bash
# 同时启动后端和前端服务

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS_DIR="$PROJECT_ROOT/scripts"

echo "=========================================="
echo " 企业关联风险智能洞察系统 - 全栈启动"
echo "=========================================="
echo ""

# 启动后端
bash "$SCRIPTS_DIR/start_backend.sh" &
BACKEND_JOB=$!

# 等待后端启动
sleep 5

# 启动前端
bash "$SCRIPTS_DIR/start_frontend.sh" &
FRONTEND_JOB=$!

echo ""
echo "=========================================="
echo " 系统启动完成"
echo "=========================================="
echo " 后端: http://localhost:8000"
echo " 前端: http://localhost:5173"
echo " API 文档: http://localhost:8000/docs"
echo "=========================================="
echo ""
echo "按 Ctrl+C 停止所有服务"

# 等待任意子进程退出
wait
