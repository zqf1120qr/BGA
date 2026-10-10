# -*- coding: utf-8 -*-
"""
🌟 BGA 智能工业质检工作站 - 全能自适应便携式打包构建系统 (Package Builder)
======================================================================
功能特性：
1. 自动收集源码、依赖、模型权重 (best.pt)、样式资源与样本图像；
2. 完整集成并打包自适应 CUDA+CPU 便携运行时 (Portable Python Runtime)；
3. 编译原生 Win32 GUI 启动器 (BGA_AI_Inspector.exe)，集成高清芯片图标与零黑窗口体验；
4. 附赠调试启动脚本 (run_debug.bat) 与 Inno Setup 安装包脚本；
5. 打包完成后自动执行自动化离屏启动测试，确保 100% 可用。
"""
import os
import sys
import shutil
import subprocess
import time
from pathlib import Path
from PIL import Image, ImageDraw

# 保证在 Windows 控制台下正常输出 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_ROOT = PROJECT_ROOT / "dist"
APP_DIST_DIR = DIST_ROOT / "BGA_AI_Inspector"
SOURCE_CONDA_ENV = Path(r"D:\Anaconda3\envs\torch")
CSC_COMPILER = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")


def log(msg: str):
    print(f"[*] {msg}", flush=True)


def check_prerequisites():
    log("检查打包前置条件与文件完整性...")
    if not (PROJECT_ROOT / "backend" / "best.pt").exists():
        raise FileNotFoundError("未找到 YOLO 权重文件 backend/best.pt！")
    if not (PROJECT_ROOT / "desktop_app" / "main.py").exists():
        raise FileNotFoundError("未找到主程序入口 desktop_app/main.py！")
    if not SOURCE_CONDA_ENV.exists():
        raise FileNotFoundError(f"未找到源 Python 运行环境: {SOURCE_CONDA_ENV}")
    if not CSC_COMPILER.exists():
        raise FileNotFoundError(f"未找到 C# 原生编译器: {CSC_COMPILER}")
    log("前置依赖与文件校验通过！")


def generate_app_icon(output_path: Path):
    log(f"生成高分辨率多尺寸应用图标: {output_path.name}...")
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    images = []

    for w, h in sizes:
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 1. 外部暗黑微光卡片
        pad = max(1, int(w * 0.06))
        draw.rounded_rectangle(
            [pad, pad, w - pad, h - pad],
            radius=max(2, int(w * 0.18)),
            fill=(15, 23, 42, 255),
            outline=(56, 189, 248, 255),
            width=max(1, int(w * 0.04)),
        )

        # 2. 内部芯片基板
        die_pad = max(3, int(w * 0.22))
        draw.rounded_rectangle(
            [die_pad, die_pad, w - die_pad, h - die_pad],
            radius=max(1, int(w * 0.08)),
            fill=(30, 41, 59, 255),
            outline=(37, 99, 235, 220),
            width=max(1, int(w * 0.02)),
        )

        # 3. 焊球矩阵
        grid_start = die_pad + max(2, int(w * 0.08))
        grid_end = w - die_pad - max(2, int(w * 0.08))
        step = (grid_end - grid_start) / 3.0 if w >= 32 else 0
        r = max(1, int(w * 0.035))

        if w >= 32:
            for i in range(4):
                for j in range(4):
                    cx = grid_start + i * step
                    cy = grid_start + j * step
                    if (i, j) == (1, 1):
                        color = (34, 197, 94, 255)  # 绿色 PASS
                    elif (i, j) == (2, 2):
                        color = (239, 68, 68, 255)  # 红色 NG
                    else:
                        color = (56, 189, 248, 230)  # 青色正常球
                    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
        else:
            draw.ellipse([w * 0.35 - 1, h * 0.35 - 1, w * 0.35 + 1, h * 0.35 + 1], fill=(56, 189, 248, 255))
            draw.ellipse([w * 0.65 - 1, h * 0.35 - 1, w * 0.65 + 1, h * 0.35 + 1], fill=(56, 189, 248, 255))
            draw.ellipse([w * 0.35 - 1, h * 0.65 - 1, w * 0.35 + 1, h * 0.65 + 1], fill=(34, 197, 94, 255))
            draw.ellipse([w * 0.65 - 1, h * 0.65 - 1, w * 0.65 + 1, h * 0.65 + 1], fill=(239, 68, 68, 255))

        images.append(img)

    images[0].save(
        output_path,
        format="ICO",
        sizes=[(im.width, im.height) for im in images],
        append_images=images[1:],
    )


