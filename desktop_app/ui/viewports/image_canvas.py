# -*- coding: utf-8 -*-
"""
🌟 核心图像主视口交互画布 (Image Graphics Canvas)
--------------------------------------------------
基于 QGraphicsView + QGraphicsScene 实现的工业级主视口：
1. 底图与标注图层彻底解耦，矢量图元零延迟硬件加速；
2. 滚轮以鼠标指针为中心平滑缩放 (0.1x ~ 20.0x)；
3. 鼠标右键或中键丝滑拖拽平移视口；
4. 【空格键秒切透视】：按住空格键 0ms 瞬间透视纯净原图，松开瞬间恢复标注；
5. 交互式 8 点 ROI 自由拉伸裁剪模式无缝嵌入；
6. 悬停浮动数据微探针定位展示；
7. 视口与缺陷列表双向居中平移定位。
"""
from __future__ import annotations

from typing import List, Optional, Tuple
import numpy as np

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QPixmap,
    QWheelEvent,
    QKeyEvent,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QWidget,
)

from desktop_app.core.image_converter import cv_mat_to_qpixmap
from desktop_app.core.inspection_manager import SolderBallRecord
from desktop_app.ui.viewports.hover_hud import HoverHudWidget
from desktop_app.ui.viewports.roi_crop_item import RoiCropGraphicsItem
from desktop_app.ui.viewports.solder_item import SolderBallGraphicsItem
from desktop_app.ui.viewports.bridge_item import BridgeDefectGraphicsItem


