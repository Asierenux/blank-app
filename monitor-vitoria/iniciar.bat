@echo off
chcp 65001 >nul
title Monitor Vitoria-Gasteiz
rem ==================================================================
rem  Doble clic aqui para arrancar el monitor (recogida + panel).
rem  La primera vez prepara Python y las librerias (1-2 minutos).
rem ==================================================================
cd /d "%~dp0"

set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
  python --version >nul 2>&1
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo.
  echo  No encuentro Python. Instalalo desde https://www.python.org/downloads/
  echo  y marca la casilla "Add python.exe to PATH". Luego abre otra vez este archivo.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo  Primera vez: preparando el entorno...
  %PY% -m venv .venv
  if errorlevel 1 goto :error
)

rem Instala las librerias solo si requirements.txt ha cambiado
fc /b requirements.txt ".venv\requisitos-instalados.txt" >nul 2>&1
if errorlevel 1 (
  echo  Instalando librerias, espera un momento...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
  if errorlevel 1 goto :error
  copy /y requirements.txt ".venv\requisitos-instalados.txt" >nul
)

".venv\Scripts\python.exe" -m monitor_vitoria iniciar %*
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo  Algo ha fallado. Haz una captura de esta ventana para revisarlo.
pause
exit /b 1
