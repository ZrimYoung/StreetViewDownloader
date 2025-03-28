@echo off
echo =============================
echo Building work-ui.exe...
echo =============================

:: Build work-ui.py as a console executable
pyinstaller --console --name work-ui work-ui.py

echo.
echo Build complete: dist\\work-ui\\work-ui.exe

:: Clean up intermediate build files
echo Cleaning up build files...
rmdir /s /q build
del /q work-ui.spec

:: Copy EXE to current directory
echo Copying work-ui.exe to current directory...
copy /Y dist\\work-ui\\work-ui.exe .

echo Done. Only dist\\work-ui\\work-ui.exe and local copy are kept.
pause