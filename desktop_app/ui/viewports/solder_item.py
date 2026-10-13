# -*- coding: utf-8 -*-
"""
焊点矢量交互图元 (Solder Ball Graphics Item)
-----------------------------------------------
1. 悬停空洞占比与状态直接在焊球上方以不被截断的胶囊标牌展示；
2. 边界框 (boundingRect) 预留充裕空间，彻底消除悬停标题被截断的问题；
3. 支持单击消隐、细轮廓渲染与激光电光青双同心圆靶心对焦。
"""
from __future__ import annotations

from typing import Callable, Optional
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

from desktop_app.core.inspection_manager import SolderBallRecord
from desktop_app.ui.styles.color_palette import DefectColors


class SolderBallGraphicsItem(QGraphicsItem):
    def __init__(
        self,
        record: SolderBallRecord,
        on_clicked_callback: Optional[Callable[[int], None]] = None,
        on_hover_enter_callback: Optional[Callable[[SolderBallRecord, QPointF], None]] = None,
        on_hover_leave_callback: Optional[Callable[[], None]] = None,
        on_review_toggled_callback: Optional[Callable[[int], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.record = record
        self.on_clicked = on_clicked_callback
        self.on_hover_enter = on_hover_enter_callback
        self.on_hover_leave = on_hover_leave_callback
        self.on_review_toggled = on_review_toggled_callback


        # 视口渲染参数
        self.view_mode = "all_outline"  # "all_outline" | "defect_only" | "raw_image"
        self.alpha_factor = 1.0        # 0.1 ~ 1.0 (默认 100% 鲜明标注)
        self.is_hovered = False
        self.is_selected = False

        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # 缓存边界矩形 (预留十字准星与高亮外圈的安全绘制边界)
        r = self.record.radius
        margin = max(24.0, r * 0.6)
        self._bounding_rect = QRectF(
            self.record.cx - r - margin,
            self.record.cy - r - margin,
            (r + margin) * 2,
            (r + margin) * 2,
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

        # 2. 若处于“仅高亮缺陷模式”，且当前焊点无真实缺陷(已通过或已复核)，未悬停且未选中时，不绘制
        if self.view_mode == "defect_only" and not self.record.final_is_ng and not self.is_hovered and not self.is_selected:
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # 3. 确定轮廓笔刷颜色与线宽
        alpha_int = int(self.alpha_factor * 255)
        is_reviewed_pass = (self.record.is_manually_reviewed and self.record.manual_status == "PASS") or (self.record.is_bridge_cleared and not self.record.final_is_ng)
        
        if is_reviewed_pass:
            # 人工复核合格 (排除误检)：专属电光青蓝轮廓 (#06b6d4)
            pen_color = QColor(
                DefectColors.REVIEW_PASS_COLOR.red(),
                DefectColors.REVIEW_PASS_COLOR.green(),
                DefectColors.REVIEW_PASS_COLOR.blue(),
                min(255, alpha_int + 30)
            )
            pen_width = 1.6 if not self.is_hovered else 2.4
        elif self.record.final_is_ng:
            if self.record.is_bridge:
                pen_color = QColor(DefectColors.BRIDGE_NG_COLOR.red(), DefectColors.BRIDGE_NG_COLOR.green(), DefectColors.BRIDGE_NG_COLOR.blue(), min(255, alpha_int + 40))  # 桥连短路：警戒鲜红
            elif self.record.is_void_ng:
                pen_color = QColor(DefectColors.VOID_NG_COLOR.red(), DefectColors.VOID_NG_COLOR.green(), DefectColors.VOID_NG_COLOR.blue(), min(255, alpha_int + 40))      # 空洞超标：亮品红
            elif self.record.is_insufficient:
                pen_color = QColor(DefectColors.INSUFF_NG_COLOR.red(), DefectColors.INSUFF_NG_COLOR.green(), DefectColors.INSUFF_NG_COLOR.blue(), min(255, alpha_int + 40))  # 虚焊少锡：高亮金黄
            else:
                pen_color = QColor(DefectColors.VOID_NG_COLOR.red(), DefectColors.VOID_NG_COLOR.green(), DefectColors.VOID_NG_COLOR.blue(), alpha_int)
            pen_width = 1.8 if not self.is_hovered else 2.6
        else:
            # 合格正常焊球：极细半透明翠绿色 (低遮挡细轮廓)
            pen_color = QColor(DefectColors.NORMAL_COLOR.red(), DefectColors.NORMAL_COLOR.green(), DefectColors.NORMAL_COLOR.blue(), int(alpha_int * 0.75))
            pen_width = 1.0 if not self.is_hovered else 2.0


        # 双击/单击表格定位选中：超高亮纯金黄 (#ffe600) 双层准星雷达复合靶心
        if self.is_selected:
            focus_col = DefectColors.FOCUS_TARGET_COLOR
            cx, cy, r = self.record.cx, self.record.cy, self.record.radius

            # 0. 底层黑色微轮廓 (保证在极亮/极白背景下依然拥有顶级反差)
            shadow_pen = QPen(QColor(0, 0, 0, 200), 4.5, Qt.PenStyle.SolidLine)
            painter.setPen(shadow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), r + 3.0, r + 3.0)

            # 1. 内环：高亮激光纯金黄实线主光环 (粗线 3.0px)
            inner_pen = QPen(focus_col, 3.0, Qt.PenStyle.SolidLine)
            painter.setPen(inner_pen)
            painter.drawEllipse(QPointF(cx, cy), r + 3.0, r + 3.0)

            # 2. 外环：高亮金色雷达大虚线圈 (扩展 10px)
            outer_pen = QPen(focus_col, 2.0, Qt.PenStyle.DashLine)
            painter.setPen(outer_pen)
            painter.drawEllipse(QPointF(cx, cy), r + 10.0, r + 10.0)

            # 3. 极醒目的 4 向十字瞄准准星标尺线 (Crosshair Reticle)
            # 先画黑底阴影
            reticle_shadow = QPen(QColor(0, 0, 0, 220), 4.0, Qt.PenStyle.SolidLine)
            painter.setPen(reticle_shadow)
            painter.drawLine(QPointF(cx, cy - r - 10.0), QPointF(cx, cy - r - 19.0))
            painter.drawLine(QPointF(cx, cy + r + 10.0), QPointF(cx, cy + r + 19.0))
            painter.drawLine(QPointF(cx - r - 10.0, cy), QPointF(cx - r - 19.0, cy))
            painter.drawLine(QPointF(cx + r + 10.0, cy), QPointF(cx + r + 19.0, cy))

            # 再画金色主体准星线
            reticle_pen = QPen(focus_col, 2.6, Qt.PenStyle.SolidLine)
            painter.setPen(reticle_pen)
            painter.drawLine(QPointF(cx, cy - r - 10.0), QPointF(cx, cy - r - 19.0))
            painter.drawLine(QPointF(cx, cy + r + 10.0), QPointF(cx, cy + r + 19.0))
            painter.drawLine(QPointF(cx - r - 10.0, cy), QPointF(cx - r - 19.0, cy))
            painter.drawLine(QPointF(cx + r + 10.0, cy), QPointF(cx + r + 19.0, cy))

        # 4. 绘制焊点外边缘主圆圈 (标准工业单一圆圈轮廓，不画任何奇异同心光环)
        painter.setPen(QPen(pen_color, pen_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(
            QPointF(self.record.cx, self.record.cy),
            self.record.radius,
            self.record.radius,
        )

        # 5. 绘制内部空洞圆 (超标为亮橙色，复核合格为柔和青绿，未超标为细电光青)
        if self.record.void_circles:
            for vc in self.record.void_circles:
                vcx, vcy = vc.get("center", (0.0, 0.0))
                vr = float(vc.get("radius", 1.0))
                if is_reviewed_pass and self.record.is_void_ng:
                    # 原本超标但已被人工复核为合格：柔和淡青色，消除警示感
                    v_pen = QPen(DefectColors.REVIEW_PASS_COLOR, 1.2, Qt.PenStyle.DashLine)
                    v_brush = QBrush(QColor(
                        DefectColors.REVIEW_PASS_COLOR.red(),
                        DefectColors.REVIEW_PASS_COLOR.green(),
                        DefectColors.REVIEW_PASS_COLOR.blue(),
                        int(alpha_int * 0.18)
                    ))
                elif self.record.is_void_ng:
                    # 超标空洞 (NG)：亮橙色 + 微加粗 1.8px + 适度轻微透明填充
                    v_pen = QPen(DefectColors.VOID_NG_COLOR, 1.8)
                    v_brush = QBrush(QColor(
                        DefectColors.VOID_NG_COLOR.red(),
                        DefectColors.VOID_NG_COLOR.green(),
                        DefectColors.VOID_NG_COLOR.blue(),
                        int(alpha_int * 0.25)
                    ))
                else:
                    # 正常微孔 (PASS)：电光青细线 1.0px + 轻微透明填充
                    v_pen = QPen(DefectColors.VOID_NORMAL_COLOR, 1.0)
                    v_brush = QBrush(QColor(
                        DefectColors.VOID_NORMAL_COLOR.red(),
                        DefectColors.VOID_NORMAL_COLOR.green(),
                        DefectColors.VOID_NORMAL_COLOR.blue(),
                        int(alpha_int * 0.20)
                    ))
                painter.setPen(v_pen)
                painter.setBrush(v_brush)
                painter.drawEllipse(QPointF(vcx, vcy), vr, vr)

        # 6. 悬停状态下高亮焊球外环发光圈
        if self.is_hovered:
            glow_col = DefectColors.REVIEW_PASS_COLOR if is_reviewed_pass else DefectColors.CONF_COLOR
            glow_pen = QPen(glow_col, 2.2, Qt.PenStyle.SolidLine)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                QPointF(self.record.cx, self.record.cy),
                self.record.radius + 2.0,
                self.record.radius + 2.0,
            )

    def contextMenuEvent(self, event):
        """右键点击焊球弹出快捷复核上下文菜单 (仅对真实缺陷或已复核项有效，正常焊点不弹菜单)"""
        is_reviewed = (self.record.is_manually_reviewed and self.record.manual_status == "PASS") or (self.record.is_bridge_cleared and not self.record.final_is_ng)
        # 正常合格焊点不弹复核菜单，杜绝误导
        if not self.record.final_is_ng and not is_reviewed:
            event.ignore()
            return

        menu = QMenu()
        menu.setCursor(Qt.CursorShape.PointingHandCursor)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #f8fafc;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 11px;
                padding: 4px;
            }
            QMenu::item {
                padding: 5px 16px 5px 10px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #1e293b;
                color: #38bdf8;
            }
        """)

        if is_reviewed:
            act_toggle = menu.addAction(f"↺ 撤销复核 (恢复焊球 #{self.record.index} 初始判定)")
        else:
            act_toggle = menu.addAction(f"排除误检 (将焊球 #{self.record.index} 标记为合格)")

        chosen = menu.exec(event.screenPos())
        if chosen == act_toggle and self.on_review_toggled:
            self.on_review_toggled(self.record.index)
        event.accept()

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
