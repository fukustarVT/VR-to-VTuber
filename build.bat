@echo off
cd /d "%~dp0"
echo This builds the app as one executable.
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm "VR to VTuber.spec"
echo.
echo File stored in: dist\VR to VTuber.exe
pause
