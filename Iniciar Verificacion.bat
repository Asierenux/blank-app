@echo off
chcp 65001 >nul
title Control de Verificacion de Carcasas/Bandages
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] No se ha instalado la aplicacion todavia en este PC.
    echo.
    echo Haz doble clic primero en "Instalar (solo la primera vez).bat"
    echo y espera a que termine antes de usar este fichero.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo ============================================================
echo   Control de Verificacion de Carcasas/Bandages
echo ============================================================
echo.
echo Abriendo la aplicacion en el navegador...
echo.
echo NO CIERRES ESTA VENTANA mientras uses la aplicacion.
echo Para salir, cierra esta ventana o pulsa Ctrl+C.
echo.

streamlit run streamlit_app.py
