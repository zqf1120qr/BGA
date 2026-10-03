# -*- coding: utf-8 -*-
"""
🌟 BGA 智能工业质检工作站 - 桌面端启动总入口
=============================================
运行方式:
    python desktop_app/main.py
"""
import os
import sys

# 保证在 Windows 控制台下正常输出 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 确保项目根目录与 backend 目录位于 sys.path 正确顺序
desktop_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(desktop_dir)
backend_dir = os.path.join(project_root, "backend")

# 1. 优先将 backend 目录置于 sys.path 最前端，确保 YOLO 底层模块 models/utils 纯正解析
while backend_dir in sys.path:
    sys.path.remove(backend_dir)
sys.path.insert(0, backend_dir)

# 2. 将 project_root 紧随其后，确保以 desktop_app.* 完整命名空间导入
while project_root in sys.path:
    sys.path.remove(project_root)
sys.path.insert(1, project_root)

# 3. 核心隔离：移除脚本默认注入的当前所在目录 desktop_dir，防止 desktop_app 内部子目录污染根命名空间
while desktop_dir in sys.path:
    sys.path.remove(desktop_dir)

# 4. 强制环境对齐：如果已存在同名 utils 命名空间，确保清除并指向 backend.utils
if "utils" in sys.modules:
    del sys.modules["utils"]

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from desktop_app.ui.main_window import MainWindow


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

    # 实例化并显示主工作站窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