class ImageCanvasView(QGraphicsView):
    sig_ball_selected = Signal(int)           # 焊球被点击选中信号 (传递 ball_index)
    sig_crop_confirmed = Signal(tuple)        # 裁剪确认信号 (传递 (x1, y1, x2, y2))
    sig_crop_cancelled = Signal()             # 裁剪取消信号
    sig_zoom_changed = Signal(float)          # 缩放比例改变信号 (例如 1.25 即 125%)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        # 视口渲染参数配置
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor(11, 15, 25)))  # 工业深色背景 (#0b0f19)

        # 内部核心图元与图层
        self.pixmap_item: Optional[QGraphicsPixmapItem] = None
        self.solder_items: List[SolderBallGraphicsItem] = []
        self.bridge_items: List[QGraphicsItem] = []
        self.crop_item: Optional[RoiCropGraphicsItem] = None
        self.hover_hud = HoverHudWidget(self.viewport())

        # 状态
        self.current_zoom = 1.0
        self._is_fit_mode = True                  # 是否处于随窗口自适应模式
        self.current_view_mode = "all_outline"
        self.current_alpha = 1.0
        self.is_space_pressed = False
        self.is_crop_mode = False
        self.raw_image_width = 0
        self.raw_image_height = 0

        # 平移拖拽支持
        self._is_panning = False
        self._pan_start_pos = QPointF()

    # ==============================================================
    # ================= 🌟 [底图与标注装载] =========================
    # ==============================================================
    def set_image_mat(self, cv_img: np.ndarray):
        """设置并加载底图，清空历史图元"""
        self.scene.clear()
        self.solder_items.clear()
        self.bridge_items.clear()
        self.crop_item = None
        self.hover_hud.hide()

        if cv_img is None or cv_img.size == 0:
            self.pixmap_item = None
            self.raw_image_width = 0
            self.raw_image_height = 0
            self.scene.setSceneRect(0, 0, 10, 10)
            self.viewport().update()
            return

        h, w = cv_img.shape[:2]
        self.raw_image_width = w
        self.raw_image_height = h

        pixmap = cv_mat_to_qpixmap(cv_img)
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.pixmap_item.setZValue(0.0)  # 底图置于最底层
        self.scene.addItem(self.pixmap_item)
        self.scene.setSceneRect(0, 0, w, h)
        self.fit_in_view()

    def load_inspection_overlay(
        self,
        records: List[SolderBallRecord],
        bridge_defects: List[dict],
        view_mode: str = "all_outline",
        alpha: float = 1.0,
    ):
        """加载矢量焊球与桥连标注图元"""
        # 清除旧的矢量标注
        for item in self.solder_items:
            self.scene.removeItem(item)
        for item in self.bridge_items:
            self.scene.removeItem(item)
        self.solder_items.clear()
        self.bridge_items.clear()

        self.current_view_mode = view_mode
        self.current_alpha = alpha

        # 1. 批量构建焊球矢量图元
        for rec in records:
            item = SolderBallGraphicsItem(
                record=rec,
                on_clicked_callback=self._handle_ball_clicked,
                on_hover_enter_callback=self._handle_hover_enter,
                on_hover_leave_callback=self._handle_hover_leave,
            )
            item.setZValue(10.0)
            item.set_view_mode(self.current_view_mode)
            item.set_alpha(self.current_alpha)
            self.scene.addItem(item)
            self.solder_items.append(item)

        # 2. 批量构建桥连短路矢量图元 (无文字、无中心连线、无填充覆盖、仅描轮廓、可调透明度、点击独立消隐)
        for b in bridge_defects:
            b_item = BridgeDefectGraphicsItem(b)
            b_item.set_view_mode(self.current_view_mode)
            b_item.set_alpha(self.current_alpha)
            self.scene.addItem(b_item)
            self.bridge_items.append(b_item)

    # ==============================================================
    # ================= [视图模式与透明度控制] ====================
    # ==============================================================
    def set_view_mode(self, mode: str):
        self.current_view_mode = mode
        for item in self.solder_items:
            item.set_view_mode(mode)
        for b_item in self.bridge_items:
            b_item.set_view_mode(mode)

    def set_overlay_alpha(self, alpha: float):
        self.current_alpha = alpha
        for item in self.solder_items:
            item.set_alpha(alpha)
        for b_item in self.bridge_items:
            b_item.set_alpha(alpha)

    def refresh_solder_items(self):
        """通知所有焊球刷新自身重判颜色"""
        for item in self.solder_items:
            item.update()

    def highlight_ball(self, ball_index: int, zoom_to: bool = True):
        """在视口中高亮选中指定序号的焊球并平滑聚焦"""
        for item in self.solder_items:
            if item.record.index == ball_index:
                item.set_selected_highlight(True)
                if zoom_to:
                    self.centerOn(item)
                    if self.current_zoom < 1.5:
                        self.set_zoom(1.8)
            else:
                item.set_selected_highlight(False)

    # ==============================================================
    # ================= 🌟 [ROI 裁剪选框控制] =======================
    # ==============================================================
    def enter_crop_mode(self):
        """进入 8 点自由拉伸交互裁剪模式"""
        if self.is_crop_mode or self.raw_image_width == 0:
            return
        self.is_crop_mode = True

        # 默认裁剪框居中占图像 75% 区域
        w = self.raw_image_width
        h = self.raw_image_height
        cx1 = w * 0.12
        cy1 = h * 0.12
        cw = w * 0.76
        ch = h * 0.76

        self.crop_item = RoiCropGraphicsItem(
            initial_rect=QRectF(cx1, cy1, cw, ch),
            max_bounds=QRectF(0, 0, w, h)
        )
        self.scene.addItem(self.crop_item)

    def confirm_crop(self) -> Optional[Tuple[int, int, int, int]]:
        """确认裁剪并返回选框坐标"""
        if not self.is_crop_mode or not self.crop_item:
            return None
        rect = self.crop_item.get_crop_rect()
        self.exit_crop_mode()
        self.sig_crop_confirmed.emit(rect)
        return rect

    def cancel_crop(self):
        """取消裁剪选框"""
        self.exit_crop_mode()
        self.sig_crop_cancelled.emit()

    def exit_crop_mode(self):
        if self.crop_item and self.crop_item.scene():
            self.scene.removeItem(self.crop_item)
        self.crop_item = None
        self.is_crop_mode = False

    # ==============================================================
    # ================= 🌟 [滚轮缩放与平移事件] =====================
    # ==============================================================
    def wheelEvent(self, event: QWheelEvent):
        self.hover_hud.hide()
        zoom_in_factor = 1.15
        zoom_out_factor = 1.0 / zoom_in_factor

        if event.angleDelta().y() > 0:
            factor = zoom_in_factor
        else:
            factor = zoom_out_factor

        new_zoom = self.current_zoom * factor
        if 0.05 <= new_zoom <= 30.0:
            self._is_fit_mode = False  # 退出随窗口自适应模式，进入自由缩放
            self.scale(factor, factor)
            self.current_zoom = self.transform().m11()
            self.sig_zoom_changed.emit(self.current_zoom)

    def mousePressEvent(self, event):
        self.hover_hud.hide()
        pos = event.position().toPoint()
        # 1. 鼠标中键或右键：在视口任意位置均可即时平移
        if event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._is_panning = True
            self._pan_start_pos = pos
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        # 2. 鼠标左键：在底图、空白处或焊点间隙按住即可直接平移拖拽
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(pos)
            is_interactive = isinstance(item, (SolderBallGraphicsItem, BridgeDefectGraphicsItem, RoiCropGraphicsItem))
            if not is_interactive or item in (None, self.pixmap_item):
                self._is_panning = True
                self._pan_start_pos = pos
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_panning:
            pos = event.position().toPoint()
            delta = pos - self._pan_start_pos
            self._pan_start_pos = pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_panning:
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ==============================================================
    # ================= 🌟 [空格键秒切透视原图核心机制] =============
    # ==============================================================
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.is_space_pressed = True
            self.hover_hud.hide()
            # 瞬间隐藏所有标注图元，100% 露出纯净底层 X-ray 原图
            for item in self.solder_items:
                item.setVisible(False)
            for b_item in self.bridge_items:
                b_item.setVisible(False)
            event.accept()
            return
        elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            event.ignore()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._is_fit_mode and not self.is_crop_mode and self.pixmap_item:
            self.fit_in_view()

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.is_space_pressed = False
            # 松开空格键瞬间恢复所有标注图元
            for item in self.solder_items:
                item.setVisible(True)
            for b_item in self.bridge_items:
                b_item.setVisible(self.current_view_mode != "raw_image")
            event.accept()
            return
        super().keyReleaseEvent(event)

    # ==============================================================
    # ================= 🌟 [视口辅助缩放工具] =======================
    # ==============================================================
    def fit_in_view(self):
        """自适应窗口居中"""
        if self.pixmap_item:
            self._is_fit_mode = True
            self.resetTransform()
            self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            self.current_zoom = self.transform().m11()
            self.sig_zoom_changed.emit(self.current_zoom)

    def set_zoom(self, target_zoom: float):
        self._is_fit_mode = False
        ratio = target_zoom / (self.current_zoom if self.current_zoom > 0 else 1.0)
        self.scale(ratio, ratio)
        self.current_zoom = self.transform().m11()
        self.sig_zoom_changed.emit(self.current_zoom)

    def zoom_1to1(self):
        """1:1 像素真实还原"""
        self._is_fit_mode = False
        self.resetTransform()
        self.current_zoom = 1.0
        self.sig_zoom_changed.emit(self.current_zoom)

    def zoom_in(self, factor: float = 1.25):
        """视口放大"""
        self.hover_hud.hide()
        new_zoom = self.current_zoom * factor
        if new_zoom <= 30.0:
            self._is_fit_mode = False
            self.scale(factor, factor)
            self.current_zoom = self.transform().m11()
            self.sig_zoom_changed.emit(self.current_zoom)

    def zoom_out(self, factor: float = 1.25):
        """视口缩小"""
        self.hover_hud.hide()
        new_zoom = self.current_zoom / factor
        if new_zoom >= 0.05:
            self._is_fit_mode = False
            self.scale(1.0 / factor, 1.0 / factor)
            self.current_zoom = self.transform().m11()
            self.sig_zoom_changed.emit(self.current_zoom)

    def drawForeground(self, painter: QPainter, rect: QRectF):
        super().drawForeground(painter, rect)
        if self.pixmap_item is None:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            vw = self.viewport().width()
            vh = self.viewport().height()

            painter.resetTransform()
            box_w, box_h = 380, 96
            bx = (vw - box_w) / 2
            by = (vh - box_h) / 2

            painter.setPen(QPen(QColor(39, 52, 73, 180), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor(17, 23, 38, 140)))
            painter.drawRoundedRect(QRectF(bx, by, box_w, box_h), 8, 8)

            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            painter.setPen(QColor(148, 163, 184))
            painter.drawText(QRectF(bx, by + 18, box_w, 24), Qt.AlignmentFlag.AlignCenter, "待检工件显示视口 (空白)")

            painter.setFont(QFont("Segoe UI", 9))
            painter.setPen(QColor(100, 116, 139))
            painter.drawText(QRectF(bx, by + 50, box_w, 20), Qt.AlignmentFlag.AlignCenter, "请点击左侧【打开单张图片】或【批量质检目录】载入图像")
            painter.restore()

    # ==============================================================
    # ================= 🌟 [事件回调处理] ===========================
    # ==============================================================
    def _handle_ball_clicked(self, ball_index: int):
        self.sig_ball_selected.emit(ball_index)

    def _handle_hover_enter(self, record: SolderBallRecord):
        center_view = self.mapFromScene(QPointF(record.cx, record.cy))
        radius_view = record.radius * self.transform().m11()
        self.hover_hud.update_data(
            index=record.index,
            status=record.status,
            cx=record.cx,
            cy=record.cy,
            void_rate=record.void_rate,
            is_void_ng=record.is_void_ng,
            reduction_percent=record.reduction_percent,
            is_insuff=record.is_insufficient,
            is_bridge=record.is_bridge,
        )
        self.hover_hud.show_above_ball(center_view, radius_view, self.viewport().size())

    def _handle_hover_leave(self):
        self.hover_hud.hide()
