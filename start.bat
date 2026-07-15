@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "ADMIN=%ROOT%frontend\admin"
set "SEARCH=%ROOT%next-web"
set "PY=%BACKEND%\.venv\Scripts\python.exe"

echo ========================================
echo   sehuatang 一键启动
echo ========================================
echo.

if not exist "%PY%" (
  echo [错误] 未找到后端虚拟环境：
  echo   %PY%
  echo 请先在 backend 目录创建 .venv 并安装依赖。
  pause
  exit /b 1
)

if not exist "%ADMIN%\package.json" (
  echo [错误] 未找到管理前端：
  echo   %ADMIN%
  pause
  exit /b 1
)

if not exist "%SEARCH%\package.json" (
  echo [错误] 未找到搜索前端：
  echo   %SEARCH%
  pause
  exit /b 1
)

if not exist "%ADMIN%\node_modules\" (
  echo [提示] 管理前端尚未安装依赖，正在 npm install ...
  pushd "%ADMIN%"
  call npm install
  if errorlevel 1 (
    echo [错误] admin npm install 失败
    popd
    pause
    exit /b 1
  )
  popd
  echo.
)

if not exist "%SEARCH%\node_modules\" (
  echo [提示] 搜索前端尚未安装依赖，正在 npm install ...
  pushd "%SEARCH%"
  call npm install
  if errorlevel 1 (
    echo [错误] next-web npm install 失败
    popd
    pause
    exit /b 1
  )
  popd
  echo.
)

echo [1/3] 启动后端 API        :8080
start "sehuatang-backend" /D "%BACKEND%" cmd /k ".venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload"

timeout /t 2 /nobreak >nul

echo [2/3] 启动管理后台 Admin  :8081
start "sehuatang-admin" /D "%ADMIN%" cmd /k "npm run dev"

timeout /t 1 /nobreak >nul

echo [3/3] 启动搜索前端 Search :3008
start "sehuatang-search" /D "%SEARCH%" cmd /k "npm run dev"

echo.
echo ----------------------------------------
echo  后端健康检查  http://127.0.0.1:8080/health
echo  管理后台      http://localhost:8081
echo  搜索前端      http://localhost:3008
echo  默认账号      admin / admin123 （仅管理后台）
echo ----------------------------------------
echo  已打开三个控制台窗口；关闭对应窗口即可停止。
echo.
pause
endlocal
