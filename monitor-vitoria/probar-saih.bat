@echo off
chcp 65001 >nul
title Diagnostico SAIH Ebro
rem Doble clic: comprueba la lectura del embalse de Urrunaga (E028) en la web del SAIH Ebro.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo  Primero abre iniciar.bat una vez para preparar el entorno.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m monitor_vitoria probar-saih E028 --estacion urrunaga
echo.
echo  Haz una captura de esta ventana. Si se ha creado datos\diagnostico_saih.txt, envialo tambien.
pause
