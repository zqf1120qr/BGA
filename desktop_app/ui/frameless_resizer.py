# -*- coding: utf-8 -*-
"""
无边框原生窗口 8 向平滑缩放与 Windows 原生生态融合器 (Frameless Resizer)
------------------------------------------------------------------
为 Windows Frameless 无边框窗口提供原生级边缘拉伸与对角缩放体验：
- 支持 8 个方向：上、下、左、右、左上、右上、左下、右下；
- 支持 Windows 11 Snap Layouts 贴靠菜单 (HTMAXBUTTON) 与 Win+方向键原生分屏；
- 在 Windows 下优先使用原生 WM_NCHITTEST 消息分流，避免全局 QApplication 性能损耗。
"""
from __future__ import annotations

import sys
from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt", wintypes.POINT),
        ]


class FramelessResizer(QObject):
    BORDER_WIDTH = 7

    def __init__(self, window: QMainWindow):
        super().__init__()
        self.win = window
        self._resizing = False
        self._resize_dir: str | None = None
        self._drag_start_pos = QPoint()
        self._drag_start_geo = QRect()
        self._cursor_overridden = False
        self._installed_app = False
        self._targets: list[QObject] = []
        if hasattr(self.win, "destroyed"):
            self.win.destroyed.connect(self.cleanup)

    def attach(self, target: QObject | None = None):
        """挂载目标事件监听 (仅在非 Windows 或局部组件中挂载)"""
        if target and target not in self._targets:
            target.installEventFilter(self)
            self._targets.append(target)

    def handle_native_event(self, eventType, message, max_btn: QWidget | None = None) -> tuple[bool, int]:
        """处理 Windows 原生消息 (WM_NCHITTEST)，无缝对接 Windows 11 Snap 布局"""
        if sys.platform != "win32":
            return False, 0
        if eventType not in (b"windows_generic_MSG", "windows_generic_MSG"):
            return False, 0

        try:
            msg = MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST
                x = ctypes.c_short(msg.lParam & 0xFFFF).value
                y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value

                # 优先检测最大化按钮 (激活 Windows 11 Snap Layouts 贴靠菜单)
                if max_btn and max_btn.isVisible():
                    top_left = max_btn.mapToGlobal(QPoint(0, 0))
                    bw = max_btn.width()
                    bh = max_btn.height()
                    if (top_left.x() <= x <= top_left.x() + bw) and (top_left.y() <= y <= top_left.y() + bh):
                        return True, 9  # HTMAXBUTTON

                if self.win.isMaximized():
                    return False, 0

                win_geo = self.win.geometry()
                wx = win_geo.x()
                wy = win_geo.y()
                ww = win_geo.width()
                wh = win_geo.height()
                b = self.BORDER_WIDTH

                on_left = (wx <= x <= wx + b)
                on_right = (wx + ww - b <= x <= wx + ww)
                on_top = (wy <= y <= wy + b)
                on_bottom = (wy + wh - b <= y <= wy + wh)

                if on_left and on_top:
                    return True, 13  # HTTOPLEFT
                if on_right and on_top:
                    return True, 14  # HTTOPRIGHT
                if on_left and on_bottom:
                    return True, 16  # HTBOTTOMLEFT
                if on_right and on_bottom:
                    return True, 17  # HTBOTTOMRIGHT
                if on_left:
                    return True, 10  # HTLEFT
                if on_right:
                    return True, 11  # HTRIGHT
                if on_top:
                    return True, 12  # HTTOP
                if on_bottom:
                    return True, 15  # HTBOTTOM
        except Exception:
            pass

        return False, 0

    def cleanup(self):
        """窗口关闭或析构时安全解绑所有事件过滤器"""
        if self._installed_app:
            app = QApplication.instance()
            if app:
                try:
                    app.removeEventFilter(self)
                except Exception:
                    pass
            self._installed_app = False
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
        if not self.win or self.win.isMaximized():
            if self._cursor_overridden:
                try:
                    self.win.unsetCursor()
                except Exception:
                    pass
                self._cursor_overridden = False
            return False

        if isinstance(obj, QWidget):
            try:
                if obj.window() != self.win:
                    return False
            except Exception:
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
