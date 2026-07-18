@echo off
setlocal

pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] IslamAI could not open its project directory.
    exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows.ps1" -Launch %*
set "ISLAMAI_EXIT_CODE=%ERRORLEVEL%"

popd
if not "%ISLAMAI_EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] IslamAI setup or startup failed. Review the message above.
    if not defined CI pause
)

exit /b %ISLAMAI_EXIT_CODE%
