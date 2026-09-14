@echo off
chcp 65001 >nul
title Control de Verificacion - Consulta remota
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
echo   Control de Verificacion - Consulta remota (solo lectura)
echo ============================================================
echo.
echo Requiere tener configurada la carpeta de red en
echo .streamlit\secrets.toml, seccion [copia_red].
echo.
echo Abriendo la aplicacion en el navegador...
echo.
echo NO CIERRES ESTA VENTANA mientras la consultes.
echo Para salir, cierra esta ventana o pulsa Ctrl+C.
echo.

set MDV_MODO_REMOTO=1
streamlit run streamlit_app.py
