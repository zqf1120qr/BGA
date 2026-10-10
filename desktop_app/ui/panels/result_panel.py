# -*- coding: utf-8 -*-
"""
🌟 质检判定看板与汇总统计卡片 (Result Summary Panel)
----------------------------------------------------
纯工程风格，无 Emoji，高对比度呈现 PASS / NG 状态与多维统计指标。
"""
from __future__ import annotations

from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class ResultSummaryPanel(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ResultSummaryPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. 顶部标题
        lbl_head = QLabel("检测结果判定看板")
        lbl_head.setStyleSheet("font-weight: 700; font-size: 13px; color: #f1f5f9; padding: 2px 0 4px 0;")
        layout.addWidget(lbl_head)

        # 2. 核心大判定胶囊卡片
        self.card_status = QFrame()
        self.card_status.setObjectName("StatusCard")
        status_card_layout = QVBoxLayout(self.card_status)
        status_card_layout.setContentsMargins(16, 14, 16, 14)
        status_card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_big_status = QLabel("READY")
        self.lbl_big_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_big_status.setStyleSheet("font-size: 26px; font-weight: 900; letter-spacing: 2px;")

        self.lbl_sub_status = QLabel("等待执行检测...")
        self.lbl_sub_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_sub_status.setStyleSheet("font-size: 12px; color: #94a3b8;")

        status_card_layout.addWidget(self.lbl_big_status)
        status_card_layout.addWidget(self.lbl_sub_status)
        layout.addWidget(self.card_status)

        self._set_card_style("READY")

        # 3. 统计网格指标
        grid_frame = QFrame()
        grid_frame.setObjectName("ResultGridFrame")
        grid = QGridLayout(grid_frame)
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        self.val_total = QLabel("0")
        self.val_void_ng = QLabel("0")
        self.val_bridge = QLabel("0")
        self.val_insuff = QLabel("0")
        self.val_time = QLabel("0.0 ms")

        for lbl in (self.val_total, self.val_void_ng, self.val_bridge, self.val_insuff, self.val_time):
            lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #f8fafc;")

        # 添加网格项
        def _mk_key(t):
            l = QLabel(t)
            l.setStyleSheet("color: #94a3b8; font-size: 11px;")
            return l

        grid.addWidget(_mk_key("检测焊球总数:"), 0, 0)
        grid.addWidget(self.val_total, 0, 1)

        grid.addWidget(_mk_key("气泡超标焊点:"), 1, 0)
        grid.addWidget(self.val_void_ng, 1, 1)

        grid.addWidget(_mk_key("桥连短路对数:"), 2, 0)
        grid.addWidget(self.val_bridge, 2, 1)

        grid.addWidget(_mk_key("虚焊少锡焊点:"), 3, 0)
        grid.addWidget(self.val_insuff, 3, 1)

        grid.addWidget(_mk_key("本次检测用时:"), 4, 0)
        grid.addWidget(self.val_time, 4, 1)

        layout.addWidget(grid_frame)

    def _set_card_style(self, status: str):
        if status == "PASS":
            self.card_status.setStyleSheet("""
                QFrame#StatusCard {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #064e3b, stop:1 #065f46);
                    border-radius: 8px;
                    border: 1px solid #10b981;
                }
            """)
            self.lbl_big_status.setText("● PASS")
            self.lbl_big_status.setStyleSheet("color: #ffffff; font-size: 26px; font-weight: 900;")
            self.lbl_sub_status.setText("整板检测合格 (符合质量标准)")
            self.lbl_sub_status.setStyleSheet("color: #a7f3d0; font-size: 11px;")
        elif status == "NG":
            self.card_status.setStyleSheet("""
                QFrame#StatusCard {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #881337, stop:1 #9f1239);
                    border-radius: 8px;
                    border: 1px solid #f43f5e;
                }
            """)
            self.lbl_big_status.setText("● NG 不良")
            self.lbl_big_status.setStyleSheet("color: #ffffff; font-size: 26px; font-weight: 900;")
            self.lbl_sub_status.setText("检出不良焊点，需人工复核")
            self.lbl_sub_status.setStyleSheet("color: #fecdd3; font-size: 11px;")
        else:
            self.card_status.setStyleSheet("""
                QFrame#StatusCard {
                    background-color: #161e31;
                    border-radius: 8px;
                    border: 1px solid #273449;
                }
            """)
            self.lbl_big_status.setText("READY")
            self.lbl_big_status.setStyleSheet("color: #64748b; font-size: 24px; font-weight: 900;")
            self.lbl_sub_status.setText("等待加载图片...")
            self.lbl_sub_status.setStyleSheet("color: #64748b; font-size: 11px;")

    def update_summary(self, stats: Dict[str, Any]):
        status = stats.get("board_status", "READY")
        self._set_card_style(status)

        self.val_total.setText(str(stats.get("total_solders", 0)))

        v_ng = stats.get("void_ng_count", 0)
        self.val_void_ng.setText(str(v_ng))
        self.val_void_ng.setStyleSheet("color: #f43f5e; font-weight: bold;" if v_ng > 0 else "color: #10b981;")

        b_ng = stats.get("bridge_count", 0)
        self.val_bridge.setText(str(b_ng))
        self.val_bridge.setStyleSheet("color: #ef4444; font-weight: bold;" if b_ng > 0 else "color: #10b981;")

        i_ng = stats.get("insufficient_count", 0)
        self.val_insuff.setText(str(i_ng))
        self.val_insuff.setStyleSheet("color: #fb923c; font-weight: bold;" if i_ng > 0 else "color: #10b981;")

        self.val_time.setText(f"{stats.get('elapsed_ms', 0.0):.1f} ms")

        # 详细缺陷原因提示
        reasons = stats.get("ng_reasons", [])
        if reasons and status == "NG":
            self.lbl_sub_status.setText(" | ".join(reasons[:2]))
