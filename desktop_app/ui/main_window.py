# -*- coding: utf-8 -*-
"""
🌟 X射线智能工业质检工作站主窗口 (Main Window)
----------------------------------------------
现代化 Slate/Zinc 工业旗舰重构版：
1. 原生无边框窗口 (Frameless Window) 支持顶部平滑拖拽与双击最大化；
2. 左侧升级为紧凑高效的 Tab 分页架构 (【质检任务】与【参数配置】双卡片)；
3. 全面剔除所有 Emoji 符号，采用极简几何状态点与工程字体；
4. 顶部视口采用现代分段式胶囊选择器 (Segmented Pills) 控制低遮挡模式；
5. 修复桥连缺陷联动与高亮定位。
"""
from __future__ import annotations

import datetime
import os
import sys
import tempfile
import cv2
import numpy as np

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizeGrip,
    QSlider,
    QSplitter,
    QStatusBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from desktop_app.ui.frameless_resizer import FramelessResizer

from desktop_app.app_config import app_config_mgr
from desktop_app.core.hardware_sniff import hardware_sniffer
from desktop_app.core.image_converter import crop_image_rect, load_image_unicode
from desktop_app.core.inspection_manager import InspectionSession
from desktop_app.core.worker_thread import InspectionWorker
from desktop_app.ui.panels.control_panel import ControlActionPanel
from desktop_app.ui.panels.defect_table import DefectTablePanel
from desktop_app.ui.panels.param_panel import HorizontalNumericStepper, ParamPanel
from desktop_app.ui.panels.result_panel import ResultSummaryPanel
from desktop_app.ui.panels.thumbnail_bar import BatchThumbnailBar
from desktop_app.ui.viewports.image_canvas import ImageCanvasView
from desktop_app.utils.excel_reporter import (
    export_inspection_excel,
    export_batch_inspection_excel,
)
from desktop_app.utils.pdf_reporter import (
    export_inspection_pdf,
    export_batch_inspection_pdf,
)
from desktop_app.ui.splash_screen import get_app_icon_path


