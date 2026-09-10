@echo off
chcp 65001 >nul
title Instalando - Control de Verificacion
cd /d "%~dp0"

echo ============================================================
echo   INSTALACION - Control de Verificacion de Carcasas/Bandages
echo ============================================================
echo.
echo Esto solo hay que hacerlo UNA VEZ en este PC.
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set PYTHON=py
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set PYTHON=python
    ) else (
        echo [ERROR] No se ha encontrado Python instalado en este PC.
        echo.
        echo Descarga e instala Python desde https://www.python.org/downloads/
        echo IMPORTANTE: durante la instalacion, marca la casilla
        echo "Add python.exe to PATH" antes de pulsar Instalar.
        echo.
        echo Cuando lo tengas instalado, vuelve a ejecutar este fichero.
        pause
        exit /b 1
    )
)

echo Python encontrado: %PYTHON%
echo.
echo Creando el entorno de la aplicacion (esto puede tardar 1-2 minutos)...
%PYTHON% -m venv .venv

call .venv\Scripts\activate.bat

echo.
echo Instalando los componentes necesarios...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Algo ha fallado durante la instalacion. Revisa el mensaje de arriba.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   INSTALACION COMPLETADA
echo ============================================================
echo.
echo A partir de ahora, para abrir la aplicacion haz doble clic en:
echo    "Iniciar Verificacion.bat"
echo.
echo Puedes crear un acceso directo de ese fichero en el Escritorio.
echo.
pause
