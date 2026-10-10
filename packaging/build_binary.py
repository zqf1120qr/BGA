# -*- coding: utf-8 -*-
"""
🌟 BGA 智能工业质检工作站 - 方案 B 一键二进制打包构建系统
=============================================================
使用方式:
    python packaging/build_binary.py
功能:
    1. 自动检测并安全关闭运行中的旧程序 (解除 Windows 文件锁)；
    2. 调度 PyInstaller 基于 packaging/bga_inspector.spec 执行二进制编译；
    3. 自动同步外部可热替换权重 (backend/best.pt) 与测试数据；
    4. 规范收纳 app_icon.ico 至 _internal/ 目录，保持根目录极致清爽；
    5. 生成即用型独立部署包: dist/BGA_AI_Inspector_Binary/。
"""
import os
import sys
import shutil
import subprocess
import time

# 保证 UTF-8 控制台输出
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
SPEC_FILE = os.path.join(CURRENT_DIR, "bga_inspector.spec")
# 生成即用型独立部署包目录: dist/BGA_AI_Inspector/
DIST_DIR = os.path.join(PROJECT_ROOT, "dist", "BGA_AI_Inspector")
INTERNAL_DIR = os.path.join(DIST_DIR, "_internal")


def log(msg: str):
    print(f"[*] {msg}", flush=True)


def check_and_kill_old_process():
    log("检查是否有旧版本工作站正在运行...")
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["powershell", "-Command", "Stop-Process -Name 'BGA_AI_Inspector' -Force -ErrorAction SilentlyContinue"],
                capture_output=True
            )
            time.sleep(1)
    except Exception:
        pass


def run_pyinstaller():
    log("开始执行 PyInstaller 二进制编译封装 (请稍候 1~2 分钟)...")
    cmd = [sys.executable, "-m", "PyInstaller", SPEC_FILE, "--noconfirm"]
    res = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if res.returncode != 0:
        print("\n[!] 编译失败，请查看上方 PyInstaller 错误输出！")
        sys.exit(res.returncode)
    log("PyInstaller 核心编译完成！")


def deploy_external_assets():
    log("正在组织外部部署资产与说明文件...")

    # 1. 确保 app_icon.ico 位于 _internal/ 内部，且根目录不残留
    icon_src = os.path.join(PROJECT_ROOT, "assets", "app_icon.ico")
    if not os.path.exists(icon_src):
        icon_src = os.path.join(PROJECT_ROOT, "app_icon.ico")
    icon_internal = os.path.join(INTERNAL_DIR, "app_icon.ico")
    if os.path.exists(icon_src):
        shutil.copyfile(icon_src, icon_internal)
    root_icon = os.path.join(DIST_DIR, "app_icon.ico")
    if os.path.exists(root_icon):
        try:
            os.remove(root_icon)
        except Exception:
            pass

    # 2. 外部模型权重 (方便现场免打包热替换)
    backend_ext = os.path.join(DIST_DIR, "backend")
    os.makedirs(backend_ext, exist_ok=True)
    weights_src = os.path.join(PROJECT_ROOT, "backend", "best.pt")
    if os.path.exists(weights_src):
        shutil.copyfile(weights_src, os.path.join(backend_ext, "best.pt"))

    # 3. 彻底排除与清理 data 测试数据目录（保持分发安装包体积纯净）
    data_dist = os.path.join(DIST_DIR, "data")
    if os.path.exists(data_dist):
        log("清理分发包中的历史残留 data 测试数据目录...")
        try:
            shutil.rmtree(data_dist, ignore_errors=True)
        except Exception as e:
            log(f"清理 data 目录提示: {e}")
            
    internal_data = os.path.join(INTERNAL_DIR, "data")
    if os.path.exists(internal_data):
        try:
            shutil.rmtree(internal_data, ignore_errors=True)
        except Exception:
            pass

    # 4. 部署官方标准《用户操作与部署手册》(.md 与 .txt 格式)
    doc_src_md = os.path.join(PROJECT_ROOT, "docs", "用户操作与部署手册.md")
    manual_dst_md = os.path.join(DIST_DIR, "用户操作与部署手册.md")
    manual_dst_txt = os.path.join(DIST_DIR, "用户操作与部署手册.txt")

    if os.path.exists(doc_src_md):
        shutil.copyfile(doc_src_md, manual_dst_md)
        with open(doc_src_md, "r", encoding="utf-8") as f:
            md_content = f.read()
        with open(manual_dst_txt, "w", encoding="utf-8") as f:
            f.write(md_content)
        log("已随包生成《用户操作与部署手册.txt》与《用户操作与部署手册.md》！")

    # 清理旧版简易指南文件 (若存在)
    # 清理旧命名目录 dist/BGA_AI_Inspector_Binary (若存在)
    old_binary_dir = os.path.join(PROJECT_ROOT, "dist", "BGA_AI_Inspector_Binary")
    if os.path.exists(old_binary_dir):
        log("清理历史旧命名目录 dist/BGA_AI_Inspector_Binary...")
        try:
            shutil.rmtree(old_binary_dir, ignore_errors=True)
        except Exception:
            pass

    log("资产组织与规整部署完成！")


def main():
    print("=" * 65)
    print("       🌟 BGA 智能工业质检工作站 - 方案 B 一键打包构建系统")
    print("=" * 65)
    log(f"项目根目录: {PROJECT_ROOT}")
    log(f"规范配置文件: {SPEC_FILE}")
    log(f"当前 Python 解释器: {sys.executable}")

    check_and_kill_old_process()
    run_pyinstaller()
    deploy_external_assets()

    print("=" * 65)
    print("✅ 打包构建成功！")
    print(f"📦 输出目录: {DIST_DIR}")
    print(f"🚀 主程序:   {os.path.join(DIST_DIR, 'BGA_AI_Inspector.exe')}")
    print("=" * 65)


if __name__ == "__main__":
    main()
