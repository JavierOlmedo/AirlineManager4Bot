@echo off
REM Abre el panel web de Airline Manager 4 Bot y, si no esta en marcha, arranca el bot en modo web
REM (sin ventana) en esta consola. Para pararlo: scripts\web_parar.bat.
title Airline Manager 4 Bot web
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0web.ps1" %*
