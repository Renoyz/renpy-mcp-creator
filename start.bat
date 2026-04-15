@echo off
chcp 65001 >nul
echo ===========================================
echo   RenPy MCP Creator - 启动器
echo ===========================================

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python。请先安装 Python 3.11 或更高版本。
    pause
    exit /b 1
)

echo [1/2] 检查依赖...
python -m pip show renpy-mcp-creator >nul 2>&1
if errorlevel 1 (
    echo    正在安装依赖（首次启动需要 1-2 分钟）...
    python -m pip install -e . >nul 2>&1
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络连接。
        pause
        exit /b 1
    )
)

echo [2/2] 启动服务...
python -m renpy_mcp.cli.app start

pause
