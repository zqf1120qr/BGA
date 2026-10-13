@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title BGA 智能工业质检工作站 - 方案 B 一键打包工具

echo ==============================================================
echo        BGA 智能工业质检工作站 - 一键打包构建工具
echo ==============================================================

set "TARGET_PYTHON="

REM 1. 检查环境变量 CONDA_PREFIX
if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" set "TARGET_PYTHON=%CONDA_PREFIX%\python.exe"

REM 2. 检查常用的 Anaconda torch 环境
if not defined TARGET_PYTHON if exist "D:\Anaconda3\envs\torch\python.exe" set "TARGET_PYTHON=D:\Anaconda3\envs\torch\python.exe"
if not defined TARGET_PYTHON if exist "C:\Anaconda3\envs\torch\python.exe" set "TARGET_PYTHON=C:\Anaconda3\envs\torch\python.exe"
if not defined TARGET_PYTHON if exist "%USERPROFILE%\anaconda3\envs\torch\python.exe" set "TARGET_PYTHON=%USERPROFILE%\anaconda3\envs\torch\python.exe"

REM 3. 检查系统默认 python
if not defined TARGET_PYTHON (
    where python >nul 2>&1
    if !ERRORLEVEL! EQU 0 set "TARGET_PYTHON=python"
)

if not defined TARGET_PYTHON (
    echo [!] 错误: 未找到可用的 Python 环境！
    echo 请确保 Anaconda/Conda 的 torch 环境路径正确，或激活环境后再试。
    pause
    exit /b 1
)

echo [*] 正在使用 Python 启动打包引擎: "!TARGET_PYTHON!"
"!TARGET_PYTHON!" "%~dp0packaging\build_binary.py"

if !ERRORLEVEL! EQU 0 (
    echo [*] 打包完成！正在为您打开产物输出目录...
    if exist "%~dp0dist\BGA_AI_Inspector" (
        explorer "%~dp0dist\BGA_AI_Inspector"
    ) else if exist "%~dp0dist\BGA_AI_Inspector_Binary" (
        explorer "%~dp0dist\BGA_AI_Inspector_Binary"
    )
) else (
    echo [!] 打包过程中发生错误，请查看上方输出信息。
)

echo.
pause