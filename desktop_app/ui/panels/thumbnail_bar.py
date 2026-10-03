# -*- coding: utf-8 -*-
"""
🌟 批量质检图像胶卷式缩略图栏 (Batch Thumbnail Strip & Switcher)
----------------------------------------------------------------
部署于主视口中央下半部分，专用于批量质检场景：
1. 顶部操作栏提供【◀ 上一张】、【下一张 ▶】、当前图像指示与缺陷统计芯片；
2. 底部胶卷栏横向排列每一张图片的微缩预览图、文件名与实时质检状态 (待检 / 质检中 / PASS / NG)；
3. 支持鼠标单击缩略图切换、键盘左右方向键 (← / →) 毫秒级秒切；
4. 选中项具备醒目亮青色外框 (#38bdf8)，自动滚动居中。
"""
from __future__ import annotations

import os
from typing import List, Optional
import cv2
import numpy as np

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImageReader, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from desktop_app.core.image_converter import cv_mat_to_qpixmap, load_image_unicode


def _generate_thumb_pixmap(file_path: str, max_w: int = 80, max_h: int = 48) -> QPixmap:
    """快速生成工件图像缩略图 Pixmap"""
    try:
        reader = QImageReader(file_path)
        if reader.canRead():
            sz = reader.size()
            if sz.isValid() and sz.width() > 0:
                scaled_sz = sz.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(scaled_sz)
                img = reader.read()
                if not img.isNull():
                    return QPixmap.fromImage(img)
    except Exception:
        pass

    # 兜底：通过 load_image_unicode 读取并双三次降采样
    try:
        mat = load_image_unicode(file_path)
        if mat is not None and mat.size > 0:
            h, w = mat.shape[:2]
            scale = min(max_w / w, max_h / h)
            nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
            resized = cv2.resize(mat, (nw, nh), interpolation=cv2.INTER_AREA)
            return cv_mat_to_qpixmap(resized)
    except Exception:
        pass

    # 若无法解析则返回空黑色占位图
    pix = QPixmap(max_w, max_h)
    pix.fill(QColor(15, 23, 42))
    return pix


