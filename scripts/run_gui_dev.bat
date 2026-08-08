@echo off
cd /d "%~dp0.."
set PYTHONPATH=%CD%\src\backend;%CD%\src
"C:\ArchivAgent\kraken_env\Scripts\python.exe" src\archivagent\main.py
if errorlevel 1 pause
