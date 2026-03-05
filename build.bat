@echo off
REM Build Multi-Browser Operator into a single .exe
REM Requires: pip install pyinstaller PyQt5

echo Building Multi-Browser Operator...

pyinstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "MultiBrowserOperator" ^
    --icon NONE ^
    --add-data "src;src" ^
    run.py

if errorlevel 1 (
    echo.
    echo ERROR: Build failed! See output above for details.
    pause
    exit /b 1
)

echo.
echo Build complete. Executable is in dist\MultiBrowserOperator.exe
pause
