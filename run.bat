@echo off
title Daily News Reporter
echo.
echo  ===================================================
echo   MA and Company Intelligence Reporter
echo  ===================================================
echo.

:: Try PATH first
where python >nul 2>&1
if %errorlevel% == 0 ( set PYEXE=python & goto run )

where py >nul 2>&1
if %errorlevel% == 0 ( set PYEXE=py & goto run )

:: Search common install locations
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    if exist "%%D\python.exe" ( set PYEXE=%%D\python.exe & goto run )
)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\*") do (
    if exist "%%D\python.exe" ( set PYEXE=%%D\python.exe & goto run )
)
for /d %%D in ("C:\Python*") do (
    if exist "%%D\python.exe" ( set PYEXE=%%D\python.exe & goto run )
)
for /d %%D in ("%USERPROFILE%\Anaconda3" "%USERPROFILE%\miniconda3" "C:\ProgramData\Anaconda3") do (
    if exist "%%D\python.exe" ( set PYEXE=%%D\python.exe & goto run )
)

:: Not found
echo  ERROR: Python not found.
echo.
echo  Please install from: https://python.org/downloads
echo  Tick "Add Python to PATH" during install.
echo.
pause
exit /b 1

:run
echo  Found Python: %PYEXE%
echo  Fetching news... (30-60 seconds)
echo.
"%PYEXE%" "%~dp0news_reporter.py"
echo.
pause
