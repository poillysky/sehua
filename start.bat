@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "ADMIN=%ROOT%frontend\admin"
set "PY=%BACKEND%\.venv\Scripts\python.exe"

echo ========================================
echo   sehua 一键启动（API + 管理）
echo   搜索请另开 start-search.bat
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

echo [1/2] 启动后端 API        :8080
echo       DB  192.168.2.38:5433/ed2k
start "sehua-api" /D "%BACKEND%" cmd /k ".venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload"

timeout /t 2 /nobreak >nul

echo [2/2] 启动管理后台 Admin  :8081
start "sehua-admin" /D "%ADMIN%" cmd /k "npm run dev"

echo.
echo ----------------------------------------
echo  后端健康检查  http://127.0.0.1:8080/health
echo  管理后台      http://localhost:8081
echo  数据库        192.168.2.38:5433 / ed2k
echo  默认账号      admin / admin123
echo ----------------------------------------
echo  窗口：sehua-api / sehua-admin（关闭即停）
echo  搜索前端请运行 start-search.bat
echo.
pause
endlocal
