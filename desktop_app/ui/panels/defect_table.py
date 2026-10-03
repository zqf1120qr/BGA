# -*- coding: utf-8 -*-
"""
🌟 焊点与缺陷明细联动表格面板 (Defect & Solder Table Panel)
-----------------------------------------------------------
无 Emoji，纯工业标准工程风格，支持双向平滑居中聚焦与桥连缺陷清晰列示。
"""
from __future__ import annotations

from typing import List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_app.core.inspection_manager import SolderBallRecord


class DefectTablePanel(QFrame):
    sig_ball_focus_requested = Signal(int)  # 请求视口聚焦焊球 (ball_index)
    sig_ball_selected = Signal(int)         # 表格选中焊球 (ball_index)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("DefectTablePanel")

        self.records: List[SolderBallRecord] = []
        self.filter_mode = "all"  # "all" | "defect_only"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 1. 顶部操作栏与过滤按钮
        lbl_title = QLabel("检测明细与缺陷清单")
        lbl_title.setStyleSheet("font-weight: 700; font-size: 13px; color: #f1f5f9; padding: 2px 0 2px 0;")
        layout.addWidget(lbl_title)

        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(6)
        self.btn_filter_all = QPushButton("全部焊球 (0)")
        self.btn_filter_all.setCheckable(True)
        self.btn_filter_all.setChecked(True)
        self.btn_filter_all.setMinimumHeight(28)
        self.btn_filter_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter_all.clicked.connect(lambda: self.set_filter("all"))

        self.btn_filter_defect = QPushButton("仅看缺陷 (0)")
        self.btn_filter_defect.setCheckable(True)
        self.btn_filter_defect.setMinimumHeight(28)
        self.btn_filter_defect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter_defect.clicked.connect(lambda: self.set_filter("defect_only"))

        filter_bar.addWidget(self.btn_filter_all)
        filter_bar.addWidget(self.btn_filter_defect)
        layout.addLayout(filter_bar)

        # 2. 表格组件
        self.table = QTableWidget()
        headers = [
            ("焊点ID", "焊点编号 (单击视口定位，双击平滑居中放大聚焦)"),
            ("气泡比", "焊球内部气泡空洞率 (空洞面积 / 焊球面积)"),
            ("偏离基准", "相对标准基准球的面积缩减率 (少锡虚焊指标)"),
            ("桥连短路", "相邻焊球锡膏粘连短路状态与目标球号"),
            ("置信度", "YOLO 深度学习模型识别置信度"),
            ("结论", "该焊点综合质量判废结论 (PASS / NG)"),
        ]
        self.table.setColumnCount(len(headers))
        for col, (name, tip) in enumerate(headers):
            h_item = QTableWidgetItem(name)
            h_item.setToolTip(tip)
            self.table.setHorizontalHeaderItem(col, h_item)

        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        self.table.setColumnWidth(0, 48)   # 焊点ID (#xxx)
        self.table.setColumnWidth(1, 56)   # 气泡比 (xx.x%)
        self.table.setColumnWidth(2, 60)   # 偏离基准 (-xx.x%)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # 桥连短路 (自适应伸展占满剩余宽度)
        self.table.setColumnWidth(4, 52)   # 置信度 (xx.x%)
        self.table.setColumnWidth(5, 46)   # 结论 (PASS/NG)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.table.cellDoubleClicked.connect(self._handle_double_clicked)
        self.table.cellClicked.connect(self._handle_clicked)
        layout.addWidget(self.table)

    def load_data(self, records: List[SolderBallRecord]):
        self.records = list(records)
        self.refresh_table()

    def set_filter(self, mode: str):
        self.filter_mode = mode
        self.btn_filter_all.setChecked(mode == "all")
        self.btn_filter_defect.setChecked(mode == "defect_only")
        self.refresh_table()

    def refresh_table(self):
        total_count = len(self.records)
        ng_count = sum(1 for r in self.records if r.is_ng)

        self.btn_filter_all.setText(f"全部焊球 ({total_count})")
        self.btn_filter_defect.setText(f"仅看缺陷 ({ng_count})")

        filtered = [
            r for r in self.records
            if (self.filter_mode == "all" or r.is_ng)
        ]

        self.table.setRowCount(len(filtered))
        bold_font = QFont()
        bold_font.setBold(True)

        for row, rec in enumerate(filtered):
            # 1. 焊点ID
            item_id = QTableWidgetItem(f"#{rec.index}")
            item_id.setData(Qt.ItemDataRole.UserRole, rec.index)
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_id.setToolTip(
                f"【焊球 #{rec.index} 几何明细】\n"
                f"• 中心坐标: ({int(rec.cx)}, {int(rec.cy)})\n"
                f"• 像素半径: {rec.radius:.1f} px\n"
                f"• 交互操作: 单击联动视口选中，双击平滑居中聚焦"
            )

            # 2. 气泡比
            item_void = QTableWidgetItem(f"{rec.void_rate * 100:.1f}%")
            item_void.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_void.setToolTip(
                f"【焊点内部气泡空洞率】\n"
                f"• 当前实测值: {rec.void_rate * 100:.2f}%\n"
                f"• 判定状态: {'❌ 空洞率超标 (NG)' if rec.is_void_ng else '✅ 正常合格 (PASS)'}"
            )

            # 3. 偏离基准 (少锡/虚焊)
            insuff_str = f"-{rec.reduction_percent:.1f}%" if rec.reduction_percent > 0 else "0.0%"
            item_insuff = QTableWidgetItem(insuff_str)
            item_insuff.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_insuff.setToolTip(
                f"【焊点少锡偏离基准】\n"
                f"• 面积缩减比: {rec.reduction_percent:.2f}%\n"
                f"• 判定状态: {'❌ 焊料萎缩超标 (少锡NG)' if rec.is_insufficient else '✅ 焊料饱满正常 (PASS)'}"
            )

            # 4. 桥连短路 (彻底解决文本截断无法查看问题，提供全量悬浮气泡预览)
            if rec.is_bridge:
                partners_str = ",".join(str(p) for p in rec.bridge_partners)
                item_bridge = QTableWidgetItem(f"短路NG (#{partners_str})" if partners_str else "短路NG")
                tip_partners = ", ".join(f"#{p}" for p in rec.bridge_partners) if rec.bridge_partners else "相邻焊点"
                item_bridge.setToolTip(
                    f"【桥连短路异常 (NG)】\n"
                    f"• 粘连目标球号: {tip_partners}\n"
                    f"• 缺陷特征: 焊点间距过小，焊锡熔合形成导电短路\n"
                    f"• 工艺建议: 检查锡膏印刷钢网厚度及贴片压力"
                )
            else:
                item_bridge = QTableWidgetItem("正常")
                item_bridge.setToolTip("【桥连短路状态】: 正常 (与相邻焊点间隙良好，无粘连)")
            item_bridge.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # 5. 置信度
            item_conf = QTableWidgetItem(f"{rec.confidence * 100:.1f}%")
            item_conf.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_conf.setToolTip(f"【YOLO 深度学习目标检测】\n• 焊点识别置信度: {rec.confidence * 100:.2f}%")

            # 6. 综合结论
            item_status = QTableWidgetItem(rec.status)
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            reasons = "、".join(rec.ng_reasons) if rec.ng_reasons else "各项质检指标完全合格"
            item_status.setToolTip(
                f"【最终判废结论】: {rec.status}\n"
                f"• 判定原因: {reasons}"
            )

            # 工业高对比配色
            if rec.is_ng:
                item_status.setForeground(QColor(244, 63, 94))  # 红色
                item_status.setFont(bold_font)

                if rec.is_void_ng:
                    item_void.setForeground(QColor(244, 63, 94))
                    item_void.setFont(bold_font)
                if rec.is_insufficient:
                    item_insuff.setForeground(QColor(251, 146, 60))
                    item_insuff.setFont(bold_font)
                if rec.is_bridge:
                    item_bridge.setForeground(QColor(239, 68, 68))  # 警报鲜红
                    item_bridge.setFont(bold_font)
            else:
                item_status.setForeground(QColor(16, 185, 129))  # 绿色
                item_void.setForeground(QColor(56, 189, 248))
                item_insuff.setForeground(QColor(148, 163, 184))
                item_bridge.setForeground(QColor(100, 116, 139))

            self.table.setItem(row, 0, item_id)
            self.table.setItem(row, 1, item_void)
            self.table.setItem(row, 2, item_insuff)
            self.table.setItem(row, 3, item_bridge)
            self.table.setItem(row, 4, item_conf)
            self.table.setItem(row, 5, item_status)

    def select_ball(self, ball_index: int):
        """外部视口点击焊球时，表格自动滚动到对应行并高亮"""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == ball_index:
                self.table.selectRow(row)
                self.table.scrollToItem(item, QTableWidget.ScrollHint.PositionAtCenter)
                break

    def _handle_clicked(self, row: int, col: int):
        item = self.table.item(row, 0)
        if item:
            ball_index = item.data(Qt.ItemDataRole.UserRole)
            self.sig_ball_selected.emit(ball_index)

    def _handle_double_clicked(self, row: int, col: int):
        item = self.table.item(row, 0)
        if item:
            ball_index = item.data(Qt.ItemDataRole.UserRole)
            self.sig_ball_focus_requested.emit(ball_index)
