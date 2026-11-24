@echo off
REM Genera DibujadorPerfiles.exe en la carpeta dist\ (ejecutar en Windows con Python 3.11+)
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-build.txt
pyinstaller --noconfirm --onefile --windowed --name DibujadorPerfiles ^
  --add-data "ejemplos;ejemplos" --add-data "perfil_app/fuentes;fuentes" ^
  --exclude-module streamlit ^
  app.py
echo.
echo Listo: dist\DibujadorPerfiles.exe
pause
