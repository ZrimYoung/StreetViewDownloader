@echo off
echo =============================
echo Building StreetViewDownloader.exe...
echo =============================

:: Check if required files exist
if not exist GUI-RUN.py (
    echo =============================
    echo ERROR: GUI-RUN.py not found!
    echo =============================
    pause
    exit /b
)
if not exist work-ui.exe (
    echo =============================
    echo ERROR: work-ui.exe not found!
    echo =============================
    pause
    exit /b
)
if not exist configuration.ini (
    echo =============================
    echo WARNING: configuration.ini not found! Default will be generated at runtime.
    echo =============================
)
if not exist icon.ico (
    echo =============================
    echo WARNING: icon.ico not found! Using default PyInstaller icon.
    echo =============================
)

:: Run PyInstaller to build GUI-RUN.py
pyinstaller ^
 --noconsole ^
 --add-data "work-ui.exe;." ^
 --add-data "configuration.ini;." ^
 --icon=icon.ico ^
 --name "StreetViewDownloader" ^
 GUI-RUN.py

echo.
if exist dist\\StreetViewDownloader\\StreetViewDownloader.exe (
    echo =============================
    echo  Build successful! EXE located at:
    echo dist\\StreetViewDownloader\\StreetViewDownloader.exe
    echo =============================
) else (
    echo =============================
    echo  Build failed.
    echo =============================
    pause
    exit /b
)

:: Cleanup intermediate build files
echo =============================
echo Cleaning up intermediate files...
echo =============================
rmdir /s /q build
del /q StreetViewDownloader.spec

echo Done.
pause