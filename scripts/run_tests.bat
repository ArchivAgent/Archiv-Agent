@echo off
cd /d "%~dp0.."
"C:\ArchivAgent\kraken_env\Scripts\python.exe" -m pytest -q
if errorlevel 1 pause
