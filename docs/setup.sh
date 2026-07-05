#!/usr/bin/env bash
# ============================================================
# AI 军团 — 评委一键部署脚本（Linux / macOS）
# 用法：bash docs/setup.sh
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  AI 军团 — 电力项目立项审核系统"
echo "  评委部署脚本"
echo "========================================"
echo ""

# ── 1. 检查 Python ──
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "❌ 未找到 Python，请先安装 Python 3.10+"
    echo "   https://www.python.org/downloads/"
    exit 1
fi

echo "✓ Python: $($PYTHON --version 2>&1)"

# ── 2. 创建虚拟环境 ──
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "→ 创建虚拟环境..."
    $PYTHON -m venv "$VENV_DIR"
fi
echo "✓ 虚拟环境: $VENV_DIR"

# ── 3. 激活并安装依赖 ──
source "$VENV_DIR/bin/activate" 2>/dev/null || source "$VENV_DIR/Scripts/activate" 2>/dev/null
echo "→ 安装 Python 依赖..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✓ 依赖安装完成"

# ── 4. 配置 API Key ──
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
    else
        echo "DEEPSEEK_API_KEY=your_key_here" > .env
    fi
fi

# 检查 key 是否已填
if grep -q "your_key_here" .env 2>/dev/null || grep -q "^DEEPSEEK_API_KEY=$" .env 2>/dev/null; then
    echo ""
    echo "⚠️  请配置 DeepSeek API Key："
    echo "   1. 访问 https://platform.deepseek.com/api_keys 获取 key"
    echo "   2. 编辑 .env 文件，将 DEEPSEEK_API_KEY=your_key_here 替换为真实 key"
    echo "   3. 重新运行本脚本"
    echo ""
    read -rp "→ 或直接在此输入 API Key（按 Enter 跳过，稍后手动编辑 .env）: " USER_KEY
    if [ -n "$USER_KEY" ]; then
        # 用 sed 替换占位符
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|DEEPSEEK_API_KEY=.*|DEEPSEEK_API_KEY=$USER_KEY|" .env
        else
            sed -i "s|DEEPSEEK_API_KEY=.*|DEEPSEEK_API_KEY=$USER_KEY|" .env
        fi
        echo "✓ API Key 已写入 .env"
    fi
else
    echo "✓ API Key 已配置"
fi

# ── 5. 启动服务 ──
echo ""
echo "========================================"
echo "  启动 Web 服务..."
echo "  公网 URL 将在启动后显示"
echo "  （形如 https://xxxxxxxxxxxx.gradio.live）"
echo "========================================"
echo ""

python -m src.aiarmy.web

# 脚本结束。Gradio 会保持运行，Ctrl+C 停止。
