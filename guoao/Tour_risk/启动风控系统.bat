@echo off
chcp 65001 >nul
title 风控系统启动中...

echo ============================================
echo         AI 风控系统 - 一键启动
echo ============================================
echo.

cd /d "D:\desktop\Tour_risk"

:: Step 1: 启动 MySQL（Docker）
echo [1/3] 检查 MySQL 数据库...
docker ps --format "{{.Names}}" | findstr "ai_risk_mysql" >nul
if %errorlevel% neq 0 (
    echo MySQL 容器未运行，正在启动...
    cd docker
    docker compose up -d mysql
    cd ..
) else (
    echo MySQL 容器已在运行 ✓
)
echo.

:: Step 2: 等待 MySQL 就绪
echo [2/3] 等待数据库就绪...
:wait_mysql
docker exec ai_risk_mysql mysqladmin ping -uroot -p123321 --silent >nul 2>&1
if %errorlevel% neq 0 (
    timeout /t 2 >nul
    goto wait_mysql
)
echo 数据库已就绪 ✓
echo.

:: Step 3: 启动风控服务
echo [3/3] 启动风控系统服务...
start "" http://localhost:8000
echo.
echo 服务启动中，浏览器即将打开...
echo 如果浏览器未自动打开，请手动访问: http://localhost:8000
echo.
echo ============================================

.venv\Scripts\python.exe run_app.py

pause
