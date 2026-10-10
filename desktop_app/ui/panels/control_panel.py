# -*- coding: utf-8 -*-
"""
🌟 待检工件管理与任务执行面板 (Control & Action Panel)
------------------------------------------------------
完全与右侧看板对齐的工业级圆角矩形体系：
1. 顶部卡片：【待检工件与图像输入】(Card 1 - ImageCard)
2. 运算引擎与质检维度 (Card 2 - EngineCard)
3. 算法判废门限微调 (Card 3 - ThreshCard)
4. 任务执行与报告交付 (Card 4 - ActionCard)
全部独立卡片拥有与右侧看板 100% 相同的圆角、深色背景、描边与悬浮高光反馈。
"""
from __future__ import annotations

import os
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ControlActionPanel(QFrame):
    sig_open_image = Signal(str)           # 打开单图 (文件路径)
    sig_open_folder = Signal(str)          # 打开批量目录 (文件夹路径)
    sig_enter_crop = Signal()              # 请求进入裁剪模式
    sig_confirm_crop = Signal()            # 确认裁剪
    sig_cancel_crop = Signal()             # 取消裁剪
    sig_reset_image = Signal()             # 重置回原始图像
    sig_start_inspection = Signal()        # 开始质检任务
    sig_stop_inspection = Signal()         # 停止质检任务
    sig_export_pdf = Signal()              # 导出 PDF 报告
    sig_export_excel = Signal()            # 导出 Excel 报表

    def __init__(self, param_panel: Optional[QWidget] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("ControlActionPanel")
        self.param_panel = param_panel

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        # ==========================================================
        # 1. 顶部卡片：待检工件与图像输入 (Card 1)
        # ==========================================================
        self.card_image = QFrame()
        self.card_image.setObjectName("ImageCard")
        card_image_layout = QVBoxLayout(self.card_image)
        card_image_layout.setContentsMargins(12, 10, 12, 10)
        card_image_layout.setSpacing(8)

        lbl_data = QLabel("待检图像与板卡导入")
        lbl_data.setStyleSheet("font-weight: 700; font-size: 13px; color: #f1f5f9; padding: 2px 0 4px 0;")
        card_image_layout.addWidget(lbl_data)

        btn_row_img = QHBoxLayout()
        btn_row_img.setSpacing(8)
        self.btn_open_img = QPushButton("打开单张图片")
        self.btn_open_img.setMinimumHeight(32)
        self.btn_open_img.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_img.clicked.connect(self._select_image_file)

        self.btn_open_dir = QPushButton("批量检测目录")
        self.btn_open_dir.setMinimumHeight(32)
        self.btn_open_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_dir.clicked.connect(self._select_folder)

        btn_row_img.addWidget(self.btn_open_img)
        btn_row_img.addWidget(self.btn_open_dir)
        card_image_layout.addLayout(btn_row_img)

        # 当前工件与硬件参数指标网格 (与右侧 ResultGridFrame 保持 100% 相同视觉质感)
        file_card = QFrame()
        file_card.setObjectName("FileInfoFrame")
        file_grid = QGridLayout(file_card)
        file_grid.setContentsMargins(10, 8, 10, 8)
        file_grid.setHorizontalSpacing(12)
        file_grid.setVerticalSpacing(6)

        def _mk_key(t: str) -> QLabel:
            l = QLabel(t)
            l.setStyleSheet("color: #94a3b8; font-size: 11px;")
            return l

        file_grid.addWidget(_mk_key("当前板卡/图片:"), 0, 0)
        self.lbl_current_file = QLabel("(未加载)")
        self.lbl_current_file.setStyleSheet("color: #f1f5f9; font-weight: bold; font-size: 12px;")
        file_grid.addWidget(self.lbl_current_file, 0, 1)

        file_grid.addWidget(_mk_key("图像尺寸:"), 1, 0)
        self.lbl_file_dim = QLabel("-- × -- px")
        self.lbl_file_dim.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 12px;")
        file_grid.addWidget(self.lbl_file_dim, 1, 1)

        card_image_layout.addWidget(file_card)

        # 裁剪交互控制
        self.btn_crop = QPushButton("框选局部区域裁剪 (ROI)")
        self.btn_crop.setMinimumHeight(32)
        self.btn_crop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_crop.clicked.connect(self._on_enter_crop)
        card_image_layout.addWidget(self.btn_crop)

        # 裁剪操作确认/取消栏 (平时隐藏)
        self.crop_action_frame = QFrame()
        crop_action_layout = QHBoxLayout(self.crop_action_frame)
        crop_action_layout.setContentsMargins(0, 0, 0, 0)
        crop_action_layout.setSpacing(8)

        self.btn_confirm_crop = QPushButton("确认裁剪")
        self.btn_confirm_crop.setObjectName("BtnConfirm")
        self.btn_confirm_crop.setMinimumHeight(32)
        self.btn_confirm_crop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirm_crop.clicked.connect(self.sig_confirm_crop.emit)

        self.btn_cancel_crop = QPushButton("取消")
        self.btn_cancel_crop.setObjectName("BtnCancel")
        self.btn_cancel_crop.setMinimumHeight(32)
        self.btn_cancel_crop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel_crop.clicked.connect(self.sig_cancel_crop.emit)

        crop_action_layout.addWidget(self.btn_confirm_crop)
        crop_action_layout.addWidget(self.btn_cancel_crop)
        self.crop_action_frame.hide()
        card_image_layout.addWidget(self.crop_action_frame)

        self.btn_reset_img = QPushButton("恢复完整大图")
        self.btn_reset_img.setMinimumHeight(32)
        self.btn_reset_img.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_img.clicked.connect(self.sig_reset_image.emit)
        self.btn_reset_img.hide()
        card_image_layout.addWidget(self.btn_reset_img)

        main_layout.addWidget(self.card_image)

        # ==========================================================
        # 2. 中间卡片区：运算引擎 (Card 2) 与算法判废 (Card 3)
        # ==========================================================
        if self.param_panel is not None:
            main_layout.addWidget(self.param_panel, stretch=1)
            if hasattr(self.param_panel, "sig_hardware_updated"):
                self.param_panel.sig_hardware_updated.connect(self._on_hardware_updated)

        # ==========================================================
        # 3. 底部独立卡片：任务执行与报告交付 (Card 4)
        # ==========================================================
        self.card_action = QFrame()
        self.card_action.setObjectName("ActionCard")
        action_layout = QVBoxLayout(self.card_action)
        action_layout.setContentsMargins(12, 10, 12, 10)
        action_layout.setSpacing(8)

        self.btn_start = QPushButton("开始执行质检任务")
        self.btn_start.setObjectName("BtnPrimary")
        self.btn_start.setMinimumHeight(42)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self.sig_start_inspection.emit)
        action_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("终止任务")
        self.btn_stop.setObjectName("BtnCancel")
        self.btn_stop.setMinimumHeight(36)
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.clicked.connect(self.sig_stop_inspection.emit)
        self.btn_stop.hide()
        action_layout.addWidget(self.btn_stop)

        btn_row_rep = QHBoxLayout()
        btn_row_rep.setSpacing(8)
        self.btn_export_pdf = QPushButton("导出 PDF 报告")
        self.btn_export_pdf.setMinimumHeight(32)
        self.btn_export_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_pdf.clicked.connect(self.sig_export_pdf.emit)

        self.btn_export_excel = QPushButton("导出 Excel 报表")
        self.btn_export_excel.setMinimumHeight(32)
        self.btn_export_excel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_excel.clicked.connect(self.sig_export_excel.emit)

        btn_row_rep.addWidget(self.btn_export_pdf)
        btn_row_rep.addWidget(self.btn_export_excel)
        action_layout.addLayout(btn_row_rep)

        main_layout.addWidget(self.card_action)

    def _on_hardware_updated(self, status_text: str, color: str):
        pass

    def set_current_filename(self, name: str, width: int = 0, height: int = 0):
        self.lbl_current_file.setText(name)
        if width > 0 and height > 0:
            self.lbl_file_dim.setText(f"{width} × {height} px")
        else:
            self.lbl_file_dim.setText("-- × -- px")

    def show_crop_actions(self, show: bool):
        if show:
            self.crop_action_frame.show()
            self.btn_crop.hide()
        else:
            self.crop_action_frame.hide()
            self.btn_crop.show()

    def set_running_state(self, running: bool):
        self.btn_start.setVisible(not running)
        self.btn_stop.setVisible(running)
        self.btn_open_img.setEnabled(not running)
        self.btn_open_dir.setEnabled(not running)
        self.btn_crop.setEnabled(not running)

    def _select_image_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择待检测的 BGA X-Ray 图像",
            "",
            "图像文件 (*.jpg *.jpeg *.png *.bmp *.tif);;所有文件 (*.*)"
        )
        if file_path:
            self.sig_open_image.emit(file_path)

    def _select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "选择包含 BGA 图像的待检目录"
        )
        if folder_path:
            self.sig_open_folder.emit(folder_path)

    def _on_enter_crop(self):
        self.show_crop_actions(True)
        self.sig_enter_crop.emit()
