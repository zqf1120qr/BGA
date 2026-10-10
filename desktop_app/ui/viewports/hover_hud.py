# -*- coding: utf-8 -*-
"""
🌟 焊点悬停浮动数据微探针 (Hover HUD Tooltip)
--------------------------------------------
1. 严格吸附于当前焊点正上方 (正对球心，距离球顶 6px)；
2. 若靠近视口顶边缘空间不足，智能自适应翻转至焊点正下方；
3. 开启 WA_TransparentForMouseEvents，彻底杜绝事件拦截与鼠标卡顿抖动；
4. 毫秒级呈现焊点编号、气泡占比、偏离基准及缺陷状态。
"""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class HoverHudWidget(QFrame):
    """半透明浮动数据微探针卡片 (精准吸附于当前焊点上方)"""
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        # 设为无焦点、穿透鼠标事件的视口浮层，绝不拦截视口鼠标事件，消除卡顿抖动
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.setObjectName("HoverHudCard")
        self.setStyleSheet("""
            QFrame#HoverHudCard {
                background-color: #0b0f19;
                border: 1.5px solid #38bdf8;
                border-radius: 6px;
                padding: 4px;
            }
            QLabel {
                color: #f1f5f9;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                font-size: 11px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)

        # 顶部标题栏：焊点 ID + 判定 Badge
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.lbl_title = QLabel("#-- 焊球")
        self.lbl_title.setStyleSheet("font-weight: 700; font-size: 12px; color: #ffffff;")
        header_layout.addWidget(self.lbl_title)

        header_layout.addStretch()

        self.lbl_status_badge = QLabel("PASS")
        self.lbl_status_badge.setStyleSheet("""
            background-color: #10b981;
            color: #ffffff;
            font-weight: bold;
            font-size: 10px;
            padding: 1px 5px;
            border-radius: 3px;
        """)
        header_layout.addWidget(self.lbl_status_badge)
        layout.addLayout(header_layout)

        # 指标明细项
        self.lbl_void = QLabel("• 气泡占比: 0.0%")
        self.lbl_insuff = QLabel("• 少锡缩减率: 0.0%")
        self.lbl_bridge = QLabel("• 桥连短路: 正常")
        self.lbl_coord = QLabel("• 中心坐标: (0, 0)")
        self.lbl_coord.setStyleSheet("color: #64748b; font-size: 10px;")

        layout.addWidget(self.lbl_void)
        layout.addWidget(self.lbl_insuff)
        layout.addWidget(self.lbl_bridge)
        layout.addWidget(self.lbl_coord)

        self.adjustSize()
        self.hide()

    def update_data(
        self,
        index: int,
        status: str,
        cx: float,
        cy: float,
        void_rate: float,
        is_void_ng: bool,
        reduction_percent: float,
        is_insuff: bool,
        is_bridge: bool,
    ):
        self.lbl_title.setText(f"#{index} 号焊球")

        # 状态 Badge 颜色
        if status == "NG":
            self.lbl_status_badge.setText("NG 不良")
            self.lbl_status_badge.setStyleSheet("""
                background-color: #f43f5e;
                color: #ffffff;
                font-weight: bold;
                font-size: 10px;
                padding: 1px 5px;
                border-radius: 3px;
            """)
        else:
            self.lbl_status_badge.setText("PASS 合格")
            self.lbl_status_badge.setStyleSheet("""
                background-color: #10b981;
                color: #ffffff;
                font-weight: bold;
                font-size: 10px;
                padding: 1px 5px;
                border-radius: 3px;
            """)

        # 气泡指标
        void_color = "#f43f5e" if is_void_ng else "#38bdf8"
        void_text = f"• 气泡占比: <b style='color:{void_color}'>{void_rate * 100:.1f}%</b>"
        if is_void_ng:
            void_text += " <span style='color:#f43f5e;font-size:10px;'>(超标)</span>"
        self.lbl_void.setText(void_text)

        # 虚焊指标
        insuff_color = "#f59e0b" if is_insuff else "#94a3b8"
        insuff_text = f"• 少锡缩减率: <b style='color:{insuff_color}'>-{reduction_percent:.1f}%</b>"
        if is_insuff:
            insuff_text += " <span style='color:#f59e0b;font-size:10px;'>(偏小)</span>"
        self.lbl_insuff.setText(insuff_text)

        # 桥连指标
        if is_bridge:
            self.lbl_bridge.setText("• 桥连短路: <b style='color:#f43f5e'>[短路不良]</b>")
        else:
            self.lbl_bridge.setText("• 桥连短路: <span style='color:#10b981'>正常</span>")

        self.lbl_coord.setText(f"• 中心坐标: ({cx:.1f}, {cy:.1f})")
        self.adjustSize()

    def show_above_ball(self, center_view: QPointF, radius_view: float, viewport_size: QSize):
        """将 HUD 卡片精确对准焊球球心，垂直悬浮在当前焊点正上方"""
        self.adjustSize()
        w = self.width()
        h = self.height()
        vw = viewport_size.width()
        vh = viewport_size.height()

        # 1. 水平方向严格居中对准焊点中心
        target_x = center_view.x() - (w / 2.0)
        # 限制在视口安全边界内
        target_x = max(8.0, min(target_x, float(vw - w - 8.0)))

        # 2. 垂直方向默认放置在当前焊点正上方 (距离焊球轮廓顶部 6px)
        target_y = center_view.y() - radius_view - h - 6.0
        # 若上方空间不足被视口上沿截断，则智能翻转至焊点正下方 (距离焊球底端 6px)
        if target_y < 8.0:
            target_y = center_view.y() + radius_view + 6.0
            # 若下方也超出视口底部，则安全吸附在底部边界内
            if target_y + h > vh - 8.0:
                target_y = max(8.0, float(vh - h - 8.0))

        self.move(int(target_x), int(target_y))
        self.show()
        self.raise_()
