@echo off
REM ──────────────────────────────────────────────────────────────────────
REM build.bat — Build PassLock standalone executable on Windows.
REM
REM Prerequisites:
REM   pip install pyinstaller
REM
REM Usage:
REM   build.bat
REM ──────────────────────────────────────────────────────────────────────

echo === PassLock Build Script (Windows) ===

REM Ensure pyinstaller is installed
where pyinstaller >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

echo Building standalone executable...
pyinstaller passlock.spec --clean --noconfirm

echo.
echo Build complete!
echo    Executable: dist\PassLock.exe
echo.
echo To create an installer, use Inno Setup or NSIS:
echo    https://jrsoftware.org/isinfo.php
echo    https://nsis.sourceforge.io/
pause
