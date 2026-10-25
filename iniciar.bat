@echo off
REM Arranca el editor de materias extrañas. La primera vez instala lo necesario (requiere internet).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno de Python...
    py -3 -m venv .venv || python -m venv .venv
    if errorlevel 1 (
        echo No se encuentra Python. Instalalo desde https://www.python.org/downloads/ marcando "Add python.exe to PATH".
        pause
        exit /b 1
    )
    echo Instalando dependencias...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || (pause & exit /b 1)
)
echo Abriendo la aplicacion en el navegador (cierra esta ventana para pararla)...
".venv\Scripts\python.exe" -m streamlit run streamlit_app.py --server.maxUploadSize 2000 --browser.gatherUsageStats false
pause
