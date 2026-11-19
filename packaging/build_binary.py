# -*- coding: utf-8 -*-
"""
🌟 X射线智能工业质检工作站 - 方案 B 一键二进制打包构建系统
=============================================================
使用方式:
    python packaging/build_binary.py
功能:
    1. 自动检测并安全关闭运行中的旧程序 (解除 Windows 文件锁)；
    2. 调度 PyInstaller 基于 packaging/x_ray_inspector.spec 执行二进制编译；
    3. 自动同步外部可热替换权重 (backend/best.pt) 与测试数据；
    4. 规范收纳 app_icon.ico 至 _internal/ 目录，保持根目录极致清爽；
    5. 生成即用型独立部署包: dist/X-Ray_AI_Inspector/。
    6. 主程序可执行文件名称: X-Ray_AI_Inspector.exe。
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
SPEC_FILE = os.path.join(CURRENT_DIR, "x_ray_inspector.spec")
# 生成即用型独立部署包目录: dist/X-Ray_AI_Inspector/
DIST_DIR = os.path.join(PROJECT_ROOT, "dist", "X-Ray_AI_Inspector")
INTERNAL_DIR = os.path.join(DIST_DIR, "_internal")


def log(msg: str):
    print(f"[*] {msg}", flush=True)


def check_and_kill_old_process():
    log("检查是否有旧版本工作站正在运行...")
    try:
        if sys.platform == "win32":
            # 兼容新旧进程名清理
            for proc_name in ["X-Ray_AI_Inspector", "X_Ray_AI_Inspector", "BGA_AI_Inspector"]:
                subprocess.run(
                    ["powershell", "-Command", f"Stop-Process -Name '{proc_name}' -Force -ErrorAction SilentlyContinue"],
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

    # 4. 生成并部署官方标准《用户操作与部署手册.pdf》（面向企业甲方交付，不随包附带 .md 与 .txt）
    doc_src_md = os.path.join(PROJECT_ROOT, "docs", "用户操作与部署手册.md")
    doc_src_pdf = os.path.join(PROJECT_ROOT, "docs", "用户操作与部署手册.pdf")
    manual_dst_pdf = os.path.join(DIST_DIR, "用户操作与部署手册.pdf")

    # 清理历史可能残留的 .md / .txt 手册
    for legacy_name in ("用户操作与部署手册.md", "用户操作与部署手册.txt"):
        legacy_path = os.path.join(DIST_DIR, legacy_name)
        if os.path.exists(legacy_path):
            try:
                os.remove(legacy_path)
            except Exception:
                pass

    if os.path.exists(doc_src_md):
        try:
            if CURRENT_DIR not in sys.path:
                sys.path.insert(0, CURRENT_DIR)
            from build_manual_pdf import build_manual_pdf
            build_manual_pdf(doc_src_md, doc_src_pdf)
            shutil.copyfile(doc_src_pdf, manual_dst_pdf)
            log("已自动渲染并随包生成企业级《用户操作与部署手册.pdf》！")
        except Exception as exc:
            log(f"[WARN] 自动渲染手册 PDF 失败: {exc}")
            if os.path.exists(doc_src_pdf):
                shutil.copyfile(doc_src_pdf, manual_dst_pdf)
                log("已回退拷贝预生成的《用户操作与部署手册.pdf》！")
    elif os.path.exists(doc_src_pdf):
        shutil.copyfile(doc_src_pdf, manual_dst_pdf)
        log("已随包拷贝《用户操作与部署手册.pdf》！")

    # 清理历史旧命名目录 (若存在)
    for old_name in ["BGA_AI_Inspector", "BGA_AI_Inspector_Binary"]:
        old_dir = os.path.join(PROJECT_ROOT, "dist", old_name)
        if os.path.exists(old_dir):
            log(f"清理历史旧命名目录 dist/{old_name}...")
            try:
                shutil.rmtree(old_dir, ignore_errors=True)
            except Exception:
                pass

    # 5. 清理发行包中的历史残留 output 调试输出目录
    output_dist = os.path.join(DIST_DIR, "output")
    if os.path.exists(output_dist):
        try:
            shutil.rmtree(output_dist, ignore_errors=True)
        except Exception:
            pass

    log("资产组织与规整部署完成！")


# =====================================================================
# 体积精简：仅剔除确认不在 torch_cuda.dll / torch_cpu.dll 静态 PE 导入表中的
# 无关子库与大体积第三方误收集资源。
# 重要教训：
# - cufft64_11.dll / cusolver64_11.dll / cusparse64_12.dll 属于 torch_cuda.dll 的
#   静态 PE 硬导入表依赖！在装有 CUDA Toolkit 的开发机上删除后会被系统 PATH 掩盖，
#   但在无 CUDA 的干净客户机上会直接导致 WinError 126 (shm.dll 加载失败)，严禁删除！
# - 同时保留 cublasLt64_12.dll 与 NVRTC / nvJitLink，确保跨代 NVIDIA 显卡兼容性。
# =====================================================================
SLIM_TORCH_DLLS = [
    # 以下子库已通过 PE 静态导入表全量递归扫描确认：无任何核心 DLL 静态导入
    "cufftw64_11.dll",
    "cusolverMg64_11.dll",
    "cudnn_adv64_9.dll",
    "curand64_10.dll",
    "nvperf_host.dll",
]

SLIM_INTERNAL_PATHS = [
    # OpenCV 的 FFMPEG 视频编解码后端（本项目只处理静态图像）
    "cv2/opencv_videoio_ffmpeg4110_64.dll",
    # Qt QML / Quick / Pdf 运行时（界面为 QWidget 体系，不使用 QML）
    "PySide6/Qt6Quick.dll", "PySide6/Qt6Qml.dll", "PySide6/Qt6QmlModels.dll",
    "PySide6/Qt6Pdf.dll", "PySide6/qml",
    # 未被引用的音频处理包
    "torchaudio",
    # HuggingFace / faiss 检索栈（本项目代码零引用，属于传递依赖误收集，约 130MB）
    "transformers", "tokenizers", "hf_xet", "timm",
    "faiss", "faiss_cpu.libs", "sentence_transformers",
    "huggingface_hub-2.2.0.dist-info", "torch-2.11.0+cu128.dist-info",
]


def _dir_size_mb(path):
    total = 0
    if os.path.isfile(path):
        return os.path.getsize(path) / (1024 * 1024)
    for root, _dirs, files in os.walk(path):
        for name in files:
            fp = os.path.join(root, name)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total / (1024 * 1024)


def slim_package():
    """剔除推理用不到的 CUDA 子库与冗余资源，显著压缩分发体积。"""
    log("开始精简分发包体积 (剔除推理无关的 CUDA 子库 / QML / 视频解码器)...")
    freed = 0.0
    removed = 0

    targets = []
    torch_lib = os.path.join(INTERNAL_DIR, "torch", "lib")
    for name in SLIM_TORCH_DLLS:
        targets.append(os.path.join(torch_lib, name))
    for rel in SLIM_INTERNAL_PATHS:
        targets.append(os.path.join(INTERNAL_DIR, rel))

    for path in targets:
        if not os.path.exists(path):
            continue
        size = _dir_size_mb(path)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            freed += size
            removed += 1
        except Exception as exc:
            log(f"  [-] 跳过 {os.path.basename(path)}: {exc}")

    # 清理根目录下误留的测试报表 / 调试 pdf（保留正式交付的《用户操作与部署手册.pdf》）
    for name in os.listdir(DIST_DIR):
        if name.lower().endswith(".pdf") and name != "用户操作与部署手册.pdf":
            try:
                size = _dir_size_mb(os.path.join(DIST_DIR, name))
                os.remove(os.path.join(DIST_DIR, name))
                freed += size
                removed += 1
            except Exception:
                pass

    total_mb = _dir_size_mb(DIST_DIR)
    log(f"精简完成：移除 {removed} 项，节省 {freed:.0f} MB，当前分发体积约 {total_mb:.0f} MB")


def main():
    print("=" * 65)
    print("       🌟 X射线智能工业质检工作站 - 方案 B 一键打包构建系统")
    print("=" * 65)
    log(f"项目根目录: {PROJECT_ROOT}")
    log(f"规范配置文件: {SPEC_FILE}")
    log(f"当前 Python 解释器: {sys.executable}")

    check_and_kill_old_process()
    run_pyinstaller()
    deploy_external_assets()
    slim_package()

    print("=" * 65)
    print("✅ 打包构建成功！")
    print(f"📦 输出目录: {DIST_DIR}")
    print(f"🚀 主程序:   {os.path.join(DIST_DIR, 'X-Ray_AI_Inspector.exe')}")
    print("=" * 65)


if __name__ == "__main__":
    main()
