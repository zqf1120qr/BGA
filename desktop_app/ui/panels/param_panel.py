# -*- coding: utf-8 -*-
"""
🌟 硬件感知与质检算法参数面板 (Parameter Panel)
-----------------------------------------------
遵循右侧看板标准，包含两个独立的圆角矩形背景卡片：
1. 【运算引擎与质检模式】(Card 2 - EngineCard)
2. 【算法判废门限微调】(Card 3 - ThreshCard)
组件具备清晰的钢灰色描边，悬停触发亮蓝高光 (#1e3a8a / #38bdf8)，与全部焊球按钮完全一致。
"""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from desktop_app.app_config import InspectionConfig
from desktop_app.core.hardware_sniff import hardware_sniffer


class ParamPanel(QFrame):
    sig_threshold_changed = Signal(float, float)  # (ng_void_thresh, undersize_thresh)
    sig_config_changed = Signal()
    sig_hardware_updated = Signal(str, str)       # (status_text, color)

    def __init__(self, config: InspectionConfig, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self.setObjectName("ParamPanel")

        panel_layout = QVBoxLayout(self)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(10)

        # ==========================================================
        # 1. 独立卡片：运算引擎与质检维度 (EngineCard)
        # ==========================================================
        self.card_engine = QFrame()
        self.card_engine.setObjectName("EngineCard")
        engine_layout = QVBoxLayout(self.card_engine)
        engine_layout.setContentsMargins(12, 12, 12, 12)
        engine_layout.setSpacing(8)

        lbl_engine_head = QLabel("运算引擎与质检维度")
        lbl_engine_head.setStyleSheet("font-weight: 700; font-size: 13px; color: #f1f5f9; padding: 2px 0 4px 0;")
        engine_layout.addWidget(lbl_engine_head)

        lbl_hw_title = QLabel("运算引擎模式:")
        lbl_hw_title.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        engine_layout.addWidget(lbl_hw_title)

        self.cb_hardware = QComboBox()
        self.cb_hardware.setMinimumHeight(32)
        self.cb_hardware.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_hardware.addItems([
            "自动感知 (GPU优先 / 自动防灾)",
            "强制指定 GPU (CUDA:0)",
            "纯 CPU 多核并发模式"
        ])
        self.cb_hardware.currentIndexChanged.connect(self._on_hardware_changed)
        engine_layout.addWidget(self.cb_hardware)

        # 硬件状态展示标签 (兼容原有属性)
        self.lbl_hw_status = QLabel("● 正在探测计算硬件...")
        self.lbl_hw_status.setStyleSheet("color: #10b981; font-size: 11px; padding: 2px 4px;")
        self.lbl_hw_status.hide()

        lbl_mode_title = QLabel("质检维度范围:")
        lbl_mode_title.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600; margin-top: 2px;")
        engine_layout.addWidget(lbl_mode_title)

        self.cb_mode = QComboBox()
        self.cb_mode.setMinimumHeight(32)
        self.cb_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_mode.addItem("全项综合质检 (气泡 + 桥连 + 虚焊)", "comprehensive")
        self.cb_mode.addItem("仅气泡质检 (Void Only)", "void")
        self.cb_mode.addItem("仅桥连质检 (Bridge Only)", "bridge")
        self.cb_mode.addItem("仅虚焊少锡质检 (Insufficient Only)", "insufficient")
        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)
        engine_layout.addWidget(self.cb_mode)

        panel_layout.addWidget(self.card_engine)

        # ==========================================================
        # 2. 独立卡片：算法判废门限微调 (ThreshCard)
        # ==========================================================
        self.card_thresh = QFrame()
        self.card_thresh.setObjectName("ThreshCard")
        thresh_layout = QVBoxLayout(self.card_thresh)
        thresh_layout.setContentsMargins(12, 12, 12, 12)
        thresh_layout.setSpacing(10)

        lbl_thresh_head = QLabel("算法判废门限微调")
        lbl_thresh_head.setStyleSheet("font-weight: 700; font-size: 13px; color: #f1f5f9; padding: 2px 0 4px 0;")
        thresh_layout.addWidget(lbl_thresh_head)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        # A. 检出置信度 (Conf)
        lbl_conf_title = QLabel("检出置信度:")
        lbl_conf_title.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        lbl_conf_title.setToolTip(
            "【检出置信度 (Confidence Threshold)】\n"
            "YOLO 深度学习模型初筛候选焊球的置信度门限 (10% ~ 90%)。\n"
            "• 默认设定为 20% (0.20)，兼顾极暗、低对比度边缘弱小焊球的最高召回率；\n"
            "• 多余或误检伪点将由后序拓扑阵列规则自动过滤清洗；\n"
            "• 若基板严重反光或背景杂散干扰过多，可微调至 35% ~ 50%。"
        )
        grid.addWidget(lbl_conf_title, 0, 0)
        self.slider_conf = QSlider(Qt.Orientation.Horizontal)
        self.slider_conf.setRange(10, 90)
        self.slider_conf.setValue(int(self.config.conf_threshold * 100))
        self.slider_conf.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_conf_val = QLabel(f"{self.slider_conf.value()}%")
        self.lbl_conf_val.setStyleSheet("font-weight: bold; color: #38bdf8; font-size: 12px; min-width: 36px;")
        self.slider_conf.valueChanged.connect(self._on_conf_slider_changed)
        grid.addWidget(self.slider_conf, 0, 1)
        grid.addWidget(self.lbl_conf_val, 0, 2)

        # B. 气泡超标阈值 (5% ~ 50%)
        lbl_void_title = QLabel("气泡超标阈值:")
        lbl_void_title.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        lbl_void_title.setToolTip(
            "【气泡空洞率阈值 (Void Threshold)】\n"
            "单焊球内气泡空洞投影面积占焊球总面积的百分比上限，超过此值判为 NG。\n"
            "• IPC-A-610 国际电子组装标准推荐判定线为 25%。"
        )
        grid.addWidget(lbl_void_title, 1, 0)
        self.slider_void = QSlider(Qt.Orientation.Horizontal)
        self.slider_void.setRange(5, 50)
        self.slider_void.setValue(int(self.config.ng_void_threshold * 100))
        self.slider_void.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_void_val = QLabel(f"{self.slider_void.value()}%")
        self.lbl_void_val.setStyleSheet("font-weight: bold; color: #f43f5e; font-size: 12px; min-width: 36px;")
        self.slider_void.valueChanged.connect(self._on_void_slider_changed)
        grid.addWidget(self.slider_void, 1, 1)
        grid.addWidget(self.lbl_void_val, 1, 2)

        # C. 虚焊少锡判定阈值 (5% ~ 50%)
        lbl_insuff_title = QLabel("虚焊少锡阈值:")
        lbl_insuff_title.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        lbl_insuff_title.setToolTip(
            "【虚焊少锡判定阈值 (Insufficient Solder Threshold)】\n"
            "焊球实测面积相对于整板焊球基准面积的缩减容忍上限，缩减比例超过此值判为虚焊少锡。\n"
            "• 例如设为 20% 时，若某焊球比平均面积小 20% 以上，即报警提示虚焊少锡风险。\n"
            "• 工业推荐值: 20%。"
        )
        grid.addWidget(lbl_insuff_title, 2, 0)
        self.slider_insuff = QSlider(Qt.Orientation.Horizontal)
        self.slider_insuff.setRange(5, 50)
        self.slider_insuff.setValue(int(self.config.undersize_threshold * 100))
        self.slider_insuff.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_insuff_val = QLabel(f"{self.slider_insuff.value()}%")
        self.lbl_insuff_val.setStyleSheet("font-weight: bold; color: #f59e0b; font-size: 12px; min-width: 36px;")
        self.slider_insuff.valueChanged.connect(self._on_insuff_slider_changed)
        grid.addWidget(self.slider_insuff, 2, 1)
        grid.addWidget(self.lbl_insuff_val, 2, 2)

        thresh_layout.addLayout(grid)

        # 底部提示小标签
        lbl_conf_hint = QLabel("提示: 鼠标悬停在指标名称上可查看详细工业原理与建议值")
        lbl_conf_hint.setStyleSheet("color: #64748b; font-size: 10px; margin-top: 4px;")
        thresh_layout.addWidget(lbl_conf_hint)

        thresh_layout.addStretch(1)

        panel_layout.addWidget(self.card_thresh, stretch=1)

        # 刷新硬件状态
        self._refresh_hardware_status()

    def _refresh_hardware_status(self):
        idx = self.cb_hardware.currentIndex()
        pref_map = {0: "auto", 1: "0", 2: "cpu"}
        user_pref = pref_map.get(idx, "auto")
        self.config.hardware_device = user_pref

        _, status_text, color = hardware_sniffer.resolve_device(user_pref)
        self.lbl_hw_status.setText(f"● {status_text}")
        self.sig_hardware_updated.emit(status_text, color)

    def _on_hardware_changed(self):
        self._refresh_hardware_status()
        self.sig_config_changed.emit()

    def _on_mode_changed(self):
        self.config.inspection_mode = self.cb_mode.currentData()
        self.sig_config_changed.emit()

    def _on_void_slider_changed(self, val: int):
        self.lbl_void_val.setText(f"{val}%")
        self.config.ng_void_threshold = val / 100.0
        self.sig_threshold_changed.emit(self.config.ng_void_threshold, self.config.undersize_threshold)

    def _on_insuff_slider_changed(self, val: int):
        self.lbl_insuff_val.setText(f"{val}%")
        self.config.undersize_threshold = val / 100.0
        self.sig_threshold_changed.emit(self.config.ng_void_threshold, self.config.undersize_threshold)

    def _on_conf_slider_changed(self, val: int):
        self.lbl_conf_val.setText(f"{val}%")
        self.config.conf_threshold = val / 100.0
        self.sig_config_changed.emit()
