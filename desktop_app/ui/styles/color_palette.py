# -*- coding: utf-8 -*-
"""
BGA 智能工业质检工作站 - 工业级高对比色彩管理体系 (Defect Color Palette)
-----------------------------------------------------------------------
统一规范视口图元、明细表格、参数控制面板、结果卡片及悬停微探针的语义色彩：
1. 正常焊球 (PASS): 极细翠绿色 (#10b981)
2. 空洞缺陷 (Voiding): 高穿透荧光亮品红 (#ff2a85)
3. 桥连短路 (Bridging): 警戒纯正鲜红 (#ef4444)
4. 虚焊少锡 (Insufficient): 高饱和亮金黄 (#f59e0b)
5. 目标定位与双击聚焦 (Focus Target): 激光电光青 (#00f2fe)
6. 识别置信度 (Confidence): 科技天蓝 (#38bdf8)
"""
from __future__ import annotations

from PySide6.QtGui import QColor


class DefectColors:
    # 1. 正常焊点 (PASS) - 翠绿色
    NORMAL_HEX = "#10b981"
    NORMAL_COLOR = QColor(16, 185, 129)

    # 2. 空洞缺陷 (Voiding)
    # 超标空洞 (NG): 工业高辨识度亮橙色 (#ff7a00)，与桥连鲜红、虚焊紫色、焊球翠绿及准星金黄彻底区分
    VOID_NG_HEX = "#ff7a00"
    VOID_NG_COLOR = QColor(255, 122, 0)
    # 未超标工艺微气泡 (PASS): 清澈电光青 / 冰川蓝 (#00f2fe)，与超标橙色形成极佳冷暖互补
    VOID_NORMAL_HEX = "#00f2fe"
    VOID_NORMAL_COLOR = QColor(0, 242, 254)

    # 3. 桥连短路缺陷 (Bridging) - 警戒鲜红
    BRIDGE_NG_HEX = "#ef4444"
    BRIDGE_NG_COLOR = QColor(239, 68, 68)

    # 4. 虚焊少锡缺陷 (Insufficient Solder) - 高对比电光紫罗兰 (与空洞黄色彻底区分)
    INSUFF_NG_HEX = "#a855f7"
    INSUFF_NG_COLOR = QColor(168, 85, 247)

    # 5. 焊球识别置信度 (Confidence) - 统一使用与焊球一致的翠绿色
    CONF_HEX = "#10b981"
    CONF_COLOR = QColor(16, 185, 129)

    # 6. 表格定位与聚焦准星 (Focus Target) - 超高亮激光纯金黄 (全图最醒目最高对比)
    FOCUS_TARGET_HEX = "#ffe600"
    FOCUS_TARGET_COLOR = QColor(255, 230, 0)
    FOCUS_TABLE_BG_HEX = "#382900"  # 表格选中行金黄光感底色
    FOCUS_TABLE_BG_COLOR = QColor(56, 41, 0)

    # 7. 人工复核合格 / 排除误检 (Manual Reviewed PASS) - 电光青蓝 (#06b6d4)
    REVIEW_PASS_HEX = "#06b6d4"
    REVIEW_PASS_COLOR = QColor(6, 182, 212)
    REVIEW_PASS_BG_HEX = "#083344"
    REVIEW_PASS_BORDER_HEX = "#0891b2"

