@echo off
cd /d "%~dp0.."
"C:\ArchivAgent\kraken_env\Scripts\python.exe" src\ocr_assistant\main.py
if errorlevel 1 pause
