# -*- coding: utf-8 -*-
"""
🌟 8 点自由交互式 ROI 裁剪选框图元 (Roi Crop Item)
--------------------------------------------------
完美对齐原有 Web 页面图 2 的裁剪交互形态：
1. 具备 8 个白色方块调节把手 (四角 + 四边中点)；
2. 鼠标悬停自动呈现相应方位的缩放光标；
3. 中心区域支持自由拖拽整体移动；
4. 边界吸附与有效范围约束；
5. 提供快捷接口输出标准整数坐标 (x1, y1, x2, y2)。
"""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QStyleOptionGraphicsItem,
    QWidget,
)


class RoiCropGraphicsItem(QGraphicsItem):
    HANDLE_SIZE = 10.0

    # 8 个把手方位标识
    HANDLE_NONE = 0
    HANDLE_TOP_LEFT = 1
    HANDLE_TOP = 2
    HANDLE_TOP_RIGHT = 3
    HANDLE_RIGHT = 4
    HANDLE_BOTTOM_RIGHT = 5
    HANDLE_BOTTOM = 6
    HANDLE_BOTTOM_LEFT = 7
    HANDLE_LEFT = 8
    HANDLE_INSIDE = 9

    def __init__(self, initial_rect: QRectF, max_bounds: QRectF, parent=None):
        super().__init__(parent)
        self.rect = QRectF(initial_rect)
        self.max_bounds = QRectF(max_bounds)

        self.current_handle = self.HANDLE_NONE
        self.drag_start_pos = QPointF()
        self.drag_start_rect = QRectF()

        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setZValue(100.0)  # 置于标注图层上方

    def boundingRect(self) -> QRectF:
        m = self.HANDLE_SIZE + 4.0
        return self.rect.adjusted(-m, -m, m, m)

    def get_crop_rect(self) -> tuple[int, int, int, int]:
        """返回规整后的正向整数裁剪坐标 (x1, y1, x2, y2)"""
        norm = self.rect.normalized()
        x1 = max(0, int(round(norm.left())))
        y1 = max(0, int(round(norm.top())))
        x2 = min(int(round(self.max_bounds.width())), int(round(norm.right())))
        y2 = min(int(round(self.max_bounds.height())), int(round(norm.bottom())))
        return (x1, y1, x2, y2)

    def _get_handles(self) -> dict[int, QRectF]:
        s = self.HANDLE_SIZE
        r = self.rect
        return {
            self.HANDLE_TOP_LEFT: QRectF(r.left() - s / 2, r.top() - s / 2, s, s),
            self.HANDLE_TOP: QRectF(r.center().x() - s / 2, r.top() - s / 2, s, s),
            self.HANDLE_TOP_RIGHT: QRectF(r.right() - s / 2, r.top() - s / 2, s, s),
            self.HANDLE_RIGHT: QRectF(r.right() - s / 2, r.center().y() - s / 2, s, s),
            self.HANDLE_BOTTOM_RIGHT: QRectF(r.right() - s / 2, r.bottom() - s / 2, s, s),
            self.HANDLE_BOTTOM: QRectF(r.center().x() - s / 2, r.bottom() - s / 2, s, s),
            self.HANDLE_BOTTOM_LEFT: QRectF(r.left() - s / 2, r.bottom() - s / 2, s, s),
            self.HANDLE_LEFT: QRectF(r.left() - s / 2, r.center().y() - s / 2, s, s),
        }

    def _detect_handle(self, pos: QPointF) -> int:
        handles = self._get_handles()
        for h_type, h_rect in handles.items():
            if h_rect.contains(pos):
                return h_type
        if self.rect.contains(pos):
            return self.HANDLE_INSIDE
        return self.HANDLE_NONE

    def hoverMoveEvent(self, event):
        h = self._detect_handle(event.pos())
        if h in (self.HANDLE_TOP_LEFT, self.HANDLE_BOTTOM_RIGHT):
            self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        elif h in (self.HANDLE_TOP_RIGHT, self.HANDLE_BOTTOM_LEFT):
            self.setCursor(QCursor(Qt.CursorShape.SizeBDiagCursor))
        elif h in (self.HANDLE_TOP, self.HANDLE_BOTTOM):
            self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
        elif h in (self.HANDLE_LEFT, self.HANDLE_RIGHT):
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif h == self.HANDLE_INSIDE:
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.current_handle = self._detect_handle(event.pos())
            self.drag_start_pos = event.pos()
            self.drag_start_rect = QRectF(self.rect)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.current_handle == self.HANDLE_NONE:
            return

        delta = event.pos() - self.drag_start_pos
        r = QRectF(self.drag_start_rect)
        min_size = 40.0

        if self.current_handle == self.HANDLE_INSIDE:
            # 整体平移
            r.translate(delta.x(), delta.y())
            # 约束在 max_bounds 内
            if r.left() < self.max_bounds.left():
                r.moveLeft(self.max_bounds.left())
            if r.top() < self.max_bounds.top():
                r.moveTop(self.max_bounds.top())
            if r.right() > self.max_bounds.right():
                r.moveRight(self.max_bounds.right())
            if r.bottom() > self.max_bounds.bottom():
                r.moveBottom(self.max_bounds.bottom())

        else:
            # 8 点缩放拉伸
            if self.current_handle in (self.HANDLE_LEFT, self.HANDLE_TOP_LEFT, self.HANDLE_BOTTOM_LEFT):
                new_left = min(r.right() - min_size, r.left() + delta.x())
                r.setLeft(max(self.max_bounds.left(), new_left))

            if self.current_handle in (self.HANDLE_RIGHT, self.HANDLE_TOP_RIGHT, self.HANDLE_BOTTOM_RIGHT):
                new_right = max(r.left() + min_size, r.right() + delta.x())
                r.setRight(min(self.max_bounds.right(), new_right))

            if self.current_handle in (self.HANDLE_TOP, self.HANDLE_TOP_LEFT, self.HANDLE_TOP_RIGHT):
                new_top = min(r.bottom() - min_size, r.top() + delta.y())
                r.setTop(max(self.max_bounds.top(), new_top))

            if self.current_handle in (self.HANDLE_BOTTOM, self.HANDLE_BOTTOM_LEFT, self.HANDLE_BOTTOM_RIGHT):
                new_bottom = max(r.top() + min_size, r.bottom() + delta.y())
                r.setBottom(min(self.max_bounds.bottom(), new_bottom))

        self.prepareGeometryChange()
        self.rect = r
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        self.current_handle = self.HANDLE_NONE
        super().mouseReleaseEvent(event)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1. 绘制选框边界线 (白色高亮虚线)
        border_pen = QPen(QColor(255, 255, 255, 230), 2.0, Qt.PenStyle.DashLine)
        painter.setPen(border_pen)
        # 半透明内部填充，轻微提亮被选区域 (与图2视觉完全一致)
        painter.setBrush(QBrush(QColor(255, 255, 255, 25)))
        painter.drawRect(self.rect)

        # 2. 绘制 8 个白色实心方块把手
        handles = self._get_handles()
        handle_pen = QPen(QColor(40, 40, 40, 200), 1.0)
        handle_brush = QBrush(QColor(255, 255, 255, 255))
        painter.setPen(handle_pen)
        painter.setBrush(handle_brush)
        for h_rect in handles.values():
            painter.drawRect(h_rect)
