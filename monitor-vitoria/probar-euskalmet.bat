@echo off
chcp 65001 >nul
title Diagnostico Euskalmet (Kapildui)
rem Doble clic: comprueba tu clave de Euskalmet y lo que mide la estacion de Kapildui.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo  Primero abre iniciar.bat una vez para preparar el entorno.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m monitor_vitoria probar-euskalmet
echo.
echo  Haz una captura de esta ventana.
pause
