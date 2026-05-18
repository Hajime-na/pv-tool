@echo off
setlocal
cd /d "%~dp0"

set "PY=python"
python --version >nul 2>nul
if errorlevel 1 (
  py -3 --version >nul 2>nul
  if errorlevel 1 (
    echo Python 3.10 or newer was not found.
    where winget >nul 2>nul
    if errorlevel 1 (
      echo Install Python manually, then run this file again.
      pause
      exit /b 1
    )
    set /p INSTALL_PY="Install Python 3.12 with winget now? [y/N]: "
    if /i "%INSTALL_PY%"=="y" (
      winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
      echo Close this window, then run start_pv_tool.bat again.
      pause
      exit /b 0
    )
    echo Python install skipped.
    pause
    exit /b 1
  ) else (
    set "PY=py -3"
  )
)

%PY% "%~dp0setup_env.py" --interactive
if errorlevel 1 (
  echo Environment setup failed.
  pause
  exit /b 1
)

start "PV Production Tool Server" %PY% "%~dp0pv_tool_server.py"
timeout /t 1 >nul
start "" "http://127.0.0.1:8767/pv_project_tool.html"

echo PV Production Tool started.
echo URL: http://127.0.0.1:8767/pv_project_tool.html
pause
