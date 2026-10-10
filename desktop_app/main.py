# -*- coding: utf-8 -*-
"""
🌟 BGA 智能工业质检工作站 - 桌面端启动总入口
=============================================
运行方式:
    python desktop_app/main.py
"""
import os
import sys

class _NullWriter:
    def write(self, s): pass
    def flush(self): pass

if sys.stdout is None:
    sys.stdout = _NullWriter()
elif hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

if sys.stderr is None:
    sys.stderr = _NullWriter()
elif hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 确保项目根目录与 backend 目录位于 sys.path 正确顺序 (兼容开发与 PyInstaller 打包)
if getattr(sys, "frozen", False):
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    project_root = base_dir
    backend_dir = os.path.join(base_dir, "backend")
    desktop_dir = os.path.join(base_dir, "desktop_app")
else:
    desktop_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(desktop_dir)
    backend_dir = os.path.join(project_root, "backend")

# 1. 优先将 backend 目录置于 sys.path 最前端，确保 YOLO 底层模块 models/utils 纯正解析
if os.path.exists(backend_dir):
    while backend_dir in sys.path:
        sys.path.remove(backend_dir)
    sys.path.insert(0, backend_dir)

# 2. 将 project_root 紧随其后，确保以 desktop_app.* 完整命名空间导入
if os.path.exists(project_root):
    while project_root in sys.path:
        sys.path.remove(project_root)
    sys.path.insert(1, project_root)

# 3. 核心隔离：移除脚本默认注入的当前所在目录 desktop_dir，防止 desktop_app 内部子目录污染根命名空间
while desktop_dir in sys.path:
    sys.path.remove(desktop_dir)

# Windows 任务栏专属独立 AppUserModelID 注册 (消除系统默认通用白框图标)
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Industrial_AI_AOI.BGA_AI_Inspector.Station.v1.0"
        )
    except Exception:
        pass

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

import traceback
import datetime

def _global_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    err_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    log_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else project_root
    log_file = os.path.join(log_dir, "crash.log")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n==================== CRASH [{datetime.datetime.now()}] ====================\n")
            f.write(err_str)
            f.write("\n==========================================================================\n")
    except Exception:
        pass
    try:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "程序运行异常", f"抱歉，系统启动或运行中遇到未捕获异常：\n\n{exc_value}\n\n详细堆栈已记录至: {log_file}")
    except Exception:
        pass

sys.excepthook = _global_exception_handler


def main():
    # 启用高分屏 High-DPI 渲染支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("BGA_AI_Inspector")
    app.setOrganizationName("Industrial_AI_AOI")

    # 全局默认字体
    default_font = QFont("Microsoft YaHei", 9)
    app.setFont(default_font)

    # 绑定应用级全局图标 (Windows 任务栏图标核心关键)
    from desktop_app.ui.splash_screen import get_app_icon_path
    icon_path = get_app_icon_path()
    if icon_path and os.path.exists(icon_path):
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)

    # 毫秒级极速创建并呈现主工作站视窗 (无闪屏，系统级光标由原生启动器无缝管理)
    from desktop_app.ui.main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
