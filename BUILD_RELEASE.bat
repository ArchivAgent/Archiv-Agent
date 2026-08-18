@echo off
chcp 65001 >nul
title ArchivAgent 7.1 RC19 - geprüfter Release-Builder
cd /d "%~dp0"

"C:\ArchivAgent\kraken_env\Scripts\python.exe" build_release.py
set "BUILD_CODE=%ERRORLEVEL%"

echo.
if "%BUILD_CODE%"=="0" (
    echo BUILD ERFOLGREICH.
    pause
    exit /b 0
)

if "%BUILD_CODE%"=="2" (
    echo BUILD ABGEBROCHEN.
    pause
    exit /b 2
)

echo BUILD FEHLGESCHLAGEN.
pause
exit /b 1
