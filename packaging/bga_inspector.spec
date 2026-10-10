# -*- mode: python ; coding: utf-8 -*-
"""
🌟 BGA 智能工业质检工作站 - PyInstaller 工业级二进制规范构建配置
=============================================================
构建目标: 方案 B (源码全封闭为二进制，全能自适应 GPU/CPU 目录部署包)
"""
import os
import sys

block_cipher = None
SPEC_DIR = os.path.abspath(SPECPATH)
PROJECT_ROOT = os.path.dirname(SPEC_DIR) if os.path.basename(SPEC_DIR) == "packaging" else SPEC_DIR
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

# 图标路径自动适配 (优先 assets/，兼容根目录)
ICON_PATH = os.path.join(PROJECT_ROOT, "assets", "app_icon.ico")
if not os.path.exists(ICON_PATH):
    ICON_PATH = os.path.join(PROJECT_ROOT, "app_icon.ico")

# 数据文件定义
added_datas = [
    # 核心深度学习模型权重 (打包内置，程序亦支持读取外部同名覆盖)
    (os.path.join(PROJECT_ROOT, "backend", "best.pt"), "backend"),
    # 暗黑工业级 QSS 样式表与图标
    (os.path.join(PROJECT_ROOT, "desktop_app", "ui", "styles"), "desktop_app/ui/styles"),
    (os.path.join(PROJECT_ROOT, "desktop_app", "ui", "styles"), "styles"),
    # 高清多尺寸应用图标
    (ICON_PATH, "."),
]

# 核心隐式依赖库 (确保 PyTorch、YOLO 与科学计算模块全部深度捕获)
hidden_imports = [
    # PyTorch 核心与 CUDA 支撑
    "torch",
    "torchvision",
    "torchvision.ops",
    "torch.nn",
    "torch.nn.functional",
    "torch.cuda",
    # 科学计算与图像处理
    "cv2",
    "numpy",
    "scipy",
    "scipy.spatial",
    "scipy.spatial.distance",
    "scipy.ndimage",
    "sklearn",
    "sklearn.utils._typedefs",
    "sklearn.neighbors._typedefs",
    # 数据分析与质检报表导出
    "pandas",
    "openpyxl",
    "reportlab",
    "reportlab.lib",
    "reportlab.platypus",
    "reportlab.pdfgen",
    "reportlab.pdfbase",
    "reportlab.pdfbase.ttfonts",
    # YOLO 神经网络模块 (反序列化 torch.load 必须)
    "models",
    "models.common",
    "models.experimental",
    "models.yolo",
    "utils",
    "utils.datasets",
    "utils.general",
    "utils.torch_utils",
    "utils.tool_kit",
    "utils.grid_node_refiner",
    # BGA 后端质检算法流水线
    "detector",
    "bga_pipeline",
    "bga_void_seg",
    "bga_bridge_detect",
    "bga_insufficient_detect",
    # 桌面工作站各子模块
    "desktop_app",
    "desktop_app.app_config",
    "desktop_app.core",
    "desktop_app.core.hardware_sniff",
    "desktop_app.core.worker_thread",
    "desktop_app.core.inspection_manager",
    "desktop_app.core.image_converter",
    "desktop_app.ui",
    "desktop_app.ui.splash_screen",
    "desktop_app.ui.main_window",
    "desktop_app.ui.frameless_resizer",
    "desktop_app.ui.panels.control_panel",
    "desktop_app.ui.panels.defect_table",
    "desktop_app.ui.panels.param_panel",
    "desktop_app.ui.panels.result_panel",
    "desktop_app.ui.panels.thumbnail_bar",
    "desktop_app.ui.viewports.image_canvas",
    "matplotlib",
    "matplotlib.pyplot",
    "desktop_app.utils.excel_reporter",
    "desktop_app.utils.pdf_reporter",
]

a = Analysis(
    [os.path.join(PROJECT_ROOT, "desktop_app", "main.py")],
    pathex=[PROJECT_ROOT, BACKEND_DIR],
    binaries=[],
    datas=added_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "IPython",
        "notebook",
        "tensorboard",
        "torch.utils.tensorboard",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BGA_AI_Inspector",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # 无控制台黑窗口 (纯正工业级原生桌面窗口)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BGA_AI_Inspector",
)
