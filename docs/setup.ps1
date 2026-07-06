# ============================================================
# AI 军团 — 评委一键部署脚本（Windows PowerShell）
# 用法：powershell -ExecutionPolicy Bypass -File docs/setup.ps1
# ============================================================
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
Set-Location $ProjectDir

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI 军团 — 电力项目立项审核系统" -ForegroundColor Cyan
Write-Host "  评委部署脚本 (Windows)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. 检查 Python ──
$pythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pythonCmd = "python3"
} else {
    Write-Host "❌ 未找到 Python，请先安装 Python 3.10+" -ForegroundColor Red
    Write-Host "   https://www.python.org/downloads/"
    exit 1
}

$pyVer = & $pythonCmd --version 2>&1
Write-Host "✓ Python: $pyVer"

# ── 2. 创建虚拟环境 ──
$VenvDir = ".venv"
if (-not (Test-Path $VenvDir)) {
    Write-Host "→ 创建虚拟环境..."
    & $pythonCmd -m venv $VenvDir
}
Write-Host "✓ 虚拟环境: $VenvDir"

# ── 3. 激活并安装依赖 ──
$ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
. $ActivateScript
Write-Host "→ 安装 Python 依赖..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
Write-Host "✓ 依赖安装完成"

# ── 4. 配置 API Key ──
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
    } else {
        "DEEPSEEK_API_KEY=sk-your-key-here" | Out-File -Encoding utf8 ".env"
    }
}

$envContent = Get-Content ".env" -Raw
if ($envContent -match "your_key_here" -or $envContent -notmatch "DEEPSEEK_API_KEY=sk-") {
    Write-Host ""
    Write-Host "⚠️  请配置 DeepSeek API Key：" -ForegroundColor Yellow
    Write-Host "   1. 访问 https://platform.deepseek.com/api_keys 获取 key"
    Write-Host "   2. 编辑 .env 文件，将 DEEPSEEK_API_KEY=your_key_here 替换为真实 key"
    Write-Host "   3. 重新运行本脚本"
    Write-Host ""
    $userKey = Read-Host "→ 或直接在此输入 API Key（按 Enter 跳过）"
    if ($userKey) {
        $newContent = $envContent -replace "DEEPSEEK_API_KEY=.*", "DEEPSEEK_API_KEY=$userKey"
        $newContent | Out-File -Encoding utf8 ".env"
        Write-Host "✓ API Key 已写入 .env"
    }
} else {
    Write-Host "✓ API Key 已配置"
}

# ── 5. 启动服务 ──
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  启动 Web 服务..." -ForegroundColor Cyan
Write-Host "  公网 URL 将在启动后显示" -ForegroundColor Cyan
Write-Host "  （公网域名，需自行配置内网穿透）" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

python -m src.aiarmy.web
