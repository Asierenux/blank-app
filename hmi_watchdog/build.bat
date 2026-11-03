@echo off
REM Genera dist\HMIWatchdog.exe (un único ejecutable, sin necesidad de Python en el PC de la HMI)
cd /d "%~dp0"
python -m pip install -r requirements-dev.txt || goto :error
python -m PyInstaller --noconfirm --onefile --windowed --name HMIWatchdog hmi_watchdog.py || goto :error
echo.
echo OK: ejecutable generado en %~dp0dist\HMIWatchdog.exe
pause
exit /b 0
:error
echo ERROR durante la compilacion
pause
exit /b 1
