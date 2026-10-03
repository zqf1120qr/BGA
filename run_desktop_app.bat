@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title BGA AI Inspector Launcher

echo ==============================================================
echo       BGA Desktop Inspection System Launcher
echo ==============================================================
echo [*] Searching for available Python environment...

set "PYTHON_EXE="

REM 1. Check local virtual environment (.venv / venv / env)
if exist "%~dp0\.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0\.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%~dp0\venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0\venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%~dp0\env\Scripts\python.exe" set "PYTHON_EXE=%~dp0\env\Scripts\python.exe"

REM 2. Check active shell environment (VIRTUAL_ENV or CONDA_PREFIX)
if not defined PYTHON_EXE if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\python.exe" set "PYTHON_EXE=%VIRTUAL_ENV%\Scripts\python.exe"
if not defined PYTHON_EXE if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" set "PYTHON_EXE=%CONDA_PREFIX%\python.exe"

REM 3. Check common Anaconda / Miniconda install locations
if not defined PYTHON_EXE if exist "D:\Anaconda3\envs\torch\python.exe" set "PYTHON_EXE=D:\Anaconda3\envs\torch\python.exe"
if not defined PYTHON_EXE if exist "D:\Anaconda3\envs\bga-build\python.exe" set "PYTHON_EXE=D:\Anaconda3\envs\bga-build\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\anaconda3\envs\torch\python.exe" set "PYTHON_EXE=%USERPROFILE%\anaconda3\envs\torch\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\miniconda3\envs\torch\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\envs\torch\python.exe"
if not defined PYTHON_EXE if exist "%LOCALAPPDATA%\anaconda3\envs\torch\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\anaconda3\envs\torch\python.exe"
if not defined PYTHON_EXE if exist "%LOCALAPPDATA%\miniconda3\envs\torch\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\miniconda3\envs\torch\python.exe"
if not defined PYTHON_EXE if exist "C:\ProgramData\anaconda3\envs\torch\python.exe" set "PYTHON_EXE=C:\ProgramData\anaconda3\envs\torch\python.exe"
if not defined PYTHON_EXE if exist "C:\ProgramData\miniconda3\envs\torch\python.exe" set "PYTHON_EXE=C:\ProgramData\miniconda3\envs\torch\python.exe"
if not defined PYTHON_EXE if exist "C:\Anaconda3\envs\torch\python.exe" set "PYTHON_EXE=C:\Anaconda3\envs\torch\python.exe"
if not defined PYTHON_EXE if exist "C:\miniconda3\envs\torch\python.exe" set "PYTHON_EXE=C:\miniconda3\envs\torch\python.exe"
if not defined PYTHON_EXE if exist "D:\miniconda3\envs\torch\python.exe" set "PYTHON_EXE=D:\miniconda3\envs\torch\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\anaconda3\python.exe" set "PYTHON_EXE=%USERPROFILE%\anaconda3\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\miniconda3\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\python.exe"
if not defined PYTHON_EXE if exist "C:\ProgramData\anaconda3\python.exe" set "PYTHON_EXE=C:\ProgramData\anaconda3\python.exe"
if not defined PYTHON_EXE if exist "C:\Anaconda3\python.exe" set "PYTHON_EXE=C:\Anaconda3\python.exe"
if not defined PYTHON_EXE if exist "D:\Anaconda3\python.exe" set "PYTHON_EXE=D:\Anaconda3\python.exe"

REM 4. Fallback to system PATH
if not defined PYTHON_EXE (
    for /f "delims=" %%I in ('where python 2^>nul') do (
        if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
    )
)

REM 5. Fallback to py launcher
if not defined PYTHON_EXE (
    where py >nul 2>nul
    if !ERRORLEVEL! equ 0 set "PYTHON_EXE=py"
)

REM 6. Error if no python found
if not defined PYTHON_EXE (
    echo.
    echo ==============================================================
    echo [ERROR] No suitable Python environment found!
    echo ==============================================================
    echo Please make sure Python 3.9 - 3.11 or Anaconda is installed:
    echo  1. Download Python from https://www.python.org or Anaconda
    echo  2. Ensure "Add Python to PATH" is checked during installation
    echo  3. Or create a virtual environment: python -m venv .venv
    echo ==============================================================
    pause
    exit /b 1
)

echo [*] Target Python: "!PYTHON_EXE!"

REM Normalize project root path without trailing slash
set "PROJ_ROOT=%~dp0"
if "%PROJ_ROOT:~-1%"=="\" set "PROJ_ROOT=%PROJ_ROOT:~0,-1%"
set "PYTHONPATH=%PROJ_ROOT%\backend;%PROJ_ROOT%;!PYTHONPATH!"

REM Test mode for automated validation
if "%~1"=="--test" (
    echo [TEST SUCCESS] Python found: !PYTHON_EXE!
    exit /b 0
)

REM 7. Check core dependencies (PySide6)
"!PYTHON_EXE!" -c "import PySide6" >nul 2>nul
if !ERRORLEVEL! neq 0 (
    echo.
    echo [WARNING] PySide6 is not installed in the target Python environment.
    if exist "requirements_desktop.txt" (
        echo [*] Auto-installing dependencies from requirements_desktop.txt...
        "!PYTHON_EXE!" -m pip install -r requirements_desktop.txt
        if !ERRORLEVEL! neq 0 (
            echo [ERROR] Failed to install dependencies.
            pause
            exit /b 1
        )
    ) else (
        echo [ERROR] requirements_desktop.txt not found. Please install PySide6 manually.
        pause
        exit /b 1
    )
)

echo [*] Environment and dependencies verified. Starting application...
echo ==============================================================

REM 8. Launch desktop application
"!PYTHON_EXE!" desktop_app\main.py %*

if !ERRORLEVEL! neq 0 (
    echo.
    echo ==============================================================
    echo [ERROR] Application exited with error code: !ERRORLEVEL!
    echo ==============================================================
    pause
)
