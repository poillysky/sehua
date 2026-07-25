@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "SEARCH=%ROOT%next-web"

echo ========================================
echo   sehua-search 独立启动
echo ========================================
echo.

if not exist "%SEARCH%\package.json" (
  echo [错误] 未找到搜索前端：
  echo   %SEARCH%
  pause
  exit /b 1
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

echo 启动搜索前端 :3010
echo DB 见 next-web\.env.local（默认 192.168.2.38:5436）
start "sehua-search" /D "%SEARCH%" cmd /k "npm run dev"

echo.
echo ----------------------------------------
echo  搜索前端  http://localhost:3010
echo  窗口名    sehua-search（关闭即停）
echo ----------------------------------------
echo.
pause
endlocal