class ThumbnailCard(QFrame):
    """单张图像微缩预览胶卷卡片"""
    sig_clicked = Signal(int)

    def __init__(self, index: int, file_path: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("ThumbnailCard")
        self.index = index
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.status = "pending"  # "pending", "inspecting", "PASS", "NG"
        self.is_selected = False

        self.setFixedSize(102, 88)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        card_tip = f"【工件序号: {index + 1}】\n文件名: {self.filename}\n(单击在视口中切换并查看此图像)"
        self.setToolTip(card_tip)

        self._setup_ui()
        self.lbl_thumb.setToolTip(card_tip)
        self.lbl_name.setToolTip(f"工件图像文件名: {self.filename}")
        self.lbl_badge.setToolTip("【质检状态: 待检测】\n等待启动执行质检任务")
        self._update_appearance()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # 1. 缩略图视口
        self.lbl_thumb = QLabel()
        self.lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_thumb.setFixedHeight(48)
        self.lbl_thumb.setStyleSheet("background-color: #0b0f19; border: none; border-radius: 3px;")

        thumb_pix = _generate_thumb_pixmap(self.file_path, 92, 48)
        self.lbl_thumb.setPixmap(thumb_pix)
        layout.addWidget(self.lbl_thumb)

        # 2. 底部信息行：文件名与状态角标
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(2, 0, 2, 0)
        bottom_row.setSpacing(2)

        self.lbl_name = QLabel(self.filename)
        self.lbl_name.setStyleSheet("font-size: 10px; color: #94a3b8; font-weight: 500; border: none; background: transparent;")
        # 裁剪展示文件名
        name_short = self.filename
        if len(name_short) > 7:
            name_short = name_short[:6] + ".."
        self.lbl_name.setText(name_short)

        self.lbl_badge = QLabel("待检")
        self.lbl_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_badge.setFixedHeight(18)
        self.lbl_badge.setFixedWidth(44)
        self.lbl_badge.setStyleSheet("""
            background-color: #1e293b;
            color: #64748b;
            font-size: 9.5px;
            font-weight: bold;
            border: none;
            border-radius: 3px;
            padding: 0px 2px;
        """)

        bottom_row.addWidget(self.lbl_name)
        bottom_row.addStretch()
        bottom_row.addWidget(self.lbl_badge)

        layout.addLayout(bottom_row)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        self._update_appearance()

    def set_status(self, status: str):
        self.status = status
        if status == "inspecting":
            self.lbl_badge.setText("质检中")
            self.lbl_badge.setToolTip("【当前状态: 正在质检】\n正在执行 AI 深度学习与几何判废分析...")
            self.lbl_badge.setStyleSheet("""
                background-color: #0284c7;
                color: #ffffff;
                font-size: 9.5px;
                font-weight: bold;
                border: none;
                border-radius: 3px;
                padding: 0px 2px;
            """)
        elif status == "PASS":
            self.lbl_badge.setText("PASS")
            self.lbl_badge.setToolTip("【当前结论: 合格 (PASS)】\n焊点气泡率、少锡指标与桥连短路检测全部通过")
            self.lbl_badge.setStyleSheet("""
                background-color: #064e3b;
                color: #34d399;
                font-size: 9.5px;
                font-weight: bold;
                border: none;
                border-radius: 3px;
                padding: 0px 2px;
            """)
        elif status == "NG":
            self.lbl_badge.setText("NG")
            self.lbl_badge.setToolTip("【当前结论: 缺陷 (NG)】\n存在气泡超标、虚焊少锡或桥连短路缺陷")
            self.lbl_badge.setStyleSheet("""
                background-color: #7f1d1d;
                color: #f87171;
                font-size: 9.5px;
                font-weight: bold;
                border: none;
                border-radius: 3px;
                padding: 0px 2px;
            """)
        else:
            self.lbl_badge.setText("待检")
            self.lbl_badge.setToolTip("【当前状态: 待检测】\n等待启动执行质检任务")
            self.lbl_badge.setStyleSheet("""
                background-color: #1e293b;
                color: #64748b;
                font-size: 9.5px;
                font-weight: bold;
                border: none;
                border-radius: 3px;
                padding: 0px 2px;
            """)
        self._update_appearance()

    def _update_appearance(self):
        if self.is_selected:
            self.setStyleSheet("""
                #ThumbnailCard {
                    background-color: #162035;
                    border: 2px solid #38bdf8;
                    border-radius: 6px;
                }
            """)
        else:
            self.setStyleSheet("""
                #ThumbnailCard {
                    background-color: #0f172a;
                    border: 1px solid #1e293b;
                    border-radius: 6px;
                }
                #ThumbnailCard:hover {
                    background-color: #131d33;
                    border: 1px solid #475569;
                }
            """)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.sig_clicked.emit(self.index)
            event.accept()
        else:
            super().mousePressEvent(event)


class BatchThumbnailBar(QFrame):
    """批量质检底栏：导航切换器与图像缩略图胶卷"""
    sig_image_selected = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("BatchThumbnailBar")
        self.setFixedHeight(144)
        self.setStyleSheet("""
            QFrame#BatchThumbnailBar {
                background-color: #111726;
                border-top: 1px solid #1e293b;
            }
        """)

        self.cards: List[ThumbnailCard] = []
        self.current_index: int = -1
        self.image_paths: List[str] = []

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(6)

        # 1. 顶部操控与统计栏
        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(2, 0, 2, 0)
        nav_row.setSpacing(8)

        self.btn_prev = QPushButton("◀ 上一张")
        self.btn_prev.setObjectName("BtnNav")
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev.setToolTip("快捷键: 键盘向左方向键 [←]")
        self.btn_prev.clicked.connect(self._on_prev_clicked)

        self.lbl_counter = QLabel("[ 0 / 0 ]  无待检图像")
        self.lbl_counter.setStyleSheet("font-size: 12px; font-weight: bold; color: #38bdf8; min-width: 130px;")

        self.btn_next = QPushButton("下一张 ▶")
        self.btn_next.setObjectName("BtnNav")
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.setToolTip("快捷键: 键盘向右方向键 [→]")
        self.btn_next.clicked.connect(self._on_next_clicked)

        self.lbl_hint = QLabel("(支持点击缩略图或按键盘 ← / → 快速切图)")
        self.lbl_hint.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 400;")

        nav_row.addWidget(self.btn_prev)
        nav_row.addWidget(self.lbl_counter)
        nav_row.addWidget(self.btn_next)
        nav_row.addWidget(self.lbl_hint)
        nav_row.addStretch()

        # 批次质量指标徽章
        self.lbl_badge_total = QLabel("总数: 0")
        self.lbl_badge_total.setStyleSheet("background-color: #1e293b; color: #94a3b8; font-size: 11px; padding: 2px 7px; border-radius: 4px; font-weight: 500;")

        self.lbl_badge_pass = QLabel("合格: 0")
        self.lbl_badge_pass.setStyleSheet("background-color: #064e3b; color: #34d399; font-size: 11px; padding: 2px 7px; border-radius: 4px; font-weight: 600;")

        self.lbl_badge_ng = QLabel("缺陷: 0")
        self.lbl_badge_ng.setStyleSheet("background-color: #7f1d1d; color: #f87171; font-size: 11px; padding: 2px 7px; border-radius: 4px; font-weight: 600;")

        nav_row.addWidget(self.lbl_badge_total)
        nav_row.addWidget(self.lbl_badge_pass)
        nav_row.addWidget(self.lbl_badge_ng)

        main_layout.addLayout(nav_row)

        # 2. 底部横向滚动胶卷区
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("ThumbnailScrollArea")
        self.scroll_area.setFixedHeight(100)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea#ThumbnailScrollArea {
                background-color: transparent;
                border: none;
            }
        """)

        self.cards_container = QWidget()
        self.cards_container.setObjectName("ThumbnailCardsContainer")
        self.cards_container.setStyleSheet("background-color: transparent;")
        self.cards_layout = QHBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(2, 2, 2, 2)
        self.cards_layout.setSpacing(6)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.scroll_area.setWidget(self.cards_container)
        main_layout.addWidget(self.scroll_area)

    def load_images(self, file_paths: List[str]):
        """加载批量图像列表，动态构建胶卷卡片"""
        self.clear()
        self.image_paths = list(file_paths)
        total = len(file_paths)

        for idx, fp in enumerate(file_paths):
            card = ThumbnailCard(index=idx, file_path=fp, parent=self.cards_container)
            card.sig_clicked.connect(self._handle_card_clicked)
            self.cards_layout.addWidget(card)
            self.cards.append(card)

        self.lbl_badge_total.setText(f"总数: {total}")
        self.lbl_badge_pass.setText("合格: 0")
        self.lbl_badge_ng.setText("缺陷: 0")

        if total > 0:
            self.set_current_index(0)
        else:
            self.current_index = -1
            self.lbl_counter.setText("[ 0 / 0 ]  无待检图像")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)

    def clear(self):
        """清空胶卷与卡片"""
        for card in self.cards:
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
        self.image_paths.clear()
        self.current_index = -1

    def set_current_index(self, index: int, scroll_to: bool = True):
        """设置当前高亮选中的图像序号"""
        if index < 0 or index >= len(self.cards):
            return

        self.current_index = index
        total = len(self.cards)
        fname = os.path.basename(self.image_paths[index])
        self.lbl_counter.setText(f"[ {index + 1} / {total} ]  {fname}")

        self.btn_prev.setEnabled(index > 0)
        self.btn_next.setEnabled(index < total - 1)

        for idx, card in enumerate(self.cards):
            card.set_selected(idx == index)

        if scroll_to and 0 <= index < len(self.cards):
            target_card = self.cards[index]
            self.scroll_area.ensureWidgetVisible(target_card, 40, 0)

    def set_item_status(self, index: int, status: str):
        """更新指定卡片的质检状态"""
        if 0 <= index < len(self.cards):
            self.cards[index].set_status(status)
            self._recalculate_badge_counts()

    def _recalculate_badge_counts(self):
        pass_count = sum(1 for c in self.cards if c.status == "PASS")
        ng_count = sum(1 for c in self.cards if c.status == "NG")
        self.lbl_badge_pass.setText(f"合格: {pass_count}")
        self.lbl_badge_ng.setText(f"缺陷: {ng_count}")

    def _handle_card_clicked(self, index: int):
        if index != self.current_index:
            self.set_current_index(index, scroll_to=False)
            self.sig_image_selected.emit(index)

    def _on_prev_clicked(self):
        if self.current_index > 0:
            new_idx = self.current_index - 1
            self.set_current_index(new_idx, scroll_to=True)
            self.sig_image_selected.emit(new_idx)

    def _on_next_clicked(self):
        if self.current_index < len(self.cards) - 1:
            new_idx = self.current_index + 1
            self.set_current_index(new_idx, scroll_to=True)
            self.sig_image_selected.emit(new_idx)
