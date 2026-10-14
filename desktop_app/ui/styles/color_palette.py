# -*- coding: utf-8 -*-
"""
X射线智能工业质检工作站 - 工业级高对比色彩管理体系 (Defect Color Palette)
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
    # 超标空洞 (NG): 高饱和度纯正明黄色 (#ffd000)，在 X-Ray 底图上拥有极高辨识度，与桥连大红形成鲜明对比
    VOID_NG_HEX = "#ffd000"
    VOID_NG_COLOR = QColor(255, 208, 0)
    # 未超标工艺微气泡 (PASS): 清澈电光青 / 冰川蓝 (#00f2fe)
    VOID_NORMAL_HEX = "#00f2fe"
    VOID_NORMAL_COLOR = QColor(0, 242, 254)

    # 3. 桥连短路缺陷 (Bridging) - 纯正警戒鲜红 (#dc2626)
    BRIDGE_NG_HEX = "#dc2626"
    BRIDGE_NG_COLOR = QColor(220, 38, 38)

    # 4. 虚焊少锡缺陷 (Insufficient Solder) - 高对比电光紫罗兰 (与空洞黄色彻底区分)
    INSUFF_NG_HEX = "#a855f7"
    INSUFF_NG_COLOR = QColor(168, 85, 247)

    # 5. 焊球识别置信度 (Confidence) - 统一使用与焊球一致的翠绿色
    CONF_HEX = "#10b981"
    CONF_COLOR = QColor(16, 185, 129)

    # 6. 表格定位与聚焦准星 (Focus Target) - 高饱和激光亮红 (#ff1744)
    # 针对白底/浅灰焊板基底提供超强穿透力与醒目视觉定位
    FOCUS_TARGET_HEX = "#ff1744"
    FOCUS_TARGET_COLOR = QColor(255, 23, 68)
    FOCUS_TABLE_BG_HEX = "#881337"  # 表格选中行深邃绯红宝石底色，与亮红准星呼应
    FOCUS_TABLE_BG_COLOR = QColor(136, 19, 55)

    # 7. 人工复核合格 / 排除误检 (Manual Reviewed PASS) - 电光青蓝 (#06b6d4)
    REVIEW_PASS_HEX = "#06b6d4"
    REVIEW_PASS_COLOR = QColor(6, 182, 212)
    REVIEW_PASS_BG_HEX = "#083344"
    REVIEW_PASS_BORDER_HEX = "#0891b2"

