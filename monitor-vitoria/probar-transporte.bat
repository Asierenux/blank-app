@echo off
chcp 65001 >nul
title Diagnostico autobuses y tranvia
rem Doble clic: comprueba los datos en tiempo real de Tuvisa y del tranvia.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo  Primero abre iniciar.bat una vez para preparar el entorno.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m monitor_vitoria probar-transporte
echo.
echo  Haz una captura de esta ventana.
pause
