# -*- coding: utf-8 -*-
"""
焊点与缺陷明细联动表格面板 (Defect & Solder Table Panel)
-----------------------------------------------------------
纯工业标准工程风格，支持双向平滑居中聚焦与桥连缺陷清晰列示。
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
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_app.core.inspection_manager import SolderBallRecord
from desktop_app.ui.styles.color_palette import DefectColors


class DefectTablePanel(QFrame):
    sig_ball_focus_requested = Signal(int)  # 请求视口聚焦焊球 (ball_index)
    sig_ball_selected = Signal(int)         # 表格选中焊球 (ball_index)
    sig_ball_review_toggled = Signal(int)   # 切换焊球复核状态 (ball_index)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("DefectTablePanel")

        self.records: List[SolderBallRecord] = []
        self.filter_mode = "all"  # "all" | "defect_only" | "reviewed_only"
        self.current_selected_ball_index: int = -1

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

        self.btn_filter_defect = QPushButton("当前不良 (0)")
        self.btn_filter_defect.setCheckable(True)
        self.btn_filter_defect.setMinimumHeight(28)
        self.btn_filter_defect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter_defect.clicked.connect(lambda: self.set_filter("defect_only"))

        self.btn_filter_reviewed = QPushButton("已排除误检 (0)")
        self.btn_filter_reviewed.setCheckable(True)
        self.btn_filter_reviewed.setMinimumHeight(28)
        self.btn_filter_reviewed.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter_reviewed.clicked.connect(lambda: self.set_filter("reviewed_only"))

        filter_bar.addWidget(self.btn_filter_all)
        filter_bar.addWidget(self.btn_filter_defect)
        filter_bar.addWidget(self.btn_filter_reviewed)
        layout.addLayout(filter_bar)

        # 2. 表格组件 (支持高对比深金黄底色与亮金黄色文字选中联动)
        self.table = QTableWidget()
        headers = [
            ("焊点ID", "焊点编号 (单击视口定位，双击平滑居中放大聚焦)"),
            ("空洞占比", "焊球内部空洞面积占焊球总面积的比例"),
            ("少锡幅度", "相对标准焊球的面积缩减率 (虚焊少锡指标)"),
            ("桥连短路", "相邻焊球锡膏粘连短路状态与关联焊点"),
            ("单点结论", "该焊点质量判定结果 (PASS合格 / NG不良 / PASS复核)"),
            ("人工复核", "点击快速排除算法误检或撤销恢复"),
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
        self.table.setColumnWidth(0, 42)   # 焊点ID (#xxx)
        self.table.setColumnWidth(1, 52)   # 空洞占比 (xx.x%)
        self.table.setColumnWidth(2, 52)   # 少锡幅度 (-xx.x%)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # 桥连短路 (自适应伸展占满剩余宽度)
        self.table.setColumnWidth(4, 62)   # 单点结论 (PASS/NG/PASS复核)
        self.table.setColumnWidth(5, 68)   # 人工复核操作列
        self.table.verticalHeader().setVisible(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._handle_context_menu)

        # 强化选中行高亮与视口纯金黄十字准星保持严格一致
        self.table.setStyleSheet(f"""
            QTableWidget {{
                selection-background-color: {DefectColors.FOCUS_TABLE_BG_HEX};
                selection-color: {DefectColors.FOCUS_TARGET_HEX};
            }}
        """)

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
        self.btn_filter_reviewed.setChecked(mode == "reviewed_only")
        self.refresh_table()


    def refresh_table(self):
        total_count = len(self.records)
        active_ng_count = sum(1 for r in self.records if r.final_is_ng)
        reviewed_count = sum(
            1 for r in self.records
            if (r.is_manually_reviewed and r.manual_status == "PASS") or r.is_bridge_cleared
        )

        self.btn_filter_all.setText(f"全部焊球 ({total_count})")
        self.btn_filter_defect.setText(f"当前不良 ({active_ng_count})")
        self.btn_filter_reviewed.setText(f"已排除误检 ({reviewed_count})")

        if self.filter_mode == "defect_only":
            filtered = [r for r in self.records if r.final_is_ng]
        elif self.filter_mode == "reviewed_only":
            filtered = [
                r for r in self.records
                if (r.is_manually_reviewed and r.manual_status == "PASS") or r.is_bridge_cleared
            ]
        else:
            filtered = list(self.records)

        # 核心防残留：彻底清空现有单元格内容与已挂载的旧 cellWidget，杜绝切过滤器错位
        self.table.clearContents()
        self.table.setRowCount(0)
        self.table.setRowCount(len(filtered))
        bold_font = QFont()
        bold_font.setBold(True)

        for row, rec in enumerate(filtered):
            is_reviewed_pass = (rec.is_manually_reviewed and rec.manual_status == "PASS")
            is_any_reviewed = is_reviewed_pass or (rec.is_bridge_cleared and not rec.final_is_ng)

            # 1. 焊点ID
            item_id = QTableWidgetItem(f"#{rec.index}")
            item_id.setData(Qt.ItemDataRole.UserRole, rec.index)
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_id.setToolTip(
                f"[ 焊球 #{rec.index} 几何明细 ]\n"
                f"• 中心坐标: ({int(rec.cx)}, {int(rec.cy)})\n"
                f"• 像素半径: {rec.radius:.1f} px\n"
                f"• 交互操作: 单击联动视口选中，双击平滑居中聚焦，右键弹出复核菜单"
            )

            # 2. 空洞占比
            item_void = QTableWidgetItem(f"{rec.void_rate * 100:.1f}%")
            item_void.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_void.setToolTip(
                f"[ 焊点内部空洞占比 ]\n"
                f"• 当前实测值: {rec.void_rate * 100:.2f}%\n"
                f"• 判定状态: {'空洞占比超标 (NG)' if rec.is_void_ng else '正常合格 (PASS)'}"
            )

            # 3. 少锡幅度 (少锡/虚焊)
            insuff_str = f"-{rec.reduction_percent:.1f}%" if rec.reduction_percent > 0 else "0.0%"
            item_insuff = QTableWidgetItem(insuff_str)
            item_insuff.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_insuff.setToolTip(
                f"[ 焊点少锡程度 ]\n"
                f"• 面积缩减幅度: {rec.reduction_percent:.2f}%\n"
                f"• 判定状态: {'少锡虚焊超标 (少锡NG)' if rec.is_insufficient else '锡量饱满正常 (PASS)'}"
            )

            # 4. 桥连短路 (严格反映当前真实状态：生效桥连NG / 已人工排除误检 / 正常)
            if rec.has_active_bridge:
                partners_str = ",".join(str(p) for p in rec.bridge_partners)
                item_bridge = QTableWidgetItem(f"桥连NG (#{partners_str})" if partners_str else "桥连NG")
                item_bridge.setForeground(DefectColors.BRIDGE_NG_COLOR)
                item_bridge.setFont(bold_font)
                tip_partners = ", ".join(f"#{p}" for p in rec.bridge_partners) if rec.bridge_partners else "相邻焊点"
                item_bridge.setToolTip(
                    f"[ 桥连短路异常 (NG) ]\n"
                    f"• 粘连关联焊点: {tip_partners}\n"
                    f"• 缺陷特征: 焊点间距过小，焊锡熔合形成导电短路\n"
                    f"• 处置建议: 点击操作列一键排除误检或在画布右键处置"
                )
            elif rec.is_bridge_cleared:
                partners_str = ",".join(str(p) for p in rec.bridge_partners)
                item_bridge = QTableWidgetItem("桥连排除" if not partners_str else f"桥连排除(#{partners_str})")
                item_bridge.setForeground(DefectColors.REVIEW_PASS_COLOR)
                item_bridge.setFont(bold_font)
                tip_partners = ", ".join(f"#{p}" for p in rec.bridge_partners) if rec.bridge_partners else "相邻焊点"
                item_bridge.setToolTip(
                    f"[ 桥连短路已排除误检 ]\n"
                    f"• 关联焊点: {tip_partners}\n"
                    f"• 状态: 已经人工复核排除为假短路，判定为合格"
                )
            else:
                item_bridge = QTableWidgetItem("正常")
                item_bridge.setForeground(QColor(100, 116, 139))
                item_bridge.setToolTip("[ 桥连短路状态 ]: 正常 (与相邻焊点间隙良好，无粘连)")
            item_bridge.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # 5. 单点结论 (区分 原生PASS / NG / 人工复核合格PASS)
            if is_any_reviewed:
                item_status = QTableWidgetItem("PASS(复核)")
                item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_status.setForeground(DefectColors.REVIEW_PASS_COLOR)
                item_status.setFont(bold_font)
                if is_reviewed_pass:
                    reason_desc = rec.review_reason or "人工复核排除误检"
                else:
                    reason_desc = "桥连短路缺陷已被人工复核排除为误检"
                item_status.setToolTip(
                    f"[ 最终判定结果 ]: PASS (人工复核合格)\n"
                    f"• 原始判定: NG 不良 ({'、'.join(rec.ng_reasons) if rec.ng_reasons else '缺陷异常'})\n"
                    f"• 复核说明: {reason_desc}\n"
                    f"• 复核时间: {rec.review_timestamp or '刚刚'}"
                )
            elif rec.final_is_ng:
                item_status = QTableWidgetItem(rec.status)
                item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_status.setForeground(DefectColors.VOID_NG_COLOR)
                item_status.setFont(bold_font)
                reasons = "、".join(rec.ng_reasons) if rec.ng_reasons else "缺陷异常"
                item_status.setToolTip(f"[ 最终判定结果 ]: {rec.status} (不良待处置)\n• 判定原因: {reasons}")
            else:
                item_status = QTableWidgetItem("PASS")
                item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_status.setForeground(DefectColors.NORMAL_COLOR)
                item_status.setToolTip("[ 最终判定结果 ]: PASS\n• 判定原因: 各项指标完全合格")

            # 颜色细节处理 (未超标项保持低调高质感暗灰，超标项高亮告警)
            if rec.final_is_ng:
                if rec.is_void_ng:
                    item_void.setForeground(DefectColors.VOID_NG_COLOR)
                    item_void.setFont(bold_font)
                else:
                    item_void.setForeground(DefectColors.CONF_COLOR)
                if rec.is_insufficient:
                    item_insuff.setForeground(DefectColors.INSUFF_NG_COLOR)
                    item_insuff.setFont(bold_font)
                else:
                    item_insuff.setForeground(QColor(148, 163, 184))
            elif is_any_reviewed:
                if rec.is_void_ng:
                    item_void.setForeground(DefectColors.REVIEW_PASS_COLOR)
                    item_void.setFont(bold_font)
                else:
                    item_void.setForeground(DefectColors.CONF_COLOR)
                if rec.is_insufficient:
                    item_insuff.setForeground(DefectColors.REVIEW_PASS_COLOR)
                    item_insuff.setFont(bold_font)
                else:
                    item_insuff.setForeground(QColor(148, 163, 184))
            else:
                item_void.setForeground(DefectColors.CONF_COLOR)
                item_insuff.setForeground(QColor(148, 163, 184))

            self.table.setItem(row, 0, item_id)
            self.table.setItem(row, 1, item_void)
            self.table.setItem(row, 2, item_insuff)
            self.table.setItem(row, 3, item_bridge)
            self.table.setItem(row, 4, item_status)

            # 6. 人工复核快捷操作列 (按需抽查排除误检 / 撤销恢复)
            ball_idx = rec.index
            if rec.final_is_ng:
                btn_action = QPushButton("排除误检")
                btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_action.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn_action.setStyleSheet("""
                    QPushButton {
                        background-color: #0c4a6e;
                        color: #38bdf8;
                        border: 1px solid #0284c7;
                        border-radius: 3px;
                        font-family: "Microsoft YaHei", sans-serif;
                        font-size: 10px;
                        font-weight: bold;
                        padding: 1px 3px;
                        margin: 2px;
                    }
                    QPushButton:hover {
                        background-color: #0284c7;
                        color: #ffffff;
                    }
                """)
                btn_action.setToolTip(f"点击一键将焊球 #{ball_idx} 标记为合格 (排除误检)")
                btn_action.clicked.connect(lambda _, b=ball_idx: self.sig_ball_review_toggled.emit(b))
                self.table.setCellWidget(row, 5, btn_action)
            elif is_any_reviewed:
                btn_action = QPushButton("↺ 恢复")
                btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_action.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn_action.setStyleSheet("""
                    QPushButton {
                        background-color: #1e293b;
                        color: #94a3b8;
                        border: 1px solid #334155;
                        border-radius: 3px;
                        font-family: "Microsoft YaHei", sans-serif;
                        font-size: 10px;
                        font-weight: bold;
                        padding: 1px 3px;
                        margin: 2px;
                    }
                    QPushButton:hover {
                        background-color: #334155;
                        color: #f8fafc;
                    }
                """)
                btn_action.setToolTip(f"点击撤销复核，恢复焊球 #{ball_idx} 系统初始判定")
                btn_action.clicked.connect(lambda _, b=ball_idx: self.sig_ball_review_toggled.emit(b))
                self.table.setCellWidget(row, 5, btn_action)
            else:
                self.table.setCellWidget(row, 5, None)
                item_dash = QTableWidgetItem("--")
                item_dash.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_dash.setForeground(QColor(71, 85, 105))
                self.table.setItem(row, 5, item_dash)

    def _handle_context_menu(self, pos):
        """表格右键行菜单弹出"""
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        item_id = self.table.item(row, 0)
        if not item_id:
            return
        ball_idx = item_id.data(Qt.ItemDataRole.UserRole)
        if 1 <= ball_idx <= len(self.records):
            rec = self.records[ball_idx - 1]
            is_rev = (rec.is_manually_reviewed and rec.manual_status == "PASS") or (rec.is_bridge_cleared and not rec.final_is_ng)
            # 正常合格焊球不弹出复核菜单 (杜绝误导)
            if not rec.final_is_ng and not is_rev:
                return

            menu = QMenu(self)
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
            if is_rev:
                act = menu.addAction(f"↺ 撤销复核 (恢复焊球 #{ball_idx} 初始判定)")
            else:
                act = menu.addAction(f"排除误检 (将焊球 #{ball_idx} 标记为合格)")

            chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
            if chosen:
                self.sig_ball_review_toggled.emit(ball_idx)


    def select_ball(self, ball_index: int):
        """外部视口点击焊球时，表格自动滚动到对应行并高亮；若 ball_index < 0 则清除选中"""
        self.current_selected_ball_index = ball_index
        if ball_index < 0:
            self.table.clearSelection()
            return
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
            if self.current_selected_ball_index == ball_index:
                # 再次单击同一行：取消选中并隐藏定位准星 (Toggle 取消)
                self.table.clearSelection()
                self.current_selected_ball_index = -1
                self.sig_ball_selected.emit(-1)
            else:
                self.current_selected_ball_index = ball_index
                self.sig_ball_selected.emit(ball_index)

    def _handle_double_clicked(self, row: int, col: int):
        item = self.table.item(row, 0)
        if item:
            ball_index = item.data(Qt.ItemDataRole.UserRole)
            self.current_selected_ball_index = ball_index
            self.sig_ball_focus_requested.emit(ball_index)