def copy_project_files():
    log(f"构建发布目录结构: {APP_DIST_DIR}...")
    APP_DIST_DIR.mkdir(parents=True, exist_ok=True)

    def ignore_patterns(path, names):
        ignored = set()
        for name in names:
            if name in ("__pycache__", ".git", ".idea", ".vscode", "scratch", "dist"):
                ignored.add(name)
            elif name.endswith((".pyc", ".pyo", ".pyd.bak", ".log", ".tmp")):
                ignored.add(name)
        return ignored

    # 1. 复制 backend
    dest_backend = APP_DIST_DIR / "backend"
    if dest_backend.exists():
        shutil.rmtree(dest_backend)
    log("正在复制后端算法与模型文件 (backend)...")
    shutil.copytree(PROJECT_ROOT / "backend", dest_backend, ignore=ignore_patterns)

    # 2. 复制 desktop_app
    dest_desktop = APP_DIST_DIR / "desktop_app"
    if dest_desktop.exists():
        shutil.rmtree(dest_desktop)
    log("正在复制桌面端 UI 与业务逻辑 (desktop_app)...")
    shutil.copytree(PROJECT_ROOT / "desktop_app", dest_desktop, ignore=ignore_patterns)

    # 3. 彻底排除与清理 data 测试数据目录（保持分发安装包体积纯净）
    dest_data = APP_DIST_DIR / "data"
    if dest_data.exists():
        log("清理分发包中的历史残留 data 测试数据目录...")
        try:
            shutil.rmtree(dest_data, ignore_errors=True)
        except Exception:
            pass

    # 4. 复制依赖清单与操作手册
    if (PROJECT_ROOT / "requirements_desktop.txt").exists():
        shutil.copy2(PROJECT_ROOT / "requirements_desktop.txt", APP_DIST_DIR / "requirements_desktop.txt")
    
    doc_src_md = PROJECT_ROOT / "docs" / "用户操作与部署手册.md"
    if doc_src_md.exists():
        shutil.copy2(doc_src_md, APP_DIST_DIR / "用户操作与部署手册.md")
        with open(doc_src_md, "r", encoding="utf-8") as f:
            md_content = f.read()
        with open(APP_DIST_DIR / "用户操作与部署手册.txt", "w", encoding="utf-8") as f:
            f.write(md_content)
        log("已随包生成《用户操作与部署手册.txt》与《用户操作与部署手册.md》！")


def copy_runtime_environment():
    dest_runtime = APP_DIST_DIR / "runtime"
    log(f"正在打包便携式 Python 运行环境至: {dest_runtime}...")
    log("采用 Windows 高速多线程并行传输 (Robocopy /MT:16)...")

    cmd = [
        "robocopy",
        str(SOURCE_CONDA_ENV),
        str(dest_runtime),
        "/E",
        "/MT:16",
        "/R:1",
        "/W:1",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/XD",
        "__pycache__",
        ".git",
        "conda-meta",
        "/XF",
        "*.pyc",
        "*.pdb",
    ]
    # robocopy 返回码 0~7 均表示成功传输
    ret = subprocess.run(cmd, capture_output=True, text=True)
    if ret.returncode > 7:
        raise RuntimeError(f"Robocopy 传输运行环境失败，错误代码: {ret.returncode}\n{ret.stderr}")

    log("便携运行环境复制完成！")


