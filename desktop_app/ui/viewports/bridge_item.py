# -*- coding: utf-8 -*-
"""
🌟 桥连短路缺陷矢量交互图元 (Bridge Defect Graphics Item)
---------------------------------------------------------
1. 无文字遮挡：不显示任何 SHORT 字符标签；
2. 无中心连线：不绘制焊球间穿透连线；
3. 无颜色覆盖：内部 100% 镂空透明 (NoBrush)，仅描绘精致轮廓线；
4. 同步透明度：跟随全局透明度滑块动态渐变；
5. 单独点击交互：鼠标单击选框即可独立隐藏/显示，方便工人透视原图。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QStyleOptionGraphicsItem,
    QWidget,
)


class BridgeDefectGraphicsItem(QGraphicsItem):
    def __init__(self, bridge_data: dict, parent=None):
        super().__init__(parent)
        self.bridge_data = bridge_data
        self.roi_box = bridge_data.get("roi_box", (0, 0, 10, 10))
        self.is_user_hidden = False
        self.view_mode = "all_outline"
        self.alpha_factor = 1.0
        self.is_hovered = False

        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setZValue(8.0)  # 置于焊球(10.0)下方，确保焊球悬停优先级

        bx, by, bw, bh = self.roi_box
        self._bounding_rect = QRectF(bx - 3, by - 3, bw + 6, bh + 6)

    def boundingRect(self) -> QRectF:
        return self._bounding_rect

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        bx, by, bw, bh = self.roi_box
        path.addRect(QRectF(bx, by, bw, bh))
        return path

    def set_view_mode(self, mode: str):
        self.view_mode = mode
        self.update()

    def set_alpha(self, alpha: float):
        self.alpha_factor = max(0.1, min(1.0, alpha))
        self.update()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None):
        # 1. 工人手动消隐或纯原图模式时不绘制
        if self.is_user_hidden or self.view_mode == "raw_image":
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bx, by, bw, bh = self.roi_box

        # 2. 仅描绘虚线轮廓，绝无填充覆盖，随透明度滑块平滑渐变 (警报鲜红)
        alpha_int = int(self.alpha_factor * 255)
        pen_color = QColor(255, 77, 79, alpha_int) if self.is_hovered else QColor(239, 68, 68, alpha_int)  # 醒目警报鲜红
        pen_width = 2.2 if self.is_hovered else 1.8

        painter.setPen(QPen(pen_color, pen_width, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)  # 严格 0 填充
        painter.drawRect(QRectF(bx, by, bw, bh))

        # 3. 若检测出短路微小锡球，同样仅描精细圆轮廓，不加实心填充
        small_ball = self.bridge_data.get("small_ball")
        if small_ball and len(small_ball) >= 3:
            sx, sy, sr = small_ball
            painter.setPen(QPen(QColor(239, 68, 68, alpha_int), 1.5, Qt.PenStyle.SolidLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(sx, sy), sr, sr)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 单击独立切换隐藏 / 显示
            self.is_user_hidden = not self.is_user_hidden
            self.update()
            event.accept()
        else:
            super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)
