@echo off
rem Doble clic para subir los carruseles 50-54 a GitHub.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0subir-lote-50-54.ps1"
echo.
pause