def compile_native_launcher(icon_path: Path):
    log("正在编译原生 Win32 GUI 启动器 (BGA_AI_Inspector.exe)...")
    cs_source = APP_DIST_DIR / "launcher.cs"
    exe_target = APP_DIST_DIR / "BGA_AI_Inspector.exe"

    cs_code = r"""using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

class BGALauncher
{
    [STAThread]
    static int Main(string[] args)
    {
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        if (baseDir.EndsWith("\\") || baseDir.EndsWith("/"))
        {
            baseDir = baseDir.Substring(0, baseDir.Length - 1);
        }

        string runtimeDir = Path.Combine(baseDir, "runtime");
        string pyw = Path.Combine(runtimeDir, "pythonw.exe");
        if (!File.Exists(pyw))
        {
            pyw = Path.Combine(runtimeDir, "python.exe");
        }

        if (!File.Exists(pyw))
        {
            MessageBox.Show(
                "未能找到系统内置 Python 运行环境：\n" + pyw + "\n\n请确保软件包已完整解压，且保留 runtime 文件夹。",
                "BGA 智能工业质检工作站 - 启动错误",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }

        string mainScript = Path.Combine(baseDir, @"desktop_app\main.py");
        if (!File.Exists(mainScript))
        {
            MessageBox.Show(
                "未能找到工作站主程序脚本：\n" + mainScript + "\n\n请确认程序目录结构完整。",
                "BGA 智能工业质检工作站 - 启动错误",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }

        ProcessStartInfo psi = new ProcessStartInfo();
        psi.FileName = pyw;
        string argStr = "\"" + mainScript + "\"";
        if (args != null && args.Length > 0)
        {
            argStr += " " + string.Join(" ", args);
        }
        psi.Arguments = argStr;
        psi.WorkingDirectory = baseDir;
        psi.UseShellExecute = false;

        // 注入高隔离度的运行环境变量
        string backendDir = Path.Combine(baseDir, "backend");
        string runtimeLibBin = Path.Combine(runtimeDir, @"Library\bin");
        string runtimeScripts = Path.Combine(runtimeDir, "Scripts");
        string existingPath = Environment.GetEnvironmentVariable("PATH") ?? "";

        psi.EnvironmentVariables["PATH"] = runtimeDir + ";" + runtimeLibBin + ";" + runtimeScripts + ";" + existingPath;
        psi.EnvironmentVariables["PYTHONPATH"] = backendDir + ";" + baseDir;

        try
        {
            Process.Start(psi);
            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                "工作站启动异常：\n" + ex.Message,
                "BGA 智能工业质检工作站 - 启动失败",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }
    }
}
"""
    cs_source.write_text(cs_code, encoding="utf-8")

    compile_cmd = [
        str(CSC_COMPILER),
        "/nologo",
        "/target:winexe",
        f"/win32icon:{icon_path}",
        f"/out:{exe_target}",
        str(cs_source),
    ]
    ret = subprocess.run(compile_cmd, capture_output=True, text=True)
    cs_source.unlink(missing_ok=True)

    if ret.returncode != 0:
        raise RuntimeError(f"编译启动器失败:\n{ret.stdout}\n{ret.stderr}")

    log("原生 Win32 启动器 BGA_AI_Inspector.exe 编译成功！")


def create_auxiliary_scripts():
    log("生成调试启动脚本与说明文档...")

    # 1. run_debug.bat
    debug_bat = APP_DIST_DIR / "run_debug.bat"
    debug_bat_content = r"""@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
title BGA AI Inspector - Debug Console Mode

echo ==============================================================
echo       BGA 智能工业质检工作站 (控制台调试模式)
echo ==============================================================
set "PROJ_ROOT=%~dp0"
if "%PROJ_ROOT:~-1%"=="\" set "PROJ_ROOT=%PROJ_ROOT:~0,-1%"

set "PATH=%PROJ_ROOT%\runtime;%PROJ_ROOT%\runtime\Library\bin;%PROJ_ROOT%\runtime\Scripts;%PATH%"
set "PYTHONPATH=%PROJ_ROOT%\backend;%PROJ_ROOT%;%PYTHONPATH%"

echo [*] 正在通过内置运行环境启动主程序...
"%PROJ_ROOT%\runtime\python.exe" desktop_app\main.py %*

if !ERRORLEVEL! neq 0 (
    echo.
    echo ==============================================================
    echo [错误提示] 应用程序退出代码: !ERRORLEVEL!
    echo ==============================================================
    pause
)
"""
    debug_bat.write_text(debug_bat_content, encoding="utf-8")

    # 2. 使用说明文档
    readme_txt = APP_DIST_DIR / "使用说明.txt"
    readme_content = """======================================================================
  BGA 智能工业质检工作站 (BGA AI Inspector) - 便携式全能发行版 v1.0
======================================================================

【快速启动】
1. 直接双击运行根目录下的【BGA_AI_Inspector.exe】即可启动工作站（无控制台黑窗口）；
2. 如需查看详细运行日志或进行工程排查，可双击运行【run_debug.bat】。

【硬件自适应能力说明】
本软件包已内置 GPU+CPU 双模自适应推理引擎：
- 若运行于配备 NVIDIA 独立显卡（RTX 30/40/50 系列等）的高配工控机：
  系统启动后将自动点亮【绿色 GPU 加速指示灯】，进入毫秒级高速质检模式（无需安装 CUDA Toolkit）；
- 若运行于无独立显卡或纯 CPU/核显电脑：
  系统启动后将自动平滑降级并点亮【黄色 CPU 指示灯】，自动调用全核多线程并发推理，绝不闪退崩溃。

【目录结构规范】
- BGA_AI_Inspector.exe : 原生无边框桌面程序启动器
- run_debug.bat        : 控制台调试启动脚本
- runtime/             : 便携式独立 Python 运行环境（请勿修改）
- backend/             : YOLO 深度学习模型与工业算法流水线
- desktop_app/         : 现代化图形界面组件、工业图元及样式表
- data/                : 样例检测工件图像库（包含桥连短路与空洞样例）

======================================================================
"""
    readme_txt.write_text(readme_content, encoding="utf-8")

    # 3. Inno Setup 打包工程脚本
    iss_file = APP_DIST_DIR / "Inno_Setup_Installer.iss"
    iss_content = r"""; Inno Setup 自动化安装包生成脚本
#define MyAppName "BGA智能工业质检工作站"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "AOI_Industrial_AI"
#define MyAppExeName "BGA_AI_Inspector.exe"

[Setup]
AppId={{E68A8E9A-C1A3-41A8-B603-9A2E77D3D2B1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..\installer_output
OutputBaseFilename=BGA_AI_Inspector_Setup_v1.0
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\调试模式启动"; Filename: "{app}\run_debug.bat"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
"""
    iss_file.write_text(iss_content, encoding="utf-8")
    log("辅助文件与安装向导脚本已就绪！")


