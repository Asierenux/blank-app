@echo off
chcp 65001 >nul
title Diagnostico trafico
rem Doble clic: comprueba la API de trafico del Gobierno Vasco (incidencias y camaras cerca de Vitoria).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo  Primero abre iniciar.bat una vez para preparar el entorno.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m monitor_vitoria probar-trafico
echo.
echo  Haz una captura de esta ventana.
pause
