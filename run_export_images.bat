@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title X-ray AI Inspector - 客户端风格质检图像批量导出

echo ==============================================================
echo       X-ray AI Inspector 客户端质检图像导出工具
echo ==============================================================
echo [*] 正在定位可用 Python 运行环境...

set "PYTHON_EXE="

REM 1. 优先检测本项目推荐 Anaconda torch 环境
if not defined PYTHON_EXE if exist "D:\Anaconda3\envs\torch\python.exe" set "PYTHON_EXE=D:\Anaconda3\envs\torch\python.exe"

REM 2. 检测本地虚拟环境 (.venv / venv / env)
if not defined PYTHON_EXE if exist "%~dp0\.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0\.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%~dp0\venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0\venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%~dp0\env\Scripts\python.exe" set "PYTHON_EXE=%~dp0\env\Scripts\python.exe"

REM 3. 检测当前终端激活的虚拟环境 (VIRTUAL_ENV 或 CONDA_PREFIX)
if not defined PYTHON_EXE if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\python.exe" set "PYTHON_EXE=%VIRTUAL_ENV%\Scripts\python.exe"
if not defined PYTHON_EXE if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" set "PYTHON_EXE=%CONDA_PREFIX%\python.exe"

REM 4. 检测其他常见 Anaconda / Miniconda 路径
if not defined PYTHON_EXE if exist "%USERPROFILE%\anaconda3\envs\torch\python.exe" set "PYTHON_EXE=%USERPROFILE%\anaconda3\envs\torch\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\miniconda3\envs\torch\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\envs\torch\python.exe"
if not defined PYTHON_EXE if exist "C:\Anaconda3\envs\torch\python.exe" set "PYTHON_EXE=C:\Anaconda3\envs\torch\python.exe"
if not defined PYTHON_EXE if exist "C:\ProgramData\anaconda3\envs\torch\python.exe" set "PYTHON_EXE=C:\ProgramData\anaconda3\envs\torch\python.exe"
if not defined PYTHON_EXE if exist "D:\Anaconda3\python.exe" set "PYTHON_EXE=D:\Anaconda3\python.exe"

REM 5. 回退至系统环境变量中的 python
if not defined PYTHON_EXE (
    for /f "delims=" %%I in ('where python 2^>nul') do (
        if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
    )
)

if not defined PYTHON_EXE (
    echo.
    echo [错误] 未找到可用的 Python 运行环境！
    echo 请确认已安装 Python 3.9-3.11 或 Anaconda，并安装相应依赖。
    pause
    exit /b 1
)

echo [*] 当前激活 Python: "!PYTHON_EXE!"
echo.

set "PROJ_ROOT=%~dp0"
if "%PROJ_ROOT:~-1%"=="\" set "PROJ_ROOT=%PROJ_ROOT:~0,-1%"
set "PYTHONPATH=%PROJ_ROOT%\backend;%PROJ_ROOT%;!PYTHONPATH!"

"!PYTHON_EXE!" "%~dp0export_inspected_images.py" %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo [提示] 脚本执行过程中发生异常，错误代码: %ERRORLEVEL%
    pause
) else (
    echo.
    echo [提示] 执行完毕，按任意键退出...
    pause >nul
)