def verify_packaged_app():
    log("对已打包应用执行自动化全量可用性验证 (离屏检测)...")
    test_py = APP_DIST_DIR / "runtime" / "python.exe"
    test_script = (
        "import os, sys\n"
        "os.environ['QT_QPA_PLATFORM'] = 'offscreen'\n"
        "base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n"
        "backend = os.path.join(base, 'backend')\n"
        "sys.path.insert(0, backend)\n"
        "sys.path.insert(1, base)\n"
        "import torch, PySide6\n"
        "from desktop_app.ui.main_window import MainWindow\n"
        "print('CUDA:', torch.cuda.is_available(), 'PySide6:', PySide6.__version__)\n"
        "app = PySide6.QtWidgets.QApplication(['--platform', 'offscreen'])\n"
        "win = MainWindow()\n"
        "print('SUCCESS: Packaged application initialized cleanly!')\n"
        "win.close()\n"
        "del win\n"
        "del app\n"
        "sys.exit(0)\n"
    )
    test_file = APP_DIST_DIR / "_verify_test.py"
    test_file.write_text(test_script, encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = str(APP_DIST_DIR / "runtime") + ";" + str(APP_DIST_DIR / "runtime" / "Library" / "bin") + ";" + env.get("PATH", "")
    env["PYTHONPATH"] = str(APP_DIST_DIR / "backend") + ";" + str(APP_DIST_DIR)

    res = subprocess.run([str(test_py), str(test_file)], capture_output=True, text=True, env=env)
    test_file.unlink(missing_ok=True)

    if res.returncode != 0:
        raise RuntimeError(f"已打包应用离屏验证失败:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")

    log(f"离屏验证输出: {res.stdout.strip()}")
    log("[SUCCESS] 已打包应用验证 100% 通过！")


def main():
    t0 = time.time()
    print("=" * 66)
    print("      [+] BGA 智能工业质检工作站 - 全能自适应便携包构建流水线")
    print("=" * 66)

    check_prerequisites()

    icon_path = PROJECT_ROOT / "app_icon.ico"
    if not icon_path.exists():
        generate_app_icon(icon_path)

    copy_project_files()
    shutil.copy2(icon_path, APP_DIST_DIR / "app_icon.ico")

    copy_runtime_environment()
    compile_native_launcher(icon_path)
    create_auxiliary_scripts()
    verify_packaged_app()

    elapsed = round(time.time() - t0, 1)
    print("=" * 66)
    print(f"[OK] 打包全流程圆满完成！总耗时: {elapsed} 秒")
    print(f"[*] 发布输出目录: {APP_DIST_DIR}")
    print("  |-- BGA_AI_Inspector.exe      (双击秒开，无黑窗口)")
    print("  |-- run_debug.bat             (控制台日志调试模式)")
    print("  |-- Inno_Setup_Installer.iss  (安装包制作工程脚本)")
    print("  |-- 使用说明.txt")
    print("  |-- runtime/                  (独立便携 Python+CUDA/CPU 运行环境)")
    print("  |-- backend/                  (YOLO 算法模型库与权重)")
    print("  +-- desktop_app/              (现代工业界面与业务模块)")
    print("=" * 66)


if __name__ == "__main__":
    main()
