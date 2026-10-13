# -*- coding: utf-8 -*-
"""
硬件感知与质检算法参数面板 (Parameter Panel)
-----------------------------------------------
遵循右侧看板标准，包含两个独立的圆角矩形背景卡片：
1. 【检测项目设置】(Card 2 - EngineCard)
2. 【合格判定标准设置】(Card 3 - ThreshCard)
包含滑块与高精度手输框双向实时联动，支持工艺配方 JSON 一键导入导出与默认值管理。
"""
from __future__ import annotations

import os
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from desktop_app.app_config import InspectionConfig, app_config_mgr
from desktop_app.core.hardware_sniff import hardware_sniffer
from desktop_app.ui.styles.color_palette import DefectColors


class HorizontalNumericStepper(QWidget):
    """
    工业级左右布局水平数值步进器 (Horizontal Numeric Stepper)
    ---------------------------------------------------------
    1. 左右按钮布局：左侧 [-] 减号，中间纯数字输入框，右侧 [+] 加号；
    2. 纯数字显示：彻底去除 '%' 百分号，文本居中对齐；
    3. 全手形光标：加减按钮均为 PointingHandCursor 手形光标，并支持长按快速连加连减；
    4. 消除边框溢出：彻底禁用 Qt 原生上下堆叠按键，中间输入框获得焦点时整体完美高亮对应缺陷色。
    """
    valueChanged = Signal(float)

    def __init__(
        self,
        min_val: float,
        max_val: float,
        step: float,
        decimals: int = 1,
        color_hex: str = "#10b981",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        self.decimals = decimals
        self.color_hex = color_hex

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        # 左侧减号按钮 [-]
        self.btn_minus = QPushButton("—")
        self.btn_minus.setFixedSize(22, 26)
        self.btn_minus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_minus.setAutoRepeat(True)
        self.btn_minus.setAutoRepeatDelay(300)
        self.btn_minus.setAutoRepeatInterval(80)
        self.btn_minus.setToolTip("减少数值 (步长微调)")

        # 中间纯数字输入框 (隐藏所有原生上下按键，彻底防止边框切断或溢出)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(min_val, max_val)
        self.spin.setSingleStep(step)
        self.spin.setDecimals(decimals)
        self.spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin.setFixedHeight(26)
        self.spin.setFixedWidth(52)
        self.spin.setCursor(Qt.CursorShape.IBeamCursor)

        # 右侧加号按钮 [+]
        self.btn_plus = QPushButton("+")
        self.btn_plus.setFixedSize(22, 26)
        self.btn_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_plus.setAutoRepeat(True)
        self.btn_plus.setAutoRepeatDelay(300)
        self.btn_plus.setAutoRepeatInterval(80)
        self.btn_plus.setToolTip("增加数值 (步长微调)")

        layout.addWidget(self.btn_minus)
        layout.addWidget(self.spin)
        layout.addWidget(self.btn_plus)

        btn_qss = """
            QPushButton {
                background-color: #1e293b;
                color: #ffffff;
                border: 1px solid #334155;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #64748b;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #0f172a;
            }
        """
        self.btn_minus.setStyleSheet(btn_qss)
        self.btn_plus.setStyleSheet(btn_qss)

        spin_qss = f"""
            QDoubleSpinBox {{
                background-color: #0b1120;
                color: {color_hex};
                border: 1px solid #334155;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
                padding: 0px 2px;
            }}
            QDoubleSpinBox:hover {{
                border: 1px solid #475569;
            }}
            QDoubleSpinBox:focus {{
                border: 1px solid {color_hex};
                background-color: #0f172a;
            }}
        """
        self.spin.setStyleSheet(spin_qss)

        self.btn_minus.clicked.connect(self._step_down)
        self.btn_plus.clicked.connect(self._step_up)
        self.spin.valueChanged.connect(self.valueChanged)

    def _step_down(self):
        new_val = max(self.min_val, self.spin.value() - self.step)
        self.spin.setValue(round(new_val, self.decimals))

    def _step_up(self):
        new_val = min(self.max_val, self.spin.value() + self.step)
        self.spin.setValue(round(new_val, self.decimals))

    def value(self) -> float:
        return self.spin.value()

    def setValue(self, val: float):
        self.spin.setValue(val)

    def blockSignals(self, b: bool) -> bool:
        return self.spin.blockSignals(b)


class ParamPanel(QFrame):
    sig_threshold_changed = Signal(float, float)  # (ng_void_thresh, undersize_thresh)
    sig_config_changed = Signal()
    sig_alpha_synced = Signal(float)              # 用于在载入配方或恢复默认时同步顶栏透明度
    sig_hardware_updated = Signal(str, str)       # (status_text, color)

    def __init__(self, config: InspectionConfig, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self.setObjectName("ParamPanel")

        panel_layout = QVBoxLayout(self)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(10)

        # ==========================================================
        # 1. 独立卡片：检测项目设置 (Card 2)
        # ==========================================================
        self.card_engine = QFrame()
        self.card_engine.setObjectName("EngineCard")
        engine_layout = QVBoxLayout(self.card_engine)
        engine_layout.setContentsMargins(12, 10, 12, 10)
        engine_layout.setSpacing(6)

        lbl_engine_head = QLabel("检测项目设置")
        lbl_engine_head.setStyleSheet("font-weight: 700; font-size: 13px; color: #f1f5f9; padding: 2px 0 2px 0;")
        engine_layout.addWidget(lbl_engine_head)

        lbl_mode_title = QLabel("质检维度范围:")
        lbl_mode_title.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        engine_layout.addWidget(lbl_mode_title)

        self.cb_mode = QComboBox()
        self.cb_mode.setMinimumHeight(32)
        self.cb_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        if self.cb_mode.view():
            self.cb_mode.view().setCursor(Qt.CursorShape.PointingHandCursor)
            if self.cb_mode.view().viewport():
                self.cb_mode.view().viewport().setCursor(Qt.CursorShape.PointingHandCursor)

        self.cb_mode.setStyleSheet("""
            QComboBox {
                background-color: #141d2d;
                color: #cbd5e1;
                border: 1px solid #243044;
                border-radius: 6px;
                padding: 6px 24px 6px 8px;
                font-size: 11px;
                font-weight: 500;
            }
            QComboBox:hover {
                background-color: #1e293b;
                border: 1px solid #38bdf8;
                color: #ffffff;
            }
            QComboBox QAbstractItemView {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 6px;
                selection-background-color: #334155;
                selection-color: #ffffff;
                color: #e2e8f0;
                padding: 4px;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                min-height: 28px;
                padding: 4px 8px;
                border-radius: 4px;
                color: #cbd5e1;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #374151;
                color: #ffffff;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #334155;
                color: #ffffff;
                font-weight: bold;
            }
        """)

        self.cb_mode.addItem("全项综合检测 (空洞 + 桥连 + 虚焊)", "comprehensive")
        self.cb_mode.addItem("仅空洞缺陷检测", "void")
        self.cb_mode.addItem("仅桥连短路检测", "bridge")
        self.cb_mode.addItem("仅虚焊少锡检测", "insufficient")
        
        # 同步配置当前选项
        curr_idx = self.cb_mode.findData(self.config.inspection_mode)
        if curr_idx >= 0:
            self.cb_mode.setCurrentIndex(curr_idx)
        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)
        engine_layout.addWidget(self.cb_mode)

        panel_layout.addWidget(self.card_engine)

        # ==========================================================
        # 2. 独立卡片：合格判定标准设置 (Card 3)
        # ==========================================================
        self.card_thresh = QFrame()
        self.card_thresh.setObjectName("ThreshCard")
        thresh_layout = QVBoxLayout(self.card_thresh)
        thresh_layout.setContentsMargins(12, 10, 12, 10)
        thresh_layout.setSpacing(8)

        lbl_thresh_head = QLabel("合格判定标准设置")
        lbl_thresh_head.setStyleSheet("font-weight: 700; font-size: 13px; color: #f1f5f9; padding: 2px 0 2px 0;")
        thresh_layout.addWidget(lbl_thresh_head)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        # 通用 Slider 样式生成器 (颜色与对应缺陷及数字 100% 对齐)
        def _get_slider_qss(color_hex: str) -> str:
            return f"""
                QSlider::groove:horizontal {{
                    height: 4px;
                    background: #1e293b;
                    border-radius: 2px;
                }}
                QSlider::sub-page:horizontal {{
                    background: {color_hex};
                    border-radius: 2px;
                }}
                QSlider::handle:horizontal {{
                    background: {color_hex};
                    border: 2px solid #ffffff;
                    width: 14px;
                    margin-top: -5px;
                    margin-bottom: -5px;
                    border-radius: 7px;
                }}
                QSlider::handle:horizontal:hover {{
                    background: #ffffff;
                    border: 2px solid {color_hex};
                }}
            """

        # A. 焊点识别过滤程度 (Confidence) - 统一使用焊球翡翠绿色，左右加减步进器
        lbl_conf_title = QLabel("焊点识别过滤程度:")
        lbl_conf_title.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        lbl_conf_title.setToolTip(
            "【焊点识别过滤程度 (Confidence)】\n"
            "初筛候选焊球的把关门槛标准 (10% ~ 90%)。\n"
            "• 数值越小: 门槛越低，防止暗淡焊点漏检；\n"
            "• 数值越大: 过滤越严格，强力抑制基板反光与噪点；\n"
            "• 推荐基准值: 20%。"
        )
        grid.addWidget(lbl_conf_title, 0, 0)
        self.slider_conf = QSlider(Qt.Orientation.Horizontal)
        self.slider_conf.setRange(10, 90)
        self.slider_conf.setValue(int(self.config.conf_threshold * 100))
        self.slider_conf.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_conf.setStyleSheet(_get_slider_qss(DefectColors.NORMAL_HEX))

        self.spin_conf = HorizontalNumericStepper(
            min_val=10.0, max_val=90.0, step=1.0, decimals=1, color_hex=DefectColors.NORMAL_HEX
        )
        self.spin_conf.setValue(self.config.conf_threshold * 100.0)

        self.slider_conf.valueChanged.connect(self._on_conf_slider_changed)
        self.spin_conf.valueChanged.connect(self._on_conf_spin_changed)
        grid.addWidget(self.slider_conf, 0, 1)
        grid.addWidget(self.spin_conf, 0, 2)

        # B. 空洞占比超标阈值 (Void Ratio) - 亮品红，左右加减步进器
        lbl_void_title = QLabel("空洞占比超标阈值:")
        lbl_void_title.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        lbl_void_title.setToolTip(
            "【空洞占比超标阈值 (Void Ratio)】\n"
            "单个焊球内部空洞面积占焊球总面积的允许上限，超过此值判为 NG。\n"
            "• IPC-A-610 国际组装工业标准推荐线为 25%。"
        )
        grid.addWidget(lbl_void_title, 1, 0)
        self.slider_void = QSlider(Qt.Orientation.Horizontal)
        self.slider_void.setRange(1, 50)
        self.slider_void.setValue(int(self.config.ng_void_threshold * 100))
        self.slider_void.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_void.setStyleSheet(_get_slider_qss(DefectColors.VOID_NORMAL_HEX))

        self.spin_void = HorizontalNumericStepper(
            min_val=1.0, max_val=50.0, step=0.5, decimals=1, color_hex=DefectColors.VOID_NORMAL_HEX
        )
        self.spin_void.setValue(self.config.ng_void_threshold * 100.0)

        self.slider_void.valueChanged.connect(self._on_void_slider_changed)
        self.spin_void.valueChanged.connect(self._on_void_spin_changed)
        grid.addWidget(self.slider_void, 1, 1)
        grid.addWidget(self.spin_void, 1, 2)

        # C. 虚焊少锡缺少比例 (Insufficient Solder) - 高对比电光紫，左右加减步进器
        lbl_insuff_title = QLabel("虚焊少锡缺少比例:")
        lbl_insuff_title.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        lbl_insuff_title.setToolTip(
            "【虚焊少锡缺少比例 (面积偏小容忍上限)】\n"
            "焊球实测面积相对于整板标准焊球缩小的容忍上限，缩减比例超过此值提示虚焊风险。\n"
            "• 例如设为 20% 时，若某个焊球比正常平均面积小 20% 以上，即判定为少锡/虚焊 NG。\n"
            "• 工业推荐值: 20%。"
        )
        grid.addWidget(lbl_insuff_title, 2, 0)
        self.slider_insuff = QSlider(Qt.Orientation.Horizontal)
        self.slider_insuff.setRange(1, 50)
        self.slider_insuff.setValue(int(self.config.undersize_threshold * 100))
        self.slider_insuff.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_insuff.setStyleSheet(_get_slider_qss(DefectColors.INSUFF_NG_HEX))

        self.spin_insuff = HorizontalNumericStepper(
            min_val=1.0, max_val=50.0, step=0.5, decimals=1, color_hex=DefectColors.INSUFF_NG_HEX
        )
        self.spin_insuff.setValue(self.config.undersize_threshold * 100.0)

        self.slider_insuff.valueChanged.connect(self._on_insuff_slider_changed)
        self.spin_insuff.valueChanged.connect(self._on_insuff_spin_changed)
        grid.addWidget(self.slider_insuff, 2, 1)
        grid.addWidget(self.spin_insuff, 2, 2)

        thresh_layout.addLayout(grid)

        # 提示标签
        lbl_conf_hint = QLabel("提示: 支持拖动滑块或直接在右侧输入框敲入具体数值")
        lbl_conf_hint.setStyleSheet("color: #64748b; font-size: 10px; margin-top: 2px;")
        thresh_layout.addWidget(lbl_conf_hint)

        # ==========================================================
        # 3. 参数配方与默认值管理工具栏 (企业级无 Emoji 设计)
        # ==========================================================
        btn_bar_frame = QFrame()
        btn_bar_frame.setStyleSheet("""
            QFrame {
                background-color: #111827;
                border: 1px solid #1f2937;
                border-radius: 6px;
                padding: 4px;
            }
            QPushButton {
                background-color: #1f2937;
                color: #e2e8f0;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #374151;
                color: #ffffff;
                border-color: #4b5563;
            }
            QPushButton:pressed {
                background-color: #111827;
            }
        """)
        btn_bar_layout = QGridLayout(btn_bar_frame)
        btn_bar_layout.setContentsMargins(4, 4, 4, 4)
        btn_bar_layout.setHorizontalSpacing(6)
        btn_bar_layout.setVerticalSpacing(6)

        self.btn_save_default = QPushButton("保存为默认")
        self.btn_save_default.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_default.setToolTip("将当前设置的所有门限参数固化为系统默认值")
        self.btn_save_default.clicked.connect(self._on_save_default)

        self.btn_reset_default = QPushButton("恢复默认")
        self.btn_reset_default.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_default.setToolTip("快速重置为系统出厂推荐基准参数")
        self.btn_reset_default.clicked.connect(self._on_reset_default)

        self.btn_export_recipe = QPushButton("导出参数")
        self.btn_export_recipe.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_recipe.setToolTip("将当前质检参数方案导出为 JSON 配方文件")
        self.btn_export_recipe.clicked.connect(self._on_export_recipe)

        self.btn_import_recipe = QPushButton("导入参数")
        self.btn_import_recipe.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import_recipe.setToolTip("从外部 JSON 文件快速导入特定产线参数配方")
        self.btn_import_recipe.clicked.connect(self._on_import_recipe)

        btn_bar_layout.addWidget(self.btn_save_default, 0, 0)
        btn_bar_layout.addWidget(self.btn_reset_default, 0, 1)
        btn_bar_layout.addWidget(self.btn_export_recipe, 1, 0)
        btn_bar_layout.addWidget(self.btn_import_recipe, 1, 1)

        thresh_layout.addWidget(btn_bar_frame)

        thresh_layout.addStretch(1)
        panel_layout.addWidget(self.card_thresh, stretch=1)

        # 刷新硬件感知状态
        self._refresh_hardware_status()

    def _refresh_hardware_status(self):
        self.config.hardware_device = "auto"
        _, status_text, color = hardware_sniffer.resolve_device("auto")
        self.sig_hardware_updated.emit(status_text, color)

    def _on_mode_changed(self):
        self.config.inspection_mode = self.cb_mode.currentData()
        self.sig_config_changed.emit()

    def _on_void_slider_changed(self, val: int):
        self.spin_void.blockSignals(True)
        self.spin_void.setValue(float(val))
        self.spin_void.blockSignals(False)

        self.config.ng_void_threshold = val / 100.0
        self.sig_threshold_changed.emit(self.config.ng_void_threshold, self.config.undersize_threshold)

    def _on_void_spin_changed(self, val: float):
        slider_val = int(round(val))
        self.slider_void.blockSignals(True)
        self.slider_void.setValue(slider_val)
        self.slider_void.blockSignals(False)

        self.config.ng_void_threshold = val / 100.0
        self.sig_threshold_changed.emit(self.config.ng_void_threshold, self.config.undersize_threshold)

    def _on_insuff_slider_changed(self, val: int):
        self.spin_insuff.blockSignals(True)
        self.spin_insuff.setValue(float(val))
        self.spin_insuff.blockSignals(False)

        self.config.undersize_threshold = val / 100.0
        self.sig_threshold_changed.emit(self.config.ng_void_threshold, self.config.undersize_threshold)

    def _on_insuff_spin_changed(self, val: float):
        slider_val = int(round(val))
        self.slider_insuff.blockSignals(True)
        self.slider_insuff.setValue(slider_val)
        self.slider_insuff.blockSignals(False)

        self.config.undersize_threshold = val / 100.0
        self.sig_threshold_changed.emit(self.config.ng_void_threshold, self.config.undersize_threshold)

    def _on_conf_slider_changed(self, val: int):
        self.spin_conf.blockSignals(True)
        self.spin_conf.setValue(float(val))
        self.spin_conf.blockSignals(False)

        self.config.conf_threshold = val / 100.0
        self.sig_config_changed.emit()

    def _on_conf_spin_changed(self, val: float):
        slider_val = int(round(val))
        self.slider_conf.blockSignals(True)
        self.slider_conf.setValue(slider_val)
        self.slider_conf.blockSignals(False)

        self.config.conf_threshold = val / 100.0
        self.sig_config_changed.emit()

    def sync_controls_from_config(self):
        """根据当前内存中的 config 重新刷新全部输入框与滑块"""
        self.slider_conf.blockSignals(True)
        self.spin_conf.blockSignals(True)
        self.slider_conf.setValue(int(self.config.conf_threshold * 100))
        self.spin_conf.setValue(self.config.conf_threshold * 100.0)
        self.slider_conf.blockSignals(False)
        self.spin_conf.blockSignals(False)

        self.slider_void.blockSignals(True)
        self.spin_void.blockSignals(True)
        self.slider_void.setValue(int(self.config.ng_void_threshold * 100))
        self.spin_void.setValue(self.config.ng_void_threshold * 100.0)
        self.slider_void.blockSignals(False)
        self.spin_void.blockSignals(False)

        self.slider_insuff.blockSignals(True)
        self.spin_insuff.blockSignals(True)
        self.slider_insuff.setValue(int(self.config.undersize_threshold * 100))
        self.spin_insuff.setValue(self.config.undersize_threshold * 100.0)
        self.slider_insuff.blockSignals(False)
        self.spin_insuff.blockSignals(False)

        self.cb_mode.blockSignals(True)
        idx = self.cb_mode.findData(self.config.inspection_mode)
        if idx >= 0:
            self.cb_mode.setCurrentIndex(idx)
        self.cb_mode.blockSignals(False)

        self.sig_threshold_changed.emit(self.config.ng_void_threshold, self.config.undersize_threshold)
        self.sig_alpha_synced.emit(self.config.overlay_alpha)
        self.sig_config_changed.emit()

    def _on_save_default(self):
        ok = app_config_mgr.save_as_default()
        if ok:
            QMessageBox.information(self, "配置保存", "当前参数组合已成功保存为最佳默认配置。")
        else:
            QMessageBox.warning(self, "配置保存", "保存默认配置失败，请检查文件写入权限。")

    def _on_reset_default(self):
        reply = QMessageBox.question(
            self,
            "恢复默认",
            "是否确认将判定标准与检测模式恢复为出厂默认设置？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            app_config_mgr.reset_to_defaults()
            self.sync_controls_from_config()

    def _on_export_recipe(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出质检参数配方",
            os.path.join(os.getcwd(), "BGA_质检参数方案.json"),
            "JSON 配方文件 (*.json)"
        )
        if path:
            ok = app_config_mgr.export_recipe_json(path)
            if ok:
                QMessageBox.information(self, "导出成功", f"质检参数方案已成功导出至:\n{path}")
            else:
                QMessageBox.critical(self, "导出失败", "导出参数配方遇到异常，请重试。")

    def _on_import_recipe(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入质检参数配方",
            os.getcwd(),
            "JSON 配方文件 (*.json)"
        )
        if path:
            ok = app_config_mgr.import_recipe_json(path)
            if ok:
                self.sync_controls_from_config()
                QMessageBox.information(self, "导入成功", f"已成功从外部文件载入参数配方并立即生效！")
            else:
                QMessageBox.critical(self, "导入失败", "解析或载入参数配方文件失败，请检查文件格式是否有效。")
