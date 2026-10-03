# -*- coding: utf-8 -*-
"""
🌟 焊点矢量交互图元 (Solder Ball Graphics Item)
-----------------------------------------------
1. 悬停气泡占比与状态直接在焊球上方以不被截断的胶囊标牌展示；
2. 边界框 (boundingRect) 预留充裕空间，彻底消除悬停标题被截断的问题；
3. 支持单击消隐、细轮廓渲染与透明度无级渐变。
"""
from __future__ import annotations

from typing import Callable, Optional
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from desktop_app.core.inspection_manager import SolderBallRecord


class SolderBallGraphicsItem(QGraphicsItem):
    def __init__(
        self,
        record: SolderBallRecord,
        on_clicked_callback: Optional[Callable[[int], None]] = None,
        on_hover_enter_callback: Optional[Callable[[SolderBallRecord, QPointF], None]] = None,
        on_hover_leave_callback: Optional[Callable[[], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.record = record
        self.on_clicked = on_clicked_callback
        self.on_hover_enter = on_hover_enter_callback
        self.on_hover_leave = on_hover_leave_callback

        # 视口渲染参数
        self.view_mode = "all_outline"  # "all_outline" | "defect_only" | "raw_image"
        self.alpha_factor = 1.0        # 0.1 ~ 1.0 (默认 100% 鲜明标注)
        self.is_hovered = False
        self.is_selected = False

        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # 缓存边界矩形 (预留上方/下方标签与左右文字空间，彻底杜绝文字截断)
        r = self.record.radius
        extra_top = 40.0
        extra_bottom = 40.0
        extra_side = max(90.0, r * 3.5)
        self._bounding_rect = QRectF(
            self.record.cx - r - extra_side,
            self.record.cy - r - extra_top,
            (r + extra_side) * 2,
            (r * 2) + extra_top + extra_bottom,
        )

    def boundingRect(self) -> QRectF:
        return self._bounding_rect

    def shape(self) -> QPainterPath:
        """精确焊球圆周探测区域，杜绝外围大边框导致的错误悬停与相邻焊球事件抖动"""
        path = QPainterPath()
        path.addEllipse(
            QPointF(self.record.cx, self.record.cy),
            self.record.radius + 2.0,
            self.record.radius + 2.0,
        )
        return path

    def set_view_mode(self, mode: str):
        self.view_mode = mode
        self.update()

    def set_alpha(self, alpha: float):
        self.alpha_factor = max(0.1, min(1.0, alpha))
        self.update()

    def set_selected_highlight(self, selected: bool):
        self.is_selected = selected
        self.update()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None):
        # 1. 若工人手动消隐该点，或处于纯原图模式，则完全不绘制任何标注
        if self.record.is_user_hidden or self.view_mode == "raw_image":
            return

        # 2. 若处于“仅高亮缺陷模式”，且当前焊点完全合格，未悬停且未选中时，不绘制
        if self.view_mode == "defect_only" and not self.record.is_ng and not self.is_hovered and not self.is_selected:
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # 3. 确定轮廓笔刷颜色与线宽
        alpha_int = int(self.alpha_factor * 255)
        
        if self.record.is_ng:
            if self.record.is_bridge:
                pen_color = QColor(245, 158, 11, min(255, alpha_int + 40))  # 桥连短路：警戒黄
            elif self.record.is_void_ng:
                pen_color = QColor(244, 63, 94, min(255, alpha_int + 40))   # 气泡超标：玫瑰红
            elif self.record.is_insufficient:
                pen_color = QColor(251, 146, 60, min(255, alpha_int + 40))  # 虚焊少锡：橙色
            else:
                pen_color = QColor(244, 63, 94, alpha_int)
            pen_width = 1.8 if not self.is_hovered else 2.6
        else:
            # 合格正常焊球：极细半透明翠绿色 (低遮挡细轮廓)
            pen_color = QColor(16, 185, 129, int(alpha_int * 0.75))
            pen_width = 1.0 if not self.is_hovered else 2.0

        # 选中呼吸外框
        if self.is_selected:
            halo_pen = QPen(QColor(56, 189, 248, 220), 2.5, Qt.PenStyle.DashLine)
            painter.setPen(halo_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                QPointF(self.record.cx, self.record.cy),
                self.record.radius + 3.0,
                self.record.radius + 3.0,
            )

        # 4. 绘制焊点外边缘主圆圈
        painter.setPen(QPen(pen_color, pen_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(
            QPointF(self.record.cx, self.record.cy),
            self.record.radius,
            self.record.radius,
        )

        # 5. 绘制内部气泡空洞圆 (精细还原)
        if self.record.void_circles:
            for vc in self.record.void_circles:
                vcx, vcy = vc.get("center", (0.0, 0.0))
                vr = float(vc.get("radius", 1.0))
                if self.record.is_void_ng:
                    v_pen = QPen(QColor(244, 63, 94, alpha_int), 1.2)
                    v_brush = QBrush(QColor(244, 63, 94, int(alpha_int * 0.25)))
                else:
                    v_pen = QPen(QColor(245, 158, 11, int(alpha_int * 0.8)), 1.0)
                    v_brush = QBrush(QColor(245, 158, 11, int(alpha_int * 0.15)))
                
                painter.setPen(v_pen)
                painter.setBrush(v_brush)
                painter.drawEllipse(QPointF(vcx, vcy), vr, vr)

        # 6. 悬停状态下高亮焊球外环发光圈，缺陷概览模式下绘制上方数据标牌
        if self.is_hovered:
            glow_pen = QPen(QColor(56, 189, 248, 230), 2.2, Qt.PenStyle.SolidLine)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                QPointF(self.record.cx, self.record.cy),
                self.record.radius + 2.0,
                self.record.radius + 2.0,
            )

        show_label = (self.view_mode == "defect_only" and self.record.is_ng and not self.is_hovered)
        if show_label:
            font = QFont("Segoe UI", 8, QFont.Weight.Bold)
            painter.setFont(font)
            fm = QFontMetrics(font)

            # 组装展示文本：包含编号与气泡占比/缺陷状态 (始终显示气泡占比)
            void_str = f"气泡{self.record.void_rate * 100:.1f}%"
            if self.record.is_bridge:
                tag_text = f"#{self.record.index} 短路NG {void_str}"
            elif self.record.is_insufficient:
                tag_text = f"#{self.record.index} 少锡-{self.record.reduction_percent:.1f}% {void_str}"
            elif self.record.is_void_ng:
                tag_text = f"#{self.record.index} {void_str}(NG)"
            else:
                tag_text = f"#{self.record.index} {void_str}"

            text_w = fm.horizontalAdvance(tag_text) + 12
            text_h = 16
            tag_x = self.record.cx - (text_w / 2.0)
            
            # 若焊点靠近图像顶边缘，向上绘制会超出画布边界截断，此时自动优雅翻转至焊点下方
            tag_y = self.record.cy - self.record.radius - text_h - 4.0
            if tag_y < 4.0:
                tag_y = self.record.cy + self.record.radius + 4.0

            # 胶囊深色背景与细边框
            painter.setPen(QPen(pen_color, 1.0))
            painter.setBrush(QBrush(QColor(15, 23, 42, 230)))
            painter.drawRoundedRect(QRectF(tag_x, tag_y, text_w, text_h), 4.0, 4.0)

            # 胶囊居中文字
            painter.setPen(QColor(248, 250, 252))
            painter.drawText(
                QRectF(tag_x, tag_y, text_w, text_h),
                Qt.AlignmentFlag.AlignCenter,
                tag_text
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 单击切换消隐
            self.record.is_user_hidden = not self.record.is_user_hidden
            self.update()
            if self.on_clicked:
                self.on_clicked(self.record.index)
            event.accept()
        else:
            super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update()
        if self.on_hover_enter:
            self.on_hover_enter(self.record)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()
        if self.on_hover_leave:
            self.on_hover_leave()
        super().hoverLeaveEvent(event)
