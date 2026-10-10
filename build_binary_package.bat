@echo off
chcp 65001 >nul
title BGA 智能工业质检工作站 - 方案 B 一键打包工具

echo ==============================================================
echo        🌟 BGA 智能工业质检工作站 - 一键打包构建工具
echo ==============================================================

set "TARGET_PYTHON=D:\Anaconda3\envs\torch\python.exe"

if exist "%TARGET_PYTHON%" (
    goto RUN_BUILD
)

:: 尝试使用当前环境 python
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "TARGET_PYTHON=python"
    goto RUN_BUILD
)

echo [!] 错误: 未找到可用的 Python 环境！
echo 请确保 Anaconda/Conda 的 torch 环境路径正确，或激活环境后再试。
pause
exit /b 1

:RUN_BUILD
echo [*] 正在使用 Python 启动打包引擎: "%TARGET_PYTHON%"
"%TARGET_PYTHON%" "%~dp0packaging\build_binary.py"

if %ERRORLEVEL% EQU 0 (
    echo [*] 打包完成！正在为您打开产物输出目录...
    explorer "%~dp0dist\BGA_AI_Inspector_Binary"
) else (
    echo [!] 打包过程中发生错误，请查看上方输出信息。
)

echo.
pause
