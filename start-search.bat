@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "SEARCH=%ROOT%next-web"
set "SCRAPE=%ROOT%scrape-web"

echo ========================================
echo   sehua-search 独立启动
echo   next-web :3010 + scrape-web :9209
echo ========================================
echo.

if not exist "%SEARCH%\package.json" (
  echo [错误] 未找到搜索前端：
  echo   %SEARCH%
  pause
  exit /b 1
)

if not exist "%SCRAPE%\package.json" (
  echo [错误] 未找到刮削服务：
  echo   %SCRAPE%
  pause
  exit /b 1
)

if not exist "%SEARCH%\node_modules\" (
  echo [提示] next-web 尚未安装依赖，正在 npm install ...
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

if not exist "%SCRAPE%\node_modules\" (
  echo [提示] scrape-web 尚未安装依赖，正在 npm install ...
  pushd "%SCRAPE%"
  call npm install
  if errorlevel 1 (
    echo [错误] scrape-web npm install 失败
    popd
    pause
    exit /b 1
  )
  popd
  echo.
)

echo [1/2] 启动刮削服务 scrape-web  :9209
echo       DB 见 scrape-web\.env（本地常见 192.168.2.38:5435/ed2k）
start "sehua-scrape" /D "%SCRAPE%" cmd /k "npm run dev"

timeout /t 2 /nobreak >nul

echo [2/2] 启动搜索前端 next-web    :3010
echo       DB 见 next-web\.env.local（本地常见 192.168.2.38:5435/ed2k）
start "sehua-search" /D "%SEARCH%" cmd /k "npm run dev"

echo.
echo ----------------------------------------
echo  搜索前端    http://localhost:3010
echo  刮削服务    http://127.0.0.1:9209
echo  窗口名      sehua-scrape / sehua-search（关闭即停）
echo  约定说明    docs\本地开发约定.md
echo ----------------------------------------
echo.
pause
endlocal
