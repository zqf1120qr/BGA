# -*- coding: utf-8 -*-
"""
🌟 无边框原生窗口 8 向平滑缩放手柄与边缘捕获器 (Frameless Resizer)
------------------------------------------------------------------
为 Windows Frameless 无边框窗口提供 100% 原生级边缘拉伸与对角缩放体验：
- 支持 8 个方向：上、下、左、右、左上、右上、左下、右下；
- 鼠标悬停到边缘 6px 内自动切换对应原生系统光标 (SizeHor / SizeVer / SizeDiag)；
- 拖拽平滑缩放，严格遵循最小尺寸限制，最大化时自动禁用。
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt
from PySide6.QtWidgets import QMainWindow


class FramelessResizer(QObject):
    BORDER_WIDTH = 6

    def __init__(self, window: QMainWindow):
        super().__init__()
        self.win = window
        self._resizing = False
        self._resize_dir = None
        self._drag_start_pos = QPoint()
        self._drag_start_geo = QRect()
        self._cursor_overridden = False
        self._targets: list[QObject] = []
        if hasattr(self.win, "destroyed"):
            self.win.destroyed.connect(self.cleanup)

    def attach(self, target: QObject):
        """挂载事件监听并记录目标对象"""
        target.installEventFilter(self)
        self._targets.append(target)

    def cleanup(self):
        """窗口关闭或析构时安全解绑所有事件过滤器，彻底杜绝内存悬空与非法访问"""
        for t in self._targets:
            try:
                t.removeEventFilter(self)
            except Exception:
                pass
        self._targets.clear()

    def get_edge_direction(self, pos: QPoint) -> str | None:
        if self.win.isMaximized():
            return None
        w, h = self.win.width(), self.win.height()
        b = self.BORDER_WIDTH
        x, y = pos.x(), pos.y()
        if x < -b or y < -b or x > w + b or y > h + b:
            return None

        l = x <= b
        r = x >= w - b
        t = y <= b
        bot = y >= h - b

        if l and t: return "top_left"
        if r and t: return "top_right"
        if l and bot: return "bottom_left"
        if r and bot: return "bottom_right"
        if l: return "left"
        if r: return "right"
        if t: return "top"
        if bot: return "bottom"
        return None

    def cursor_for_direction(self, direction: str | None) -> Qt.CursorShape | None:
        if direction in ("top_left", "bottom_right"):
            return Qt.CursorShape.SizeFDiagCursor
        if direction in ("top_right", "bottom_left"):
            return Qt.CursorShape.SizeBDiagCursor
        if direction in ("left", "right"):
            return Qt.CursorShape.SizeHorCursor
        if direction in ("top", "bottom"):
            return Qt.CursorShape.SizeVerCursor
        return None

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if self.win.isMaximized():
            return False

        ev_type = event.type()

        if ev_type == QEvent.Type.MouseMove:
            g_pos = event.globalPosition().toPoint()
            win_pos = self.win.mapFromGlobal(g_pos)

            if self._resizing and self._resize_dir:
                dx = g_pos.x() - self._drag_start_pos.x()
                dy = g_pos.y() - self._drag_start_pos.y()
                geo = QRect(self._drag_start_geo)
                min_w = self.win.minimumWidth()
                min_h = self.win.minimumHeight()

                if "right" in self._resize_dir:
                    geo.setWidth(max(min_w, self._drag_start_geo.width() + dx))
                if "bottom" in self._resize_dir:
                    geo.setHeight(max(min_h, self._drag_start_geo.height() + dy))
                if "left" in self._resize_dir:
                    new_w = max(min_w, self._drag_start_geo.width() - dx)
                    geo.setLeft(self._drag_start_geo.right() - new_w)
                if "top" in self._resize_dir:
                    new_h = max(min_h, self._drag_start_geo.height() - dy)
                    geo.setTop(self._drag_start_geo.bottom() - new_h)

                self.win.setGeometry(geo)
                return True
            else:
                d = self.get_edge_direction(win_pos)
                if d:
                    cursor = self.cursor_for_direction(d)
                    if cursor:
                        self.win.setCursor(cursor)
                        self._cursor_overridden = True
                elif self._cursor_overridden:
                    self.win.unsetCursor()
                    self._cursor_overridden = False

        elif ev_type == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                g_pos = event.globalPosition().toPoint()
                win_pos = self.win.mapFromGlobal(g_pos)
                d = self.get_edge_direction(win_pos)
                if d:
                    self._resizing = True
                    self._resize_dir = d
                    self._drag_start_pos = g_pos
                    self._drag_start_geo = self.win.geometry()
                    return True

        elif ev_type == QEvent.Type.MouseButtonRelease:
            if self._resizing:
                self._resizing = False
                self._resize_dir = None
                self.win.unsetCursor()
                self._cursor_overridden = False
                return True

        return False
