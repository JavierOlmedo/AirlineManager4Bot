@echo off
REM Lleva el codigo de este equipo a la Raspberry y reinicia alli los bots (ver desplegar_pi.ps1).
title Airline Manager 4 Bot - desplegar en la Raspberry
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0desplegar_pi.ps1" %*
pause
