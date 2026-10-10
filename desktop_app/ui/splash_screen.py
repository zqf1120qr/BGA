# -*- coding: utf-8 -*-
"""
🌟 BGA 智能工业质检工作站 - 科技感启动闪屏 (Splash Screen)
------------------------------------------------------------
在主界面加载重型科学计算库及深度学习引擎时提供丝滑即时的视觉反馈与进度指示。
"""
import os
import sys

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


def get_app_icon_path() -> str:
    """获取应用图标绝对路径 (优先从 _internal 目录检索，保持根目录整洁)"""
    search_dirs = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        search_dirs.append(os.path.join(exe_dir, "_internal"))
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            search_dirs.append(meipass)
        search_dirs.append(exe_dir)
    
    # 源码环境
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(cur_dir))
    search_dirs.append(project_root)
    search_dirs.append(os.getcwd())

    for d in search_dirs:
        cand = os.path.join(d, "app_icon.ico")
        if os.path.exists(cand):
            return os.path.abspath(cand)
        cand_assets = os.path.join(d, "assets", "app_icon.ico")
        if os.path.exists(cand_assets):
            return os.path.abspath(cand_assets)
    return ""


class BgaSplashScreen(QWidget):
    """现代化深邃工业风高科技启动闪屏"""
    def __init__(self, icon_path: str = ""):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(560, 310)

        self.icon_path = icon_path or get_app_icon_path()
        self._setup_ui()
        self._center_on_screen()

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            x = (geo.width() - self.width()) // 2
            y = (geo.height() - self.height()) // 2
            self.move(x, y)

    def _setup_ui(self):
        # 顶级容器 (科技深色背景 + 发光细边框)
        root = QFrame(self)
        root.setGeometry(0, 0, self.width(), self.height())
        root.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #080d19, stop:0.5 #0d1527, stop:1 #060913);
                border: 1px solid #1e293b;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 26, 28, 22)
        layout.setSpacing(10)

        # 1. 顶部 Header 栏 (左侧图标 + 右侧标题与版本)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(16)

        # 图标
        self.lbl_icon = QLabel()
        self.lbl_icon.setStyleSheet("border: none; background: transparent;")
        if self.icon_path and os.path.exists(self.icon_path):
            pix = QIcon(self.icon_path).pixmap(52, 52)
            self.lbl_icon.setPixmap(pix)
        else:
            self.lbl_icon.setText("🔬")
            self.lbl_icon.setStyleSheet("font-size: 38px; border: none; background: transparent;")
        header_layout.addWidget(self.lbl_icon)

        # 文本信息
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        lbl_title = QLabel("BGA 芯片智能工业质检工作站")
        lbl_title.setStyleSheet("""
            font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            font-size: 19px;
            font-weight: bold;
            color: #f8fafc;
            border: none;
            background: transparent;
        """)
        title_box.addWidget(lbl_title)

        lbl_sub = QLabel("BGA AI Industrial AOI Inspection Workstation")
        lbl_sub.setStyleSheet("""
            font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            font-size: 11px;
            font-weight: 500;
            color: #38bdf8;
            letter-spacing: 0.5px;
            border: none;
            background: transparent;
        """)
        title_box.addWidget(lbl_sub)

        header_layout.addLayout(title_box)
        header_layout.addStretch()

        # 版本药丸胶囊
        lbl_ver = QLabel("v1.0.0 Pro")
        lbl_ver.setStyleSheet("""
            color: #10b981;
            background-color: #064e3b;
            border: 1px solid #059669;
            border-radius: 9px;
            padding: 3px 9px;
            font-size: 11px;
            font-weight: bold;
        """)
        header_layout.addWidget(lbl_ver, alignment=Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header_layout)

        # 分割线
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background-color: #1e293b; border: none; max-height: 1px;")
        layout.addWidget(divider)

        # 2. 中部架构说明
        desc_box = QVBoxLayout()
        desc_box.setSpacing(4)
        lbl_core = QLabel("⚙️ 工业深度神经网络推理架构 (PyTorch · CUDA / CPU 硬件自适应引擎)")
        lbl_core.setStyleSheet("color: #94a3b8; font-size: 12px; border: none; background: transparent;")
        desc_box.addWidget(lbl_core)

        lbl_feature = QLabel("🛡️ 四维质检体系: 空洞率计算 | 桥连短路侦测 | 虚焊少锡判定 | 网格拓扑精修")
        lbl_feature.setStyleSheet("color: #64748b; font-size: 11px; border: none; background: transparent;")
        desc_box.addWidget(lbl_feature)
        layout.addLayout(desc_box)

        layout.addStretch()

        # 3. 底部加载状态与进度条
        self.lbl_status = QLabel("● 正在初始化核心计算拓扑与硬件环境...")
        self.lbl_status.setStyleSheet("""
            color: #38bdf8;
            font-family: 'Microsoft YaHei', sans-serif;
            font-size: 12px;
            font-weight: 500;
            border: none;
            background: transparent;
        """)
        layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(10)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(5)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e293b;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #38bdf8);
                border-radius: 2px;
            }
        """)
        layout.addWidget(self.progress_bar)

    def set_progress(self, percent: int, text: str = ""):
        """更新闪屏加载进度与状态文字并即时刷新界面"""
        self.progress_bar.setValue(max(0, min(100, percent)))
        if text:
            self.lbl_status.setText(text)
        QApplication.processEvents()

    def finish(self, main_window: QWidget):
        """当主窗口准备就绪时优雅淡出/关闭闪屏并展示主窗口"""
        self.close()
        main_window.show()
        QApplication.processEvents()
