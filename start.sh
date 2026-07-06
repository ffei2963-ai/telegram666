#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  TG Cloud Controller - 启动脚本"
echo "========================================"

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

if [ -z "$TG_BOT_TOKEN" ]; then
    echo ""
    echo "[错误] 未配置 Bot Token！"
    echo ""
    echo "请执行以下步骤："
    echo "  1. cp .env.example .env"
    echo "  2. 编辑 .env 文件，填入:"
    echo "     - TG_BOT_TOKEN (必填)"
    echo "     - DEEPSEEK_API_KEY (可选)"
    echo "     - TG_ADMIN_IDS (可选)"
    echo ""
    exit 1
fi

ENV_FILE="$SCRIPT_DIR/.env"

# Check if running in Docker
if [ -f /.dockerenv ]; then
    echo "[信息] 检测到 Docker 环境"
else
    if ! python3 -c "import python_telegram_bot" 2>/dev/null; then
        echo "[信息] 安装 Python 依赖..."
        pip3 install -r requirements.txt -q
    fi
fi

# Ensure data directories exist
mkdir -p "$SCRIPT_DIR/data/sessions" "$SCRIPT_DIR/data/uploads"

echo "[信息] Bot Token: ${TG_BOT_TOKEN:0:8}..."
echo "[信息] DeepSeek API: ${DEEPSEEK_API_KEY:+已配置}${DEEPSEEK_API_KEY:-未配置}"
echo "[信息] 管理员 IDs: ${TG_ADMIN_IDS:-无限制}"
echo "[信息] 并发数: ${MAX_CONCURRENT_ACCOUNTS:-5}"
echo ""

echo "[启动] 正在启动 TG Cloud Controller..."
exec python3 main.py
