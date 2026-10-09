@echo off
REM Para Airline Manager 4 Bot (modo web o app de escritorio) de forma limpia, cerrando tambien Chrome.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0web_parar.ps1" %*