class WindowControlButton(QPushButton):
    """
    🌟 标题栏窗口控制按钮 (最小化 / 最大化·还原 / 关闭)
    ---------------------------------------------------------
    1. 不用系统字体字符 (— □ ❐ ✕) 做图标: 这些字符在不同字体下字宽、字重、
       基线位置各不相同, 三个按钮放在一起会明显不对齐、大小不一;
    2. 改为 QPainter 矢量绘制, 线宽统一 1.4px、图标外框统一 10×10、几何中心严格对齐,
       三个按钮尺寸同为 44×30、圆角 6px, 视觉上完全成套;
    3. 交互: 悬停/按下绘制浅色底, 关闭按钮悬停转为告警红; 图标颜色随悬停由灰转白。
    """
    _KINDS = {"min", "max", "restore", "close"}

    def __init__(self, kind: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._kind = kind if kind in self._KINDS else "max"
        self._hovered = False
        self.setFixedSize(44, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName("BtnClose" if self._kind == "close" else "BtnWinCtrl")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.pressed.connect(self.update)
        self.released.connect(self.update)
        self._sync_tooltip()

    # ---------------- 状态 ----------------
    def _sync_tooltip(self):
        self.setToolTip({
            "min": "最小化",
            "max": "最大化",
            "restore": "向下还原",
            "close": "关闭工作站",
        }.get(self._kind, ""))

    def set_kind(self, kind: str):
        if kind in self._KINDS and kind != self._kind:
            self._kind = kind
            self._sync_tooltip()
            self.update()

    @property
    def kind(self) -> str:
        return self._kind

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    # ---------------- 绘制 ----------------
    def _bg_for_state(self) -> QColor | None:
        pressed = self.isDown()
        active = self._hovered or pressed
        if self._kind == "close":
            if pressed:
                return QColor("#be123c")
            return QColor("#e11d48") if active else None
        if pressed:
            return QColor("#334155")
        return QColor("#1e293b") if active else None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        active = self._hovered or self.isDown()

        # 1) 圆角底色 (悬停 / 按下), 三个按钮同一半径与内缩量
        bg = self._bg_for_state()
        if bg is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(
                QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0), 6.0, 6.0
            )

        # 2) 矢量图标: 统一线宽 1.4px, 统一 10×10 视觉外框, 严格几何居中
        pen = QPen(QColor("#ffffff") if active else QColor("#94a3b8"))
        pen.setWidthF(1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        half = 5.0  # 图标半幅 -> 统一 10×10 视觉外框

        if self._kind == "min":
            painter.drawLine(QPointF(cx - half, cy), QPointF(cx + half, cy))
        elif self._kind == "max":
            painter.drawRect(QRectF(cx - half, cy - half, half * 2, half * 2))
        elif self._kind == "restore":
            # 后方窗口 (右上) 完整方框
            back_rect = QRectF(cx - 0.5, cy - 5.0, 6.8, 6.8)
            front_rect = QRectF(cx - 5.0, cy - 1.8, 6.8, 6.8)
            painter.drawRect(back_rect)
            # 前方窗口 (左下): 先用底色遮住被压住的部分, 再描边, 避免线条穿插
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg if bg is not None else QColor("#0b0f19"))
            painter.drawRect(front_rect.adjusted(0.9, 0.9, -0.9, -0.9))
            painter.restore()
            painter.drawRect(front_rect)
        else:  # close: 略小 (9.6) 以抵消斜线的视觉膨胀感, 与方框视觉等重
            half_d = 4.8
            painter.drawLine(QPointF(cx - half_d, cy - half_d), QPointF(cx + half_d, cy + half_d))
            painter.drawLine(QPointF(cx + half_d, cy - half_d), QPointF(cx - half_d, cy + half_d))

        painter.end()


class CustomTitleBar(QFrame):
    """现代化原生无边框窗口自定义标题栏 (支持平滑拖动与双击最大化)"""
    def __init__(self, parent_window: QMainWindow):
        super().__init__(parent_window)
        self.win = parent_window
        self.drag_start_pos: QPoint | None = None
        self.setFixedHeight(38)
        self.setObjectName("CustomTitleBar")
        self.setStyleSheet("""
            QFrame#CustomTitleBar {
                background-color: #0b0f19;
                border-bottom: 1px solid #1e293b;
            }
            QLabel {
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QPushButton#BtnWinCtrl, QPushButton#BtnClose {
                background: transparent;
                border: none;
                padding: 0px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(10)

        # 应用图标与标题
        icon_path = get_app_icon_path()
        if icon_path and os.path.exists(icon_path):
            self.lbl_icon = QLabel()
            self.lbl_icon.setPixmap(QIcon(icon_path).pixmap(18, 18))
            self.lbl_icon.setStyleSheet("border: none; background: transparent;")
            layout.addWidget(self.lbl_icon)
        else:
            self.lbl_dot = QLabel("●")
            self.lbl_dot.setStyleSheet("color: #38bdf8; font-size: 12px;")
            layout.addWidget(self.lbl_dot)

        self.lbl_title = QLabel("X射线智能工业质检工作站")
        self.lbl_title.setStyleSheet("font-weight: 800; font-size: 12px; color: #f8fafc; letter-spacing: 0.5px;")
        layout.addWidget(self.lbl_title)

        self.lbl_sub = QLabel("| X-ray AI Inspector v1.0")
        self.lbl_sub.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(self.lbl_sub)

        layout.addStretch()

        # 窗口控制按钮组 (最小化 / 最大化·还原 / 关闭) —— 统一的矢量图标, 独立紧凑排布
        self.btn_min = WindowControlButton("min")
        self.btn_min.setToolTip("最小化")
        self.btn_min.clicked.connect(self.win.showMinimized)

        self.btn_max = WindowControlButton("max")
        self.btn_max.clicked.connect(self._toggle_maximize)

        self.btn_close = WindowControlButton("close")
        self.btn_close.clicked.connect(self.win.close)

        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(2)
        ctrl_layout.addWidget(self.btn_min)
        ctrl_layout.addWidget(self.btn_max)
        ctrl_layout.addWidget(self.btn_close)
        layout.addLayout(ctrl_layout)

    def update_max_button(self, is_maximized: bool):
        # 最大化时切换为「还原」图标, 常规态为「最大化」方框
        self.btn_max.set_kind("restore" if is_maximized else "max")

    def _toggle_maximize(self):
        if self.win.isMaximized():
            self.win.showNormal()
        else:
            self.win.showMaximized()
        self.update_max_button(self.win.isMaximized())

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if sys.platform == "win32":
                try:
                    import ctypes
                    ctypes.windll.user32.ReleaseCapture()
                    ctypes.windll.user32.SendMessageW(int(self.win.winId()), 0x0112, 0xF012, 0)
                    event.accept()
                    return
                except Exception:
                    pass
            self.drag_start_pos = event.globalPosition().toPoint() - self.win.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.drag_start_pos and not self.win.isMaximized():
            self.win.move(event.globalPosition().toPoint() - self.drag_start_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.drag_start_pos = None

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()


class CornerGripWidget(QWidget):
    """
    🌟 工业级无边框窗口右下角专用缩放手柄 (Corner Size Grip)
    ---------------------------------------------------------
    1. 视觉标识：绘制 3 道精致 45° 科技感防滑斜线纹理，平时深灰 #64748b，悬停/拖拽时高亮青蓝 #38bdf8；
    2. 鼠标状态：鼠标悬停、划入、拖拽全生命周期锁定为 Qt.CursorShape.SizeFDiagCursor (双向对角箭头 ↘↖)；
    3. 自由拉伸：鼠标左键按住拖拽即可同步平滑调整主窗口的宽度 (Width) 与高度 (Height)，并受最小限制保护；
    4. 自动互斥：主窗口最大化时自动消隐，还原窗口时自动显现。
    """
    def __init__(self, parent_window: QMainWindow, parent: QWidget | None = None):
        super().__init__(parent)
        self.win = parent_window
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip("按住拖拽调整窗口大小 (宽高)")
        self._dragging = False
        self._start_global_pos = QPoint()
        self._start_win_size = QPoint()
        self._is_hovered = False

    def enterEvent(self, event):
        self._is_hovered = True
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        if self.win.isMaximized():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor("#38bdf8") if (self._is_hovered or self._dragging) else QColor("#64748b")
        pen = QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        w, h = self.width(), self.height()
        # 绘制三道平行的对角防滑斜纹 (45度倾斜，贴合右下角)
        painter.drawLine(w - 3, h - 6, w - 6, h - 3)
        painter.drawLine(w - 3, h - 10, w - 10, h - 3)
        painter.drawLine(w - 3, h - 14, w - 14, h - 3)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and not self.win.isMaximized():
            self._dragging = True
            self._start_global_pos = event.globalPosition().toPoint()
            self._start_win_size = QPoint(self.win.width(), self.win.height())
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            self.grabMouse()
            self.update()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            cur_pos = event.globalPosition().toPoint()
            dx = cur_pos.x() - self._start_global_pos.x()
            dy = cur_pos.y() - self._start_global_pos.y()

            min_w = self.win.minimumWidth()
            min_h = self.win.minimumHeight()

            new_w = max(min_w, self._start_win_size.x() + dx)
            new_h = max(min_h, self._start_win_size.y() + dy)

            self.win.resize(new_w, new_h)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.releaseMouse()
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            self.update()
            event.accept()


def _same_file_path(p1: str, p2: str) -> bool:
    """跨平台规范化路径一致性判定"""
    if not p1 or not p2:
        return False
    try:
        return os.path.normcase(os.path.abspath(p1)) == os.path.normcase(os.path.abspath(p2))
    except Exception:
        return p1 == p2


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 启用无边框现代化原生窗口
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.config = app_config_mgr.config
        init_w = max(1120, int(getattr(self.config, "window_width", 1460)))
        init_h = max(720, int(getattr(self.config, "window_height", 920)))
        self.resize(init_w, init_h)
        self.setMinimumSize(1120, 720)

        # 绑定应用与窗口专属图标与标题 (确保任务栏与系统原生显示)
        self.setWindowTitle("X射线智能工业质检工作站")
        icon_path = get_app_icon_path()
        if icon_path and os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.config = app_config_mgr.config
        self.session = InspectionSession()
        self.worker: InspectionWorker | None = None

        # 图像状态与批量质检缓存
        self.current_img_path = ""
        self.original_cv_mat: np.ndarray | None = None
        self.active_cv_mat: np.ndarray | None = None
        self.is_image_cropped: bool = False
        self.crop_temp_map: dict[str, str] = {}
        self.batch_files: list[str] = []
        self.batch_results: dict[str, dict] = {}
        self.batch_review_overrides: dict[str, dict] = {}
        self.current_batch_index: int = -1
        self.is_auto_follow_inspection: bool = True
        self.current_inspecting_index: int = -1

        self._setup_ui()
        self._load_stylesheet()
        self._connect_signals()
        # 🌟 启动时把持久化的视图模式同步到单选按钮 + 画布，
        # 否则会出现「按钮显示 全部细轮廓、画面却按 纯原图 不画任何标注」的错位假象
        self._sync_view_mode_from_config()
        self._apply_toolbar_responsive(self.width())


        # 4. 后台静默预热深度学习模型 (预热 GPU/CPU，消除首次点击的冷启动等待)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(200, self._start_background_model_preload)

    # ==============================================================
    # ================= 🌟 [UI 界面构建与布局] ======================
    # ==============================================================
    def _setup_ui(self):
        # 顶级容器 (给无边框窗体添加精致 1px 边框)
        root_container = QWidget(self)
        root_container.setObjectName("RootContainer")
        root_container.setStyleSheet("QWidget#RootContainer { background-color: #0b0f19; border: 1px solid #273449; }")
        root_layout = QVBoxLayout(root_container)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. 现代化无边框自定义标题栏
        self.custom_titlebar = CustomTitleBar(self)
        root_layout.addWidget(self.custom_titlebar)

        # 2. 顶部视口控制与防遮挡模式工具条
        self._create_top_toolbar(root_layout)

        # 3. 核心中央画布与子组件
        self.canvas = ImageCanvasView(self)
        self.panel_param = ParamPanel(self.config, self)
        self.panel_control = ControlActionPanel(param_panel=self.panel_param, parent=self)
        self.panel_result = ResultSummaryPanel(self)
        self.panel_defect_table = DefectTablePanel(self)

        # 4. 主体左右三栏布局 (QSplitter)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setHandleWidth(2)

        # 4.1 左侧面板：质检任务与算法参数一体化排布
        left_scroll = QScrollArea()
        left_scroll.setObjectName("LeftScrollArea")
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        left_container = QWidget()
        left_container.setObjectName("LeftScrollContainer")
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(6, 6, 6, 6)
        left_layout.setSpacing(0)

        left_layout.addWidget(self.panel_control, stretch=1)

        left_scroll.setWidget(left_container)
        left_scroll.setMinimumWidth(360)
        left_scroll.setMaximumWidth(500)

        # 4.2 中央视口画布与批量缩略图组合容器
        center_container = QWidget()
        center_container.setObjectName("CenterViewportContainer")
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self.thumbnail_bar = BatchThumbnailBar(self)
        self.thumbnail_bar.hide()  # 默认单图模式下隐藏，批量目录载入后显现

        center_layout.addWidget(self.canvas, stretch=1)
        center_layout.addWidget(self.thumbnail_bar, stretch=0)

        # 4.3 右侧看板 (PASS/NG 状态大卡片 + 缺陷明细表)
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(10)

        right_layout.addWidget(self.panel_result)
        right_layout.addWidget(self.panel_defect_table, stretch=1)
        right_container.setMinimumWidth(380)
        right_container.setMaximumWidth(500)

        # 将三部分装入 Splitter
        main_splitter.addWidget(left_scroll)
        main_splitter.addWidget(center_container)
        main_splitter.addWidget(right_container)

        # 优化宽度配比：左翼展开容纳全部控制参数 (370px)，中央视口居中舒展 (690px)，右侧面板舒展容纳表格 (400px)
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setStretchFactor(2, 0)
        main_splitter.setSizes([370, 690, 400])

        root_layout.addWidget(main_splitter, stretch=1)

        # 5. 底部状态栏与进度条
        self._create_status_bar(root_layout)

        # 统一全局交互控件鼠标悬停手型光标 (PointingHandCursor)
        for cls in (QPushButton, QComboBox, QSlider, QRadioButton):
            for w in self.findChildren(cls):
                w.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setCentralWidget(root_container)

        # 安装 8 向平滑窗口缩放手柄与边缘捕获器
        self.resizer = FramelessResizer(self)
        self.resizer.attach(self)
        self.resizer.attach(root_container)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            is_max = self.isMaximized()
            if hasattr(self, "custom_titlebar") and self.custom_titlebar:
                self.custom_titlebar.update_max_button(is_max)
            if hasattr(self, "size_grip") and self.size_grip:
                self.size_grip.setVisible(not is_max)
        super().changeEvent(event)

    def nativeEvent(self, eventType, message):
        if hasattr(self, "resizer") and self.resizer:
            max_btn = getattr(self.custom_titlebar, "btn_max", None) if hasattr(self, "custom_titlebar") else None
            handled, result = self.resizer.handle_native_event(eventType, message, max_btn=max_btn)
            if handled:
                return True, result
        return super().nativeEvent(eventType, message)

    def closeEvent(self, event):
        # 🌟 方案 C: 记忆保存窗口状态与尺寸
        try:
            is_max = self.isMaximized()
            self.config.window_maximized = is_max
            if not is_max:
                # 仅在非最大化常规窗口下记录具体长宽，避免全屏分辨率污染常规还原尺寸
                self.config.window_width = int(self.width())
                self.config.window_height = int(self.height())
            app_config_mgr.save()
        except Exception as e:
            print(f"[WARN] 记忆保存窗口状态失败: {e}")

        if hasattr(self, "resizer") and self.resizer:
            self.resizer.cleanup()
        super().closeEvent(event)

    def _create_top_toolbar(self, parent_layout: QVBoxLayout):
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("TopToolbarFrame")
        toolbar_frame.setStyleSheet("""
            QFrame#TopToolbarFrame {
                background-color: #111726;
                border-bottom: 1px solid #1e293b;
                padding: 4px 8px;
            }
            QPushButton#BtnTool {
                background-color: #141d2d;
                border: 1px solid #243044;
                border-radius: 5px;
                padding: 5px 10px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 11px;
                font-weight: 500;
                color: #cbd5e1;
            }
            QPushButton#BtnTool:hover {
                background-color: #1e293b;
                border: 1px solid #38bdf8;
                font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
                font-size: 11px;
                font-weight: 500;
                color: #ffffff;
            }
        """)

        layout = QHBoxLayout(toolbar_frame)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(12)
        # 供响应式布局 (_apply_toolbar_responsive) 访问
        self._toolbar_frame = toolbar_frame
        self._toolbar_layout = layout

        # 视图模式独立分段控制胶囊容器 (高对比深色卡片底座，绝不与顶栏背景混淆)
        self.view_mode_frame = QFrame()
        self.view_mode_frame.setObjectName("ViewModeFrame")
        view_layout = QHBoxLayout(self.view_mode_frame)
        view_layout.setContentsMargins(8, 2, 8, 2)
        view_layout.setSpacing(10)

        lbl_mode = QLabel("视图模式:")
        self.lbl_mode_prefix = lbl_mode
        view_layout.addWidget(lbl_mode)

        self.btn_view_outline = QRadioButton("全部细轮廓 (默认)")
        self.btn_view_outline.setChecked(True)
        self.btn_view_outline.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_outline.toggled.connect(lambda: self._on_view_mode_changed("all_outline"))

        self.btn_view_defect = QRadioButton("仅高亮缺陷")
        self.btn_view_defect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_defect.toggled.connect(lambda: self._on_view_mode_changed("defect_only"))

        self.btn_view_raw = QRadioButton("纯原图")
        self.btn_view_raw.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_raw.toggled.connect(lambda: self._on_view_mode_changed("raw_image"))

        self.view_btn_group = QButtonGroup(self)
        self.view_btn_group.addButton(self.btn_view_outline)
        self.view_btn_group.addButton(self.btn_view_defect)
        self.view_btn_group.addButton(self.btn_view_raw)

        view_layout.addWidget(self.btn_view_outline)
        view_layout.addWidget(self.btn_view_defect)
        view_layout.addWidget(self.btn_view_raw)

        layout.addWidget(self.view_mode_frame)

        # 标注透明度调节 (保留在顶栏原本位置，支持滑块、键盘手输具体数值与加减步进微调)
        self.lbl_alpha = QLabel("| 标注透明度:")
        self.lbl_alpha.setStyleSheet("font-size: 11px; color: #94a3b8; margin-left: 6px;")
        layout.addWidget(self.lbl_alpha)

        self.slider_alpha = QSlider(Qt.Orientation.Horizontal)
        self.slider_alpha.setRange(10, 100)
        self.slider_alpha.setValue(int(self.config.overlay_alpha * 100))
        self.slider_alpha.setFixedWidth(75)
        self.slider_alpha.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_alpha.valueChanged.connect(self._on_alpha_slider_changed)
        layout.addWidget(self.slider_alpha)

        self.spin_alpha = HorizontalNumericStepper(
            min_val=10.0, max_val=100.0, step=5.0, decimals=0, color_hex="#38bdf8"
        )
        self.spin_alpha.setValue(self.config.overlay_alpha * 100.0)
        self.spin_alpha.valueChanged.connect(self._on_alpha_spin_changed)
        layout.addWidget(self.spin_alpha)

        # 🌟 窄窗口折叠入口：视口辅助按钮收进「更多」下拉菜单，避免顶栏被挤压溢出/文字被裁切
        self.btn_more = QToolButton()
        self.btn_more.setText("更多")
        self.btn_more.setToolTip("更多视口操作 (窗口较窄时自动收起的按钮)")
        self.btn_more.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_more.setStyleSheet("""
            QToolButton {
                background-color: #141d2d;
                color: #cbd5e1;
                border: 1px solid #243044;
                border-radius: 4px;
                padding: 3px 6px 3px 8px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 11px;
                font-weight: 500;
                min-height: 20px;
            }
            QToolButton:hover {
                background-color: #243044;
                border: 1px solid #38bdf8;
                color: #ffffff;
            }
        """)
        self._menu_more = QMenu(self.btn_more)
        self._menu_more.setStyleSheet(
            "QMenu { background-color: #141d2d; color: #cbd5e1; border: 1px solid #243044; padding: 4px; }"
            "QMenu::item { padding: 5px 22px 5px 14px; border-radius: 4px; font-size: 11px; }"
            "QMenu::item:selected { background-color: #1e293b; color: #ffffff; }"
        )
        self._menu_more.addAction("适应窗口").triggered.connect(lambda: self.canvas.fit_in_view())
        self._menu_more.addAction("1:1 原尺寸").triggered.connect(lambda: self.canvas.zoom_1to1())
        self._menu_more.addAction("放大 +").triggered.connect(lambda: self.canvas.zoom_in())
        self._menu_more.addAction("缩小 -").triggered.connect(lambda: self.canvas.zoom_out())
        self._menu_more.addSeparator()
        self._menu_more.addAction("恢复显示标注").triggered.connect(self._handle_restore_annotations)
        self.btn_more.setMenu(self._menu_more)
        self.btn_more.hide()
        layout.addWidget(self.btn_more)

        # 视口辅助控制分隔器
        self.lbl_sep = QLabel("|")
        self.lbl_sep.setStyleSheet("color: #475569; margin: 0 4px;")
        layout.addWidget(self.lbl_sep)

        # 视口辅助控制 (锁定文字字号/字重/边距，悬浮仅改背景色，彻底杜绝文字抖动跳跃)
        btn_tool_qss = """
            QPushButton {
                background-color: #141d2d;
                color: #cbd5e1;
                border: 1px solid #243044;
                border-radius: 4px;
                padding: 3px 8px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 11px;
                font-weight: 500;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #243044;
                color: #cbd5e1;
                border: 1px solid #243044;
                padding: 3px 8px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:pressed {
                background-color: #0b1120;
                color: #cbd5e1;
                border: 1px solid #243044;
                padding: 3px 8px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 11px;
                font-weight: 500;
            }
        """

        self.btn_fit = QPushButton("适应窗口")
        self.btn_fit.setObjectName("BtnTool")
        self.btn_fit.setStyleSheet(btn_tool_qss)
        self.btn_fit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fit.clicked.connect(lambda: self.canvas.fit_in_view())
        layout.addWidget(self.btn_fit)

        self.btn_1to1 = QPushButton("1:1 原尺寸")
        self.btn_1to1.setObjectName("BtnTool")
        self.btn_1to1.setStyleSheet(btn_tool_qss)
        self.btn_1to1.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_1to1.clicked.connect(lambda: self.canvas.zoom_1to1())
        layout.addWidget(self.btn_1to1)

        self.btn_zoom_in = QPushButton("放大 +")
        self.btn_zoom_in.setObjectName("BtnTool")
        self.btn_zoom_in.setStyleSheet(btn_tool_qss)
        self.btn_zoom_in.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_zoom_in.setToolTip("放大视口 (快捷键: 鼠标滚轮向上滚动)")
        self.btn_zoom_in.clicked.connect(lambda: self.canvas.zoom_in())
        layout.addWidget(self.btn_zoom_in)

        self.btn_zoom_out = QPushButton("缩小 -")
        self.btn_zoom_out.setObjectName("BtnTool")
        self.btn_zoom_out.setStyleSheet(btn_tool_qss)
        self.btn_zoom_out.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_zoom_out.setToolTip("缩小视口 (快捷键: 鼠标滚轮向下滚动)")
        self.btn_zoom_out.clicked.connect(lambda: self.canvas.zoom_out())
        layout.addWidget(self.btn_zoom_out)

        # 视口辅助控制分隔器
        self.lbl_sep2 = QLabel("|")
        self.lbl_sep2.setStyleSheet("color: #475569; margin: 0 4px;")
        layout.addWidget(self.lbl_sep2)

        # 一键恢复所有被隐藏标注的快捷按钮
        self.btn_restore_visible = QPushButton("恢复显示标注")
        self.btn_restore_visible.setObjectName("BtnTool")
        self.btn_restore_visible.setStyleSheet(btn_tool_qss)
        self.btn_restore_visible.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restore_visible.setToolTip(
            "【一键恢复所有标注显示】\n"
            "• 功能: 恢复所有因鼠标单击而被临时隐藏/消隐的焊点与桥连缺陷标注\n"
            "• 快捷键: 键盘按 Esc 键亦可随时一键恢复全部显示\n"
            "• 说明: 单击缺陷可单独隐藏以透视底图原貌，点击此按钮可全部复原"
        )
        self.btn_restore_visible.clicked.connect(self._handle_restore_annotations)
        layout.addWidget(self.btn_restore_visible)

        layout.addStretch()

        # 视口快捷操作指南 (精炼提示 + 悬停完整手势浮窗，彻底消除右侧边界截断)
        self.lbl_hint = QLabel("提示: 滚轮缩放 | 拖拽平移 | 空格对比原图 | Esc恢复隐藏标注")
        self.lbl_hint.setStyleSheet("font-size: 11px; color: #38bdf8; font-weight: 500; padding-right: 6px;")
        self.lbl_hint.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_hint.setToolTip(
            "【视口核心快捷操作指南】\n"
            "• 鼠标滚轮 / 顶栏按钮: 缩放画面 (支持 0.1x ~ 10.0x)\n"
            "• 鼠标左键 / 右键按住拖拽: 自由平移画布\n"
            "• 空格键 (按住/松开): 极速闪现对比 X 光纯净原图\n"
            "• 鼠标单击任意焊球/桥连: 独立切换该标注隐藏/显示\n"
            "• 顶栏【恢复显示标注】或按 Esc 键: 一键恢复所有被隐藏的标注\n"
            "• 选中缺陷焊点按 R 键: 极速排除误检或恢复"
        )
        layout.addWidget(self.lbl_hint)

        parent_layout.addWidget(toolbar_frame)

    # ==============================================================
    # ================= 🌟 [顶栏响应式自适应] ======================
    # ==============================================================
    def _set_toolbar_tier(self, tier: str):
        """应用顶栏显示档位: "wide" 全量 / "mid" 收起提示 / "narrow" 折叠按钮+短语"""
        wide = tier == "wide"
        mid = tier in ("wide", "mid")

        # 1. 右侧快捷提示（占宽最大，优先收起）
        self.lbl_hint.setVisible(wide)

        # 2. 视口辅助按钮：常用缩放类始终保留，低频项在窄带折叠进「更多 ▾」
        for btn in (self.btn_fit, self.btn_zoom_in, self.btn_zoom_out):
            btn.setVisible(True)
        for btn in (self.btn_1to1, self.btn_restore_visible):
            btn.setVisible(mid)
        self.lbl_sep.setVisible(True)
        self.lbl_sep2.setVisible(mid)
        self.btn_more.setVisible(not mid)

        # 3. 文案长短自适应（窄带用短语，杜绝单选文字被裁切）
        self.lbl_mode_prefix.setVisible(mid)
        if mid:
            self.btn_view_outline.setText("全部细轮廓 (默认)")
            self.btn_view_defect.setText("仅高亮缺陷")
            self.btn_view_raw.setText("纯原图")
            self.lbl_alpha.setText("| 标注透明度:")
        else:
            self.btn_view_outline.setText("细轮廓")
            self.btn_view_defect.setText("高亮缺陷")
            self.btn_view_raw.setText("纯原图")
            self.lbl_alpha.setText("| 透明度:")

    def _apply_toolbar_responsive(self, width: int = None):
        """按当前宽度自动挑选最合适的顶栏档位：从最全开始逐级降级，直到放得下为止。"""
        if not hasattr(self, "btn_more"):
            return
        w = int(width if width is not None else self.width())
        for tier in ("wide", "mid", "narrow"):
            self._set_toolbar_tier(tier)
            # activate() 强制重算布局，否则 totalSizeHint 会返回上一档的缓存值
            self._toolbar_layout.activate()
            if self._toolbar_layout.totalSizeHint().width() <= w - 4:
                break

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_toolbar_responsive(event.size().width())


    def _create_status_bar(self, parent_layout: QVBoxLayout):
        status_frame = QFrame()
        status_frame.setObjectName("BottomStatusBar")
        status_frame.setStyleSheet("""
            QFrame#BottomStatusBar {
                background-color: #0b0f19;
                border-top: 1px solid #1e293b;
                padding: 4px 10px;
            }
        """)

        layout = QHBoxLayout(status_frame)
        layout.setContentsMargins(10, 2, 2, 2)
        layout.setSpacing(10)

        self.lbl_status_msg = QLabel("系统就绪: 请导入待检图片...")
        self.lbl_status_msg.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self.lbl_status_msg, stretch=1)

        # 硬件状态常驻胶囊指示器
        self.lbl_hw_badge = QLabel("硬件自适应中...")
        self.lbl_hw_badge.setStyleSheet("color: #10b981; font-size: 11px; font-weight: bold; padding: 2px 8px; background-color: #161e31; border-radius: 4px; border: 1px solid #1e293b;")
        self.lbl_hw_badge.setToolTip("计算硬件状态 (系统全自动智能感知调度)")
        layout.addWidget(self.lbl_hw_badge)

        self.lbl_zoom = QLabel("缩放: --%")
        self.lbl_zoom.setStyleSheet("color: #64748b; font-size: 11px; min-width: 70px;")
        layout.addWidget(self.lbl_zoom)

        # 批量进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(160)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # 6. 专属高灵敏右下角缩放手柄 (CornerGripWidget)
        self.size_grip = CornerGripWidget(self, status_frame)
        if self.isMaximized():
            self.size_grip.hide()
        layout.addWidget(self.size_grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        parent_layout.addWidget(status_frame)

    def _load_stylesheet(self):
        # 兼容源码与打包冻结环境的多路径回退探测
        search_dirs = []
        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", "")
            if meipass:
                search_dirs.append(os.path.join(meipass, "desktop_app", "ui", "styles"))
                search_dirs.append(os.path.join(meipass, "styles"))
            exe_dir = os.path.dirname(sys.executable)
            search_dirs.append(os.path.join(exe_dir, "styles"))
            search_dirs.append(os.path.join(exe_dir, "desktop_app", "ui", "styles"))
        search_dirs.append(os.path.join(os.path.dirname(__file__), "styles"))

        target_qss = None
        target_dir = None
        for d in search_dirs:
            candidate = os.path.join(d, "dark_industrial.qss")
            if os.path.exists(candidate):
                target_qss = candidate
                target_dir = d
                break

        if target_qss and os.path.exists(target_qss):
            try:
                with open(target_qss, "r", encoding="utf-8") as f:
                    content = f.read()
                    arrow_icon = os.path.join(target_dir, "arrow_down.png").replace("\\", "/")
                    content = content.replace("url(arrow_down.png)", f"url({arrow_icon})")
                    app_inst = QApplication.instance()
                    if app_inst:
                        app_inst.setStyleSheet(content)
                    self.setStyleSheet(content)
            except Exception as e:
                print(f"[WARN] 加载样式表异常: {e}")

    # ==============================================================
    # ================= 🌟 [信号槽事件绑定] =========================
    # ==============================================================
    def _connect_signals(self):
        # 视口与缩放联动
        self.canvas.sig_zoom_changed.connect(lambda z: self.lbl_zoom.setText(f"缩放: {int(z * 100)}%"))
        self.canvas.sig_ball_selected.connect(self.panel_defect_table.select_ball)
        self.canvas.sig_crop_confirmed.connect(self._handle_crop_confirmed)
        self.canvas.sig_crop_cancelled.connect(lambda: self.panel_control.show_crop_actions(False))

        # 批量图像胶卷选择联动
        self.thumbnail_bar.sig_image_selected.connect(self._handle_user_selected_image)

        # 控制面板交互
        self.panel_control.sig_open_image.connect(self.load_image)
        self.panel_control.sig_open_folder.connect(self.load_folder)
        self.panel_control.sig_enter_crop.connect(self._handle_enter_crop)
        self.panel_control.sig_confirm_crop.connect(self.canvas.confirm_crop)
        self.panel_control.sig_cancel_crop.connect(self.canvas.cancel_crop)
        self.panel_control.sig_reset_image.connect(self._reset_to_original_image)
        self.panel_control.sig_start_inspection.connect(self.start_inspection)
        self.panel_control.sig_stop_inspection.connect(self.stop_inspection)
        self.panel_control.sig_export_pdf.connect(self.export_pdf)
        self.panel_control.sig_export_excel.connect(self.export_excel)

        # 参数面板动态重算与硬件联动
        self.panel_param.sig_threshold_changed.connect(self._handle_threshold_changed)
        self.panel_param.sig_alpha_synced.connect(self._sync_alpha_from_config)
        self.panel_param.sig_config_changed.connect(self._handle_model_config_changed)
        self.panel_param.sig_hardware_updated.connect(self._on_hardware_updated)
        self.panel_param._refresh_hardware_status()

        # 表格联动聚焦 (单击立即平移居中定位并显示超醒目金黄十字准星，若-1则取消；双击深度特写放大)
        self.panel_defect_table.sig_ball_selected.connect(
            lambda idx: self.canvas.highlight_ball(idx, zoom_to=True, min_zoom=1.2)
        )
        self.panel_defect_table.sig_ball_focus_requested.connect(
            lambda idx: self.canvas.highlight_ball(idx, zoom_to=True, min_zoom=1.8)
        )

        # 人工复核交互信号联动 (画布图元右键/快捷键R/表格操作按钮/表格右键)
        self.canvas.sig_ball_review_toggled.connect(self._handle_ball_review_toggled)
        self.canvas.sig_bridge_review_toggled.connect(self._handle_bridge_review_toggled)
        self.panel_defect_table.sig_ball_review_toggled.connect(self._handle_ball_review_toggled)
        self.canvas.sig_annotations_restored.connect(lambda n: self._handle_restore_annotations())


    def _on_hardware_updated(self, text: str, color: str):
        """同步硬件感知状态至底部状态栏常驻指示器"""
        if hasattr(self, "lbl_hw_badge"):
            self.lbl_hw_badge.setText(text)
            self.lbl_hw_badge.setStyleSheet(
                f"color: {color}; font-size: 11px; font-weight: bold; padding: 2px 8px; "
                f"background-color: #161e31; border-radius: 4px; border: 1px solid #1e293b;"
            )

    # ==============================================================
    # ================= 🌟 [业务功能实现] ===========================
    # ==============================================================
    def load_image(self, file_path: str):
        """加载单张 X-Ray 图像"""
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "错误", f"图片不存在: {file_path}")
            return

        mat = load_image_unicode(file_path)
        if mat is None:
            QMessageBox.critical(self, "读取失败", f"无法解析图像文件: {file_path}")
            return

        self.batch_files = [file_path]
        self.batch_results.clear()
        self.batch_review_overrides.clear()
        self.crop_temp_map.clear()
        self.is_image_cropped = False
        self.current_batch_index = 0
        self.thumbnail_bar.hide()

        self.current_img_path = file_path
        self.original_cv_mat = mat.copy()
        self.active_cv_mat = mat.copy()

        self.canvas.set_image_mat(self.active_cv_mat)
        h, w = mat.shape[:2]
        self.panel_control.set_current_filename(os.path.basename(file_path), width=w, height=h)
        self.panel_control.btn_reset_img.hide()
        self.panel_control.show_crop_actions(False)

        # 清空上一张的统计与明细
        self.session = InspectionSession()
        self.panel_result.update_summary(self.session.get_summary_stats())
        self.panel_defect_table.load_data([])
        self.panel_control.set_dirty_state(False)
        self.lbl_status_msg.setText(f"已加载单张图片: {os.path.basename(file_path)} ({w} x {h} px)")

    def load_folder(self, folder_path: str):
        """导入整个文件夹进行批量质检"""
        exts = (".jpg", ".jpeg", ".png", ".bmp", ".tif")
        all_files = [
            os.path.join(folder_path, f)
            for f in sorted(os.listdir(folder_path))
            if f.lower().endswith(exts)
        ]
        if not all_files:
            QMessageBox.information(self, "提示", "所选目录中未找到支持的图像文件")
            return

        self.current_folder_name = os.path.basename(os.path.abspath(folder_path))
        self.batch_files = all_files
        self.batch_results.clear()
        self.batch_review_overrides.clear()

        self.crop_temp_map.clear()
        self.is_image_cropped = False
        self.thumbnail_bar.show()
        self.thumbnail_bar.load_images(self.batch_files)
        self.navigate_to_image(0)
        self.lbl_status_msg.setText(f"已就绪批量检测队列: 共 {len(all_files)} 张图像 (支持点击胶卷或键盘 ← / → 快速切图)")

    def navigate_to_image(self, index: int, during_inspection: bool = False):
        """平滑切换至指定序号的工件图像及检测结果"""
        if index < 0 or index >= len(self.batch_files):
            return

        self.current_batch_index = index
        target_path = self.batch_files[index]
        self.current_img_path = target_path
        self.is_image_cropped = False

        mat = load_image_unicode(target_path)
        if mat is None:
            return
        self.original_cv_mat = mat.copy()
        self.active_cv_mat = mat.copy()

        h, w = mat.shape[:2]
        self.panel_control.set_current_filename(os.path.basename(target_path), width=w, height=h)
        self.panel_control.btn_reset_img.hide()
        self.panel_control.show_crop_actions(False)

        # 设置底图 (Canvas 会自动触发 fit_in_view，无滚动条舒展全屏)
        self.canvas.set_image_mat(self.active_cv_mat)

        # 判断该图像是否已有检测结果
        matched_result = None
        for p, r in self.batch_results.items():
            if _same_file_path(p, target_path):
                matched_result = r
                break

        if matched_result is not None:
            self.session.load_from_pipeline_result(
                image_path=target_path,
                raw_mat=self.active_cv_mat,
                result=matched_result,
                ng_void_thresh=self.config.ng_void_threshold,
                undersize_thresh=self.config.undersize_threshold,
            )
            self.session.elapsed_ms = matched_result.get("elapsed_ms", 0.0)

            # 恢复当前工件历史人工复核记录 (按需抽查记录不丢失)
            cached_rev = self.batch_review_overrides.get(target_path, {})
            if cached_rev:
                for b_idx, stat in cached_rev.get("balls", {}).items():
                    self.session.manual_review_ball(b_idx, stat)
                for br_idx in cached_rev.get("bridges", set()):
                    self.session.manual_review_bridge(br_idx, True)
                self.session.re_evaluate(self.config.ng_void_threshold, self.config.undersize_threshold)

            # 视口加载矢量标注
            self.canvas.load_inspection_overlay(
                records=self.session.solder_records,
                bridge_defects=self.session.bridge_defects,
                view_mode=self.config.view_mode,
                alpha=self.config.overlay_alpha,
            )
            # 刷新看板与明细表格
            self.panel_result.update_summary(self.session.get_summary_stats())
            self.panel_defect_table.load_data(self.session.solder_records)
            # 保证该卡片状态与 session.board_status 保持严格一致
            self.thumbnail_bar.set_item_status(index, self.session.board_status)

        else:
            # 尚未检测完成（待检状态或质检进行中尚未出结果）
            self.session = InspectionSession()
            self.panel_result.update_summary(self.session.get_summary_stats())
            self.panel_defect_table.load_data([])

        self.thumbnail_bar.set_current_index(index, scroll_to=True)
        if not during_inspection:
            if self.worker and self.worker.isRunning():
                self.lbl_status_msg.setText(
                    f"已锁定浏览 [{index + 1}/{len(self.batch_files)}]: {os.path.basename(target_path)} (后台批量质检运行中)"
                )
            else:
                self.lbl_status_msg.setText(f"已切换图像 [{index + 1}/{len(self.batch_files)}]: {os.path.basename(target_path)}")

    def _handle_user_selected_image(self, index: int):
        """处理用户在胶卷栏中手动点击卡片切图 (用户主动切图即锁定视口，不再自动跳转)"""
        if self.worker and self.worker.isRunning():
            # 若用户主动点击的是当前正处于 inspecting 状态的卡片，恢复跟随；否则锁定在用户所选工件上，绝不自动切走
            self.is_auto_follow_inspection = (index == self.current_inspecting_index)
        self.navigate_to_image(index, during_inspection=False)

    def keyPressEvent(self, event: QKeyEvent):
        """全局键盘切图快捷键支持 (← 上一张, → 下一张, Esc 恢复隐藏标注)"""
        if event.key() == Qt.Key.Key_Left:
            if len(self.batch_files) > 1 and self.current_batch_index > 0:
                if self.worker and self.worker.isRunning():
                    self.is_auto_follow_inspection = False
                self.navigate_to_image(self.current_batch_index - 1)
                event.accept()
                return
        elif event.key() == Qt.Key.Key_Right:
            if len(self.batch_files) > 1 and self.current_batch_index < len(self.batch_files) - 1:
                if self.worker and self.worker.isRunning():
                    self.is_auto_follow_inspection = False
                self.navigate_to_image(self.current_batch_index + 1)
                event.accept()
                return
        elif event.key() == Qt.Key.Key_Escape:
            self._handle_restore_annotations()
            event.accept()
            return
        super().keyPressEvent(event)

    def _handle_restore_annotations(self):
        """一键恢复所有被手动点击消隐的缺陷标注显示"""
        restored = self.canvas.restore_all_annotations_visibility()
        if hasattr(self, "session"):
            self.session.reset_all_visibility()
        if restored > 0:
            self.lbl_status_msg.setText(f"已恢复 {restored} 处手动消隐的缺陷标注显示 (所有标注已就绪)")
        else:
            self.lbl_status_msg.setText("所有焊点与缺陷标注均已处于显示状态")

    def _handle_enter_crop(self):
        """进入 ROI 裁剪模式前安全检查"""
        if self.active_cv_mat is None:
            QMessageBox.information(self, "提示", "请先打开待检测的 X射线 图像，再进行 ROI 裁剪")
            self.panel_control.show_crop_actions(False)
            return
        self.canvas.enter_crop_mode()
        self.panel_control.show_crop_actions(True)

    def _handle_crop_confirmed(self, crop_rect: tuple[int, int, int, int]):
        """执行图像裁剪"""
        if self.original_cv_mat is None:
            return
        cropped = crop_image_rect(self.original_cv_mat, crop_rect)
        self.active_cv_mat = cropped
        self.is_image_cropped = True
        self.canvas.set_image_mat(self.active_cv_mat)
        self.panel_control.show_crop_actions(False)
        self.panel_control.btn_reset_img.show()
        cw = crop_rect[2] - crop_rect[0]
        ch = crop_rect[3] - crop_rect[1]
        self.panel_control.set_current_filename(f"{os.path.basename(self.current_img_path)} (已裁剪)", width=cw, height=ch)
        self.lbl_status_msg.setText(f"裁剪完成: {cw} × {ch} px")

    def _reset_to_original_image(self):
        """撤销裁剪恢复全图"""
        if self.original_cv_mat is not None:
            self.active_cv_mat = self.original_cv_mat.copy()
            self.is_image_cropped = False
            self.canvas.set_image_mat(self.active_cv_mat)
            self.panel_control.btn_reset_img.hide()
            h, w = self.original_cv_mat.shape[:2]
            self.panel_control.set_current_filename(os.path.basename(self.current_img_path), width=w, height=h)
            self.lbl_status_msg.setText("已恢复完整原始全图")

    def start_inspection(self):
        """触发深度学习质检"""
        if self.active_cv_mat is None:
            QMessageBox.warning(self, "提示", "请先打开待检测的 X射线 图像")
            return

        if len(self.batch_files) > 1:
            queue = list(self.batch_files)
        else:
            # 若是单图且进行了裁剪，写入临时文件传递给算法
            if self.is_image_cropped:
                temp_dir = tempfile.gettempdir()
                temp_path = os.path.join(temp_dir, f"xray_crop_{os.path.basename(self.current_img_path)}")
                cv2.imencode(".jpg", self.active_cv_mat)[1].tofile(temp_path)
                self.crop_temp_map[temp_path] = self.current_img_path
                target_path = temp_path
            else:
                target_path = self.current_img_path
            queue = [target_path]

        self.panel_control.set_running_state(True)
        self.panel_control.set_dirty_state(False)
        self.progress_bar.show()
        self.progress_bar.setRange(0, len(queue))
        self.progress_bar.setValue(0)
        self.is_auto_follow_inspection = True
        self.current_inspecting_index = 0

        # 启动工作线程
        self.worker = InspectionWorker(queue, self.config, self)
        self.worker.sig_started.connect(self._handle_worker_started)
        self.worker.sig_progress.connect(self._handle_worker_progress)
        self.worker.sig_single_finished.connect(self._handle_single_result)
        self.worker.sig_batch_finished.connect(self._handle_batch_finished)
        self.worker.sig_error.connect(lambda f, e: QMessageBox.critical(self, "质检出错", f"{f} 发生错误: {e}"))
        self.worker.sig_log.connect(lambda m: self.lbl_status_msg.setText(m))
        self.worker.start()

    def stop_inspection(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.is_auto_follow_inspection = False

    def _handle_worker_started(self, img_path: str):
        orig_path = self.crop_temp_map.get(img_path, img_path)
        for idx, fp in enumerate(self.batch_files):
            if _same_file_path(fp, orig_path):
                self.current_inspecting_index = idx
                self.thumbnail_bar.set_item_status(idx, "inspecting")
                # 只有在保持“实时跟随”模式下，才自动将主视口切换至当前正在质检的图像
                if self.is_auto_follow_inspection:
                    self.navigate_to_image(idx, during_inspection=True)
                break

        if self.is_auto_follow_inspection:
            self.lbl_status_msg.setText(f"正在质检: {os.path.basename(orig_path)}...")
        else:
            cur_name = os.path.basename(self.current_img_path) if self.current_img_path else ""
            self.lbl_status_msg.setText(
                f"后台正在质检: {os.path.basename(orig_path)} | 视口已锁定查看: {cur_name}"
            )

    def _handle_worker_progress(self, current: int, total: int, filename: str):
        self.progress_bar.setValue(current)

    def _handle_single_result(self, result: dict):
        """单张质检完成，保存结果并动态刷新"""
        raw_path = result.get("input_image_path", self.current_img_path)
        img_path = self.crop_temp_map.get(raw_path, raw_path)
        result["input_image_path"] = img_path
        self.batch_results[img_path] = result

        # 核心判定修复：根据当前设定的算法判废阈值，精确重算该图最终质量状态 (PASS / NG)
        temp_session = InspectionSession()
        temp_session.load_from_pipeline_result(
            image_path=img_path,
            raw_mat=self.active_cv_mat if _same_file_path(img_path, self.current_img_path) else None,
            result=result,
            ng_void_thresh=self.config.ng_void_threshold,
            undersize_thresh=self.config.undersize_threshold,
        )
        status_str = temp_session.board_status  # "PASS" 或 "NG"，与看板结果 100% 严格一致

        for idx, fp in enumerate(self.batch_files):
            if _same_file_path(fp, img_path):
                self.thumbnail_bar.set_item_status(idx, status_str)
                break

        # 如果当前视口正停留在该图像上，立即渲染矢量标注与数据
        if _same_file_path(img_path, self.current_img_path):
            self.session = temp_session
            self.session.elapsed_ms = result.get("elapsed_ms", 0.0)

            # 1. 视口加载矢量图元 (低遮挡细轮廓)
            self.canvas.load_inspection_overlay(
                records=self.session.solder_records,
                bridge_defects=self.session.bridge_defects,
                view_mode=self.config.view_mode,
                alpha=self.config.overlay_alpha,
            )

            # 2. 刷新右侧 PASS/NG 胶囊卡片
            stats = self.session.get_summary_stats()
            self.panel_result.update_summary(stats)

            # 3. 刷新明细表格
            self.panel_defect_table.load_data(self.session.solder_records)

    def _handle_batch_finished(self, results_list: list):
        self.panel_control.set_running_state(False)
        self.progress_bar.hide()
        self.is_auto_follow_inspection = False
        self.current_inspecting_index = -1
        pass_count = sum(1 for c in self.thumbnail_bar.cards if c.status.startswith("PASS"))
        ng_count = sum(1 for c in self.thumbnail_bar.cards if c.status == "NG")
        self.lbl_status_msg.setText(f"批量质检全部完成: 共 {len(self.thumbnail_bar.cards)} 张 | 合格 {pass_count} 张 | 缺陷 {ng_count} 张")

    # ==============================================================
    # ================= 🌟 [人工复核误检消除与闭环联动] =============
    # ==============================================================
    def _handle_ball_review_toggled(self, ball_index: int):
        """处理焊点人工复核切换 (误检转合格 / 撤销恢复)"""
        if not self.session.solder_records:
            return

        is_now_pass = self.session.toggle_ball_review(ball_index)
        self.session.re_evaluate(self.config.ng_void_threshold, self.config.undersize_threshold)

        # 缓存当前图像的复核记录，确保切图来回不丢失
        cur_path = self.current_img_path
        if cur_path not in self.batch_review_overrides:
            self.batch_review_overrides[cur_path] = {"balls": {}, "bridges": set()}
        if is_now_pass:
            self.batch_review_overrides[cur_path]["balls"][ball_index] = "PASS"
        else:
            self.batch_review_overrides[cur_path]["balls"].pop(ball_index, None)

        # 同步双向桥连缓存状态
        for b_idx, b in enumerate(self.session.bridge_defects):
            if b.get("is_reviewed_pass", False):
                self.batch_review_overrides[cur_path]["bridges"].add(b_idx)
            else:
                self.batch_review_overrides[cur_path]["bridges"].discard(b_idx)

        # 联动视口图元、判定看板与明细表格
        self.canvas.refresh_solder_items()
        stats = self.session.get_summary_stats()
        self.panel_result.update_summary(stats)
        self.panel_defect_table.refresh_table()

        # 同步更新当前缩略图胶卷卡片徽标状态
        if 0 <= self.current_batch_index < len(self.thumbnail_bar.cards):
            card_status = self.session.board_status
            self.thumbnail_bar.set_item_status(self.current_batch_index, card_status)

        action_name = "已排除误检 (标记合格)" if is_now_pass else "已撤销复核 (恢复为AI判决)"
        self.lbl_status_msg.setText(
            f"焊球 #{ball_index} {action_name} | 当前有效不良: {stats['total_ng_balls']} 处 | 已排除误检: {stats['manual_cleared_count']} 处"
        )

    def _handle_bridge_review_toggled(self, bridge_index: int):
        """处理桥连短路缺陷人工复核 (误检排除 / 撤销恢复)"""
        if not self.session.bridge_defects or bridge_index >= len(self.session.bridge_defects):
            return

        b = self.session.bridge_defects[bridge_index]
        curr = b.get("is_reviewed_pass", False)
        new_state = not curr
        self.session.manual_review_bridge(bridge_index, new_state)
        self.session.re_evaluate(self.config.ng_void_threshold, self.config.undersize_threshold)

        cur_path = self.current_img_path
        if cur_path not in self.batch_review_overrides:
            self.batch_review_overrides[cur_path] = {"balls": {}, "bridges": set()}
        if new_state:
            self.batch_review_overrides[cur_path]["bridges"].add(bridge_index)
        else:
            self.batch_review_overrides[cur_path]["bridges"].discard(bridge_index)

        self.canvas.refresh_solder_items()
        stats = self.session.get_summary_stats()
        self.panel_result.update_summary(stats)
        self.panel_defect_table.refresh_table()

        if 0 <= self.current_batch_index < len(self.thumbnail_bar.cards):
            self.thumbnail_bar.set_item_status(self.current_batch_index, self.session.board_status)

        action_name = "已排除桥连误检 (标记非短路)" if new_state else "已撤销复核 (恢复桥连判定)"
        self.lbl_status_msg.setText(f"桥连短路缺陷 #{bridge_index + 1} {action_name}")

    # ==============================================================
    # ================= 🌟 [动态阈值毫秒级重判] =====================
    # ==============================================================
    def _handle_threshold_changed(self, ng_void_thresh: float, undersize_thresh: float):

        if not self.session.solder_records:
            return
        # 1. 内存重算当前查看的图像会话
        self.session.re_evaluate(ng_void_thresh, undersize_thresh)
        self.canvas.refresh_solder_items()
        self.panel_result.update_summary(self.session.get_summary_stats())
        self.panel_defect_table.refresh_table()

        # 2. 联动刷新所有已完成检测的批量卡片 PASS/NG 状态
        for idx, fp in enumerate(self.batch_files):
            cached_res = None
            for p, r in self.batch_results.items():
                if _same_file_path(p, fp):
                    cached_res = r
                    break
            if cached_res is not None:
                tmp = InspectionSession()
                tmp.load_from_pipeline_result(
                    image_path=fp,
                    raw_mat=None,
                    result=cached_res,
                    ng_void_thresh=ng_void_thresh,
                    undersize_thresh=undersize_thresh,
                )
                # 恢复该工件的历史人工复核记录
                cached_rev = {}
                for rev_p, rev_v in self.batch_review_overrides.items():
                    if _same_file_path(rev_p, fp):
                        cached_rev = rev_v
                        break
                if cached_rev:
                    for b_idx, stat in cached_rev.get("balls", {}).items():
                        tmp.manual_review_ball(b_idx, stat)
                    for br_idx in cached_rev.get("bridges", set()):
                        tmp.manual_review_bridge(br_idx, True)
                    tmp.re_evaluate(ng_void_thresh, undersize_thresh)

                self.thumbnail_bar.set_item_status(idx, tmp.board_status)

    def _handle_model_config_changed(self):
        """当模型置信度或检测模式发生修改时触发 (脏状态管理)"""
        if self.session.solder_records:
            self.panel_control.set_dirty_state(True)
            self.lbl_status_msg.setText("[提示] 质检模式或置信度已修改，当前显示为历史结果，请点击【重新执行质检】生效")
        else:
            self._handle_threshold_changed(self.config.ng_void_threshold, self.config.undersize_threshold)

    def _on_view_mode_changed(self, mode: str):
        self.config.view_mode = mode
        self.canvas.set_view_mode(mode)

    def _sync_view_mode_from_config(self):
        """启动时把 settings.json 里持久化的视图模式同步到单选按钮与画布，保证二者一致。"""
        mode = str(self.config.view_mode or "all_outline")
        btn = {
            "all_outline": self.btn_view_outline,
            "defect_only": self.btn_view_defect,
            "raw_image": self.btn_view_raw,
        }.get(mode)
        if btn is None:
            mode = "all_outline"
            btn = self.btn_view_outline
        if not btn.isChecked():
            btn.setChecked(True)   # 会触发 toggled -> _on_view_mode_changed
        self.canvas.set_view_mode(mode)
        self.config.view_mode = mode

    def _on_alpha_slider_changed(self, val: int):
        self.spin_alpha.blockSignals(True)
        self.spin_alpha.setValue(float(val))
        self.spin_alpha.blockSignals(False)

        alpha = val / 100.0
        self.config.overlay_alpha = alpha
        self.canvas.set_overlay_alpha(alpha)

    def _on_alpha_spin_changed(self, val: float):
        slider_val = int(round(val))
        self.slider_alpha.blockSignals(True)
        self.slider_alpha.setValue(slider_val)
        self.slider_alpha.blockSignals(False)

        alpha = slider_val / 100.0
        self.config.overlay_alpha = alpha
        self.canvas.set_overlay_alpha(alpha)

    def _sync_alpha_from_config(self, alpha: float):
        """当载入外部配方或重置默认配置时，自动同步更新顶栏透明度滑块与步进输入框"""
        self.slider_alpha.blockSignals(True)
        self.spin_alpha.blockSignals(True)
        self.slider_alpha.setValue(int(alpha * 100))
        self.spin_alpha.setValue(alpha * 100.0)
        self.slider_alpha.blockSignals(False)
        self.spin_alpha.blockSignals(False)
        self.canvas.set_overlay_alpha(alpha)

    # ==============================================================
    # ================= 🌟 [双模报告导出] ===========================
    # ==============================================================
    def _collect_completed_batch_items(self) -> list[dict]:
        """收集所有已完成质检的工件数据列表 (严格保持 batch_files 队列顺序)"""
        items = []
        for fp in self.batch_files:
            # 1. 若当前视口正停留在该图且已有结果，优先直接取当前活跃 session (包含最新交互复核修改)
            if (
                self.session
                and self.session.solder_records
                and _same_file_path(fp, self.current_img_path)
            ):
                items.append({
                    "image_name": os.path.basename(fp),
                    "image_path": fp,
                    "summary_stats": self.session.get_summary_stats(),
                    "records": list(self.session.solder_records),
                    "bridge_defects": list(self.session.bridge_defects),
                    "preview_img_path": self.session.inspected_image_path or fp,
                })
                continue

            # 2. 从 self.batch_results 查找该图历史检测结果
            cached_res = None
            for p, r in self.batch_results.items():
                if _same_file_path(p, fp):
                    cached_res = r
                    break

            if cached_res is not None:
                tmp_sess = InspectionSession()
                tmp_sess.load_from_pipeline_result(
                    image_path=fp,
                    raw_mat=None,
                    result=cached_res,
                    ng_void_thresh=self.config.ng_void_threshold,
                    undersize_thresh=self.config.undersize_threshold,
                )
                tmp_sess.elapsed_ms = cached_res.get("elapsed_ms", 0.0)

                # 恢复该工件的人工复核覆盖记录 (支持路径大小写与正反斜杠鲁棒匹配)
                cached_rev = {}
                for rev_p, rev_v in self.batch_review_overrides.items():
                    if _same_file_path(rev_p, fp):
                        cached_rev = rev_v
                        break

                if cached_rev:
                    for b_idx, stat in cached_rev.get("balls", {}).items():
                        tmp_sess.manual_review_ball(b_idx, stat)
                    for br_idx in cached_rev.get("bridges", set()):
                        tmp_sess.manual_review_bridge(br_idx, True)
                    tmp_sess.re_evaluate(self.config.ng_void_threshold, self.config.undersize_threshold)

                preview_path = tmp_sess.inspected_image_path
                if not preview_path or not os.path.exists(preview_path):
                    preview_path = cached_res.get("visual_output_path")
                if not preview_path or not os.path.exists(preview_path):
                    preview_path = fp

                items.append({
                    "image_name": os.path.basename(fp),
                    "image_path": fp,
                    "summary_stats": tmp_sess.get_summary_stats(),
                    "records": list(tmp_sess.solder_records),
                    "bridge_defects": list(tmp_sess.bridge_defects),
                    "preview_img_path": preview_path,
                })

        return items

    def export_pdf(self):
        completed_items = self._collect_completed_batch_items()
        if not completed_items:
            # 兜底：若 batch_files 尚未同步但当前 session 已有数据
            if self.session and self.session.solder_records and self.current_img_path:
                completed_items = [{
                    "image_name": os.path.basename(self.current_img_path),
                    "image_path": self.current_img_path,
                    "summary_stats": self.session.get_summary_stats(),
                    "records": list(self.session.solder_records),
                    "bridge_defects": list(self.session.bridge_defects),
                    "preview_img_path": self.session.inspected_image_path or self.current_img_path,
                }]
            else:
                QMessageBox.information(self, "提示", "请先执行质检任务，产生结果后再导出报告")
                return

        # 判定是否为批量导出场景
        is_batch = len(self.batch_files) > 1 and len(completed_items) > 1
        if is_batch:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("导出 PDF 质检单")
            msg_box.setText(
                f"当前批量检测队列共完成 {len(completed_items)} / {len(self.batch_files)} 张工件质检。\n\n"
                "请选择导出方式："
            )
            btn_batch = msg_box.addButton(f"批量合并导出 ({len(completed_items)} 张合并为单份 PDF)", QMessageBox.ButtonRole.AcceptRole)
            btn_single = msg_box.addButton("仅导出当前工件单图", QMessageBox.ButtonRole.ActionRole)
            btn_cancel = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            msg_box.setDefaultButton(btn_batch)
            msg_box.exec()

            clicked = msg_box.clickedButton()
            if clicked == btn_cancel:
                return
            export_as_batch = (clicked == btn_batch)
        else:
            export_as_batch = False

        if export_as_batch:
            now_tag = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"X射线_Batch_Report_{now_tag}.pdf"
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "批量合并导出 PDF 工业质检单",
                default_name,
                "PDF 文档 (*.pdf)"
            )
            if save_path:
                from PySide6.QtWidgets import QApplication, QProgressDialog
                from PySide6.QtCore import Qt

                progress = QProgressDialog("正在准备导出批量 PDF 报告...", None, 0, len(completed_items) + 1, self)
                progress.setWindowTitle("导出 PDF 质检单")
                progress.setWindowModality(Qt.WindowModality.WindowModal)
                progress.setMinimumDuration(0)
                progress.setValue(0)
                progress.show()
                QApplication.processEvents()

                def on_pdf_progress(cur, total, msg):
                    progress.setMaximum(total)
                    progress.setValue(cur)
                    progress.setLabelText(msg)
                    self.lbl_status_msg.setText(msg)
                    QApplication.processEvents()

                try:
                    folder_name = getattr(self, "current_folder_name", "")
                    if not folder_name and self.batch_files:
                        folder_name = os.path.basename(os.path.dirname(os.path.abspath(self.batch_files[0])))
                    if not folder_name:
                        folder_name = "X射线 批量工件"

                    # 注入当前判废门限参数
                    cur_params = self.param_panel.get_params() if hasattr(self, "param_panel") and self.param_panel else {}
                    v_th = cur_params.get("void_area_thresh", getattr(self.session, "void_thresh", 0.15))
                    r_th = cur_params.get("reduction_thresh", getattr(self.session, "reduction_thresh", 0.20))
                    for it in completed_items:
                        if "summary_stats" in it:
                            it["summary_stats"]["void_threshold"] = v_th
                            it["summary_stats"]["reduction_threshold"] = r_th

                    export_batch_inspection_pdf(
                        save_path=save_path,
                        batch_items=completed_items,
                        batch_product_name=folder_name,
                        progress_callback=on_pdf_progress,
                    )
                    progress.close()
                    self.lbl_status_msg.setText(f"批量 PDF 报告导出完成: {os.path.basename(save_path)}")
                    QMessageBox.information(
                        self,
                        "导出成功",
                        f"已成功将 {len(completed_items)} 张工件质检单合并导出至单份 PDF 文件:\n{save_path}"
                    )
                except Exception as e:
                    progress.close()
                    QMessageBox.critical(self, "导出失败", f"批量生成 PDF 报告失败: {e}")
        else:
            # 单图导出
            if not self.session.solder_records:
                QMessageBox.information(self, "提示", "当前工件尚未产生质检结果，请先执行质检")
                return
            cur_name = os.path.splitext(os.path.basename(self.current_img_path))[0]
            default_name = f"X射线_Report_{cur_name}.pdf"
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "导出 PDF 工业质检单",
                default_name,
                "PDF 文档 (*.pdf)"
            )
            if save_path:
                from PySide6.QtWidgets import QApplication, QProgressDialog
                from PySide6.QtCore import Qt

                progress = QProgressDialog("正在生成单图 PDF 质检报告...", None, 0, 2, self)
                progress.setWindowTitle("导出 PDF 质检单")
                progress.setWindowModality(Qt.WindowModality.WindowModal)
                progress.setMinimumDuration(0)
                progress.setValue(0)
                progress.show()
                QApplication.processEvents()

                def on_single_pdf_progress(cur, total, msg):
                    progress.setMaximum(total)
                    progress.setValue(cur)
                    progress.setLabelText(msg)
                    self.lbl_status_msg.setText(msg)
                    QApplication.processEvents()

                try:
                    stats = self.session.get_summary_stats()
                    cur_params = self.param_panel.get_params() if hasattr(self, "param_panel") and self.param_panel else {}
                    stats["void_threshold"] = cur_params.get("void_area_thresh", getattr(self.session, "void_thresh", 0.15))
                    stats["reduction_threshold"] = cur_params.get("reduction_thresh", getattr(self.session, "reduction_thresh", 0.20))

                    export_inspection_pdf(
                        save_path=save_path,
                        image_name=os.path.basename(self.current_img_path),
                        summary_stats=stats,
                        records=self.session.solder_records,
                        preview_img_path=self.session.inspected_image_path,
                        image_path=self.current_img_path,
                        bridge_defects=self.session.bridge_defects,
                        progress_callback=on_single_pdf_progress,
                    )
                    progress.close()
                    QMessageBox.information(self, "导出成功", f"PDF 质检单已保存至:\n{save_path}")
                except Exception as e:
                    progress.close()
                    QMessageBox.critical(self, "导出失败", f"生成 PDF 报告失败: {e}")

    def export_excel(self):
        completed_items = self._collect_completed_batch_items()
        if not completed_items:
            # 兜底：若 batch_files 尚未同步但当前 session 已有数据
            if self.session and self.session.solder_records and self.current_img_path:
                completed_items = [{
                    "image_name": os.path.basename(self.current_img_path),
                    "image_path": self.current_img_path,
                    "summary_stats": self.session.get_summary_stats(),
                    "records": list(self.session.solder_records),
                    "preview_img_path": self.session.inspected_image_path or self.current_img_path,
                }]
            else:
                QMessageBox.information(self, "提示", "请先执行质检任务，产生结果后再导出表格")
                return

        # 判定是否为批量导出场景
        is_batch = len(self.batch_files) > 1 and len(completed_items) > 1
        if is_batch:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("导出 Excel 报表")
            msg_box.setText(
                f"当前批量检测队列共完成 {len(completed_items)} / {len(self.batch_files)} 张工件质检。\n\n"
                "请选择导出方式："
            )
            btn_batch = msg_box.addButton(f"批量合并导出 ({len(completed_items)} 张多 Sheet 合并为单一 Excel)", QMessageBox.ButtonRole.AcceptRole)
            btn_single = msg_box.addButton("仅导出当前工件单表", QMessageBox.ButtonRole.ActionRole)
            btn_cancel = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            msg_box.setDefaultButton(btn_batch)
            msg_box.exec()

            clicked = msg_box.clickedButton()
            if clicked == btn_cancel:
                return
            export_as_batch = (clicked == btn_batch)
        else:
            export_as_batch = False

        if export_as_batch:
            now_tag = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"X射线_Batch_Details_{now_tag}.xlsx"
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "批量合并导出 Excel 原始数据明细表",
                default_name,
                "Excel 工作簿 (*.xlsx)"
            )
            if save_path:
                from PySide6.QtWidgets import QApplication, QProgressDialog
                from PySide6.QtCore import Qt

                progress = QProgressDialog("正在准备导出批量 Excel 报表...", None, 0, len(completed_items) + 1, self)
                progress.setWindowTitle("导出 Excel 报表")
                progress.setWindowModality(Qt.WindowModality.WindowModal)
                progress.setMinimumDuration(0)
                progress.setValue(0)
                progress.show()
                QApplication.processEvents()

                def on_excel_progress(cur, total, msg):
                    progress.setMaximum(total)
                    progress.setValue(cur)
                    progress.setLabelText(msg)
                    self.lbl_status_msg.setText(msg)
                    QApplication.processEvents()

                try:
                    export_batch_inspection_excel(
                        save_path=save_path,
                        batch_items=completed_items,
                        progress_callback=on_excel_progress,
                    )
                    progress.close()
                    self.lbl_status_msg.setText(f"批量 Excel 报表导出完成: {os.path.basename(save_path)}")
                    QMessageBox.information(
                        self,
                        "导出成功",
                        f"已成功将 {len(completed_items)} 张工件质检数据合并导出至单一 Excel 文件 (多 Sheet 结构):\n{save_path}"
                    )
                except Exception as e:
                    progress.close()
                    QMessageBox.critical(self, "导出失败", f"批量生成 Excel 表格失败: {e}")
        else:
            # 单图导出
            if not self.session.solder_records:
                QMessageBox.information(self, "提示", "当前工件尚未产生质检结果，请先执行质检")
                return
            cur_name = os.path.splitext(os.path.basename(self.current_img_path))[0]
            default_name = f"X射线_Details_{cur_name}.xlsx"
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "导出 Excel 原始数据明细表",
                default_name,
                "Excel 工作簿 (*.xlsx)"
            )
            if save_path:
                from PySide6.QtWidgets import QApplication, QProgressDialog
                from PySide6.QtCore import Qt

                progress = QProgressDialog("正在生成单图 Excel 数据报表...", None, 0, 3, self)
                progress.setWindowTitle("导出 Excel 报表")
                progress.setWindowModality(Qt.WindowModality.WindowModal)
                progress.setMinimumDuration(0)
                progress.setValue(0)
                progress.show()
                QApplication.processEvents()

                def on_single_excel_progress(cur, total, msg):
                    progress.setMaximum(total)
                    progress.setValue(cur)
                    progress.setLabelText(msg)
                    self.lbl_status_msg.setText(msg)
                    QApplication.processEvents()

                try:
                    export_inspection_excel(
                        save_path=save_path,
                        image_name=os.path.basename(self.current_img_path),
                        summary_stats=self.session.get_summary_stats(),
                        records=self.session.solder_records,
                        progress_callback=on_single_excel_progress,
                    )
                    progress.close()
                    QMessageBox.information(self, "导出成功", f"Excel 数据表已保存至:\n{save_path}")
                except Exception as e:
                    progress.close()
                    QMessageBox.critical(self, "导出失败", f"生成 Excel 表格失败: {e}")

    def _start_background_model_preload(self):
        """后台守护线程静默预加载检测器模型，消除首张图片的冷启动等待，且不阻塞 UI 交互"""
        import threading
        def _preload_worker():
            try:
                from xray_void_seg import get_detector_instance
                device, _, _ = hardware_sniffer.resolve_device(self.config.hardware_device)
                det = get_detector_instance(self.config.weights_path, device=device)
                # 🌟 交给检测器内部统一预热：使用与正式推理相同的 img_size，
                # 并与正式推理共用互斥锁，避免 640 空跑与 1280 质检并发踩踏 Detect.grid 缓存
                det.warmup()
            except Exception:
                pass

        t = threading.Thread(target=_preload_worker, daemon=True, name="ModelWarmupThread")
        t.start()
