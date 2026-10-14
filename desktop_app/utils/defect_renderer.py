# -*- coding: utf-8 -*-
"""
X射线 质检报告专用 - 高清纯缺陷矢量标注图渲染器 (Defect Preview Renderer)
----------------------------------------------------------------------
核心优化特性：
1. 极致色彩区分度：桥连短路使用警戒鲜红 (#dc2626)，空洞超标使用高亮高对比明黄色 (#ffd000)，在灰度 X-Ray 图上一眼立分；
2. 彻底消灭重复标牌：桥连短路仅在短路 ROI 框上统一标注一次 (#A ↔ #B 短路)，涉及焊球仅描红圈，不再重复贴大标牌；
3. 紧凑贴合定位：标牌紧贴缺陷对象外沿 (间隙仅 3-4px)，彻底解决标牌放置过远的问题；
4. 复合缺陷智能合并：单个焊点若同时存在多种异常 (如空洞超标+少锡)，自动合并为单一行标牌，杜绝多标签层叠；
5. 多方向智能防碰撞避让 (4-Way Collision Avoidance)：标牌自动在 上/下/右/左 探测无重叠空间；
6. 零图像遮挡：全图图例移至外部 PDF 页面中呈现，100% 释放图片原始视野。
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QPainter,
    QPen,
)

from desktop_app.core.image_converter import load_image_unicode
from desktop_app.core.inspection_manager import SolderBallRecord

# 工业级高对比色彩管理体系 (红黄高对比升级)
class DefectColors:
    # 纯正警戒鲜红：桥连短路 (#dc2626)
    BRIDGE_NG_COLOR = QColor(220, 38, 38)
    # 高明度纯正亮黄色：空洞超标 (#ffd000)，在灰度底图上与红色反差极大
    VOID_NG_COLOR = QColor(255, 208, 0)
    # 高对比电光紫罗兰：虚焊少锡 (#a855f7)
    INSUFF_NG_COLOR = QColor(168, 85, 247)
    # 电光青蓝：人工复核合格 (#06b6d4)
    REVIEW_PASS_COLOR = QColor(6, 182, 212)
    # 翠绿：正常焊点 (#10b981)
    NORMAL_COLOR = QColor(16, 185, 129)


def _calc_overlap_area(r1: QRectF, r2: QRectF) -> float:
    """计算两个矩形的相交面积"""
    intersect = r1.intersected(r2)
    if intersect.isEmpty() or intersect.width() <= 0 or intersect.height() <= 0:
        return 0.0
    return float(intersect.width() * intersect.height())


def _find_best_badge_rect_for_box(
    rx: float,
    ry: float,
    rw: float,
    rh: float,
    badge_w: float,
    badge_h: float,
    img_w: int,
    img_h: int,
    occupied_rects: List[QRectF],
    gap: float = 4.0,
) -> QRectF:
    """
    针对矩形 ROI 框紧凑贴边放置标牌 (默认紧贴右侧边框，绝不推远)
    """
    candidates = [
        # 0. 紧贴右侧 (垂直居中)
        ("right", QRectF(rx + rw + gap, ry + (rh - badge_h) / 2.0, badge_w, badge_h)),
        # 1. 紧贴左侧 (垂直居中)
        ("left", QRectF(rx - badge_w - gap, ry + (rh - badge_h) / 2.0, badge_w, badge_h)),
        # 2. 紧贴上方 (水平居中)
        ("top", QRectF(rx + (rw - badge_w) / 2.0, ry - badge_h - gap, badge_w, badge_h)),
        # 3. 紧贴下方 (水平居中)
        ("bottom", QRectF(rx + (rw - badge_w) / 2.0, ry + rh + gap, badge_w, badge_h)),
    ]

    best_rect = candidates[0][1]
    min_penalty = float("inf")

    for idx, (name, rect) in enumerate(candidates):
        penalty = float(idx * 5.0)  # 优先右侧、左侧

        # 越界惩罚
        if rect.left() < 2.0:
            penalty += (2.0 - rect.left()) * 150.0
        if rect.top() < 2.0:
            penalty += (2.0 - rect.top()) * 150.0
        if rect.right() > img_w - 2.0:
            penalty += (rect.right() - (img_w - 2.0)) * 150.0
        if rect.bottom() > img_h - 2.0:
            penalty += (rect.bottom() - (img_h - 2.0)) * 150.0

        # 重叠惩罚
        for occ in occupied_rects:
            ov = _calc_overlap_area(rect, occ)
            if ov > 0:
                penalty += ov * 80.0 + 500.0

        if penalty < min_penalty:
            min_penalty = penalty
            best_rect = rect

    # 边界限制
    cx = max(2.0, min(img_w - badge_w - 2.0, best_rect.left()))
    cy = max(2.0, min(img_h - badge_h - 2.0, best_rect.top()))
    final_rect = QRectF(cx, cy, badge_w, badge_h)
    occupied_rects.append(final_rect)
    return final_rect


def _find_best_badge_rect_for_ball(
    center_x: float,
    center_y: float,
    radius: float,
    badge_w: float,
    badge_h: float,
    img_w: int,
    img_h: int,
    occupied_rects: List[QRectF],
    preferred_dirs: Tuple[str, ...] = ("top", "bottom", "right", "left"),
    gap: float = 3.0,
) -> QRectF:
    """
    针对圆形焊点紧贴圆周放置标牌 (贴合紧凑，间隙仅 3px)
    """
    candidates = {
        "top": QRectF(center_x - badge_w / 2.0, center_y - radius - badge_h - gap, badge_w, badge_h),
        "bottom": QRectF(center_x - badge_w / 2.0, center_y + radius + gap, badge_w, badge_h),
        "right": QRectF(center_x + radius + gap, center_y - badge_h / 2.0, badge_w, badge_h),
        "left": QRectF(center_x - radius - badge_w - gap, center_y - badge_h / 2.0, badge_w, badge_h),
    }

    best_rect = candidates[preferred_dirs[0]]
    min_penalty = float("inf")

    for idx, d_name in enumerate(preferred_dirs):
        rect = candidates[d_name]
        penalty = float(idx * 5.0)

        # 越界惩罚
        if rect.left() < 2.0:
            penalty += (2.0 - rect.left()) * 150.0
        if rect.top() < 2.0:
            penalty += (2.0 - rect.top()) * 150.0
        if rect.right() > img_w - 2.0:
            penalty += (rect.right() - (img_w - 2.0)) * 150.0
        if rect.bottom() > img_h - 2.0:
            penalty += (rect.bottom() - (img_h - 2.0)) * 150.0

        # 重叠惩罚
        for occ in occupied_rects:
            ov = _calc_overlap_area(rect, occ)
            if ov > 0:
                penalty += ov * 80.0 + 500.0

        if penalty < min_penalty:
            min_penalty = penalty
            best_rect = rect

    cx = max(2.0, min(img_w - badge_w - 2.0, best_rect.left()))
    cy = max(2.0, min(img_h - badge_h - 2.0, best_rect.top()))
    final_rect = QRectF(cx, cy, badge_w, badge_h)
    occupied_rects.append(final_rect)
    return final_rect


def render_defect_only_preview(
    image_path: str,
    records: List[SolderBallRecord],
    bridge_defects: List[Dict[str, Any]],
    output_dir: Optional[str] = None,
) -> str:
    """
    基于原图渲染仅包含缺陷和异常项的高清全景检测标注图：
    - 纯正大红 (桥连) vs 纯正明黄 (空洞)，色彩对比度拉满；
    - 桥连短路仅在短路框标注一次，涉及焊球不重复贴标牌；
    - 标牌紧贴对象外沿放置，绝不推远；
    - 单焊球复合缺陷自动合并为单一行标牌；
    - 4 方向智能防碰撞避让；
    - 全图图例移至 PDF 页面，图片 100% 原始视野无遮挡。
    """
    if not image_path or not os.path.exists(image_path):
        return image_path

    # 保证存在 QGuiApplication 实例以安全进行字体指标测绘
    _app = QGuiApplication.instance()
    if _app is None:
        _app = QGuiApplication(sys.argv if hasattr(sys, "argv") and sys.argv else ["xray_renderer"])

    # 1. 优先读取完整高清原图
    raw_bgr = load_image_unicode(image_path)
    if raw_bgr is None or raw_bgr.size == 0:
        return image_path

    h, w = raw_bgr.shape[:2]

    # 转为 3 通道 RGB
    if len(raw_bgr.shape) == 2:
        rgb_img = cv2.cvtColor(raw_bgr, cv2.COLOR_GRAY2RGB)
    else:
        rgb_img = cv2.cvtColor(raw_bgr, cv2.COLOR_BGR2RGB)

    # 2. 构造 Qt QImage 进行硬件级抗锯齿离屏绘制
    bytes_per_line = 3 * w
    q_img = QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()

    painter = QPainter(q_img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    # 3. 动态比例尺 (适应不同分辨率图像)
    base_dim = max(w, h)
    scale = max(0.8, min(3.5, base_dim / 1300.0))

    pen_thick = max(1.8, 2.2 * scale)
    pen_thin = max(1.1, 1.5 * scale)
    font_size = max(8, int(9.0 * scale))
    badge_font = QFont("Microsoft YaHei", font_size, QFont.Weight.Bold)
    painter.setFont(badge_font)
    fm = QFontMetrics(badge_font)

    # 高对比色彩体系
    col_bridge = DefectColors.BRIDGE_NG_COLOR     # 纯正警戒鲜红 (#dc2626)
    col_void = DefectColors.VOID_NG_COLOR         # 纯正高亮明黄 (#ffd000)
    col_insuff = DefectColors.INSUFF_NG_COLOR     # 高对比电光紫 (#a855f7)
    col_review = DefectColors.REVIEW_PASS_COLOR   # 电光青蓝 (#06b6d4)

    has_defects = False
    occupied_badge_rects: List[QRectF] = []

    # --------------------------------------------------------------
    # 步骤 A: 预处理桥连短路缺陷，区分活跃短路与已排除误检短路
    # --------------------------------------------------------------
    active_bridge_defects = []
    reviewed_bridge_defects = []
    active_bridge_ball_indices = set()
    reviewed_bridge_ball_indices = set()

    for b in bridge_defects:
        if b.get("is_reviewed_pass", False):
            reviewed_bridge_defects.append(b)
            has_defects = True
            for s_idx in b.get("ball_indices", []):
                reviewed_bridge_ball_indices.add(s_idx)
        else:
            active_bridge_defects.append(b)
            has_defects = True
            for s_idx in b.get("ball_indices", []):
                active_bridge_ball_indices.add(s_idx)

    # --------------------------------------------------------------
    # 步骤 B: 绘制所有缺陷与复核焊球轮廓 (正常合格焊球 100% 保持底图零遮挡)
    # --------------------------------------------------------------
    defect_records_to_label = []

    for rec in records:
        is_ball_rev_pass = (rec.is_manually_reviewed and rec.manual_status == "PASS")
        is_bridge_cleared = (getattr(rec, "is_bridge_cleared", False) and not rec.final_is_ng)
        is_cleared = is_ball_rev_pass or is_bridge_cleared
        is_ng = rec.final_is_ng

        if not is_ng and not is_cleared:
            continue  # 正常焊球 100% 保持底图原貌！

        has_defects = True
        cx, cy, r = rec.cx, rec.cy, rec.radius

        # 确定主轮廓颜色 (优先级：桥连大红 > 空洞纯黄 > 虚焊紫 > 复核青)
        if is_ng:
            if getattr(rec, "has_active_bridge", False) or rec.index in active_bridge_ball_indices:
                pen_c = col_bridge
            elif rec.is_void_ng:
                pen_c = col_void
            elif rec.is_insufficient:
                pen_c = col_insuff
            else:
                pen_c = col_void
        else:
            pen_c = col_review

        # 绘制焊球外圈: 复核排除合格的使用虚线圈，缺陷使用实线圈
        if is_cleared:
            painter.setPen(QPen(pen_c, pen_thick, Qt.PenStyle.DashLine))
        else:
            painter.setPen(QPen(pen_c, pen_thick))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r, r)

        # 若为空洞超标，描绘内部气泡圈 (高对比纯明黄色)
        if rec.is_void_ng and rec.void_circles:
            painter.setPen(QPen(col_void, pen_thin))
            for vc in rec.void_circles:
                vcx, vcy = vc.get("center", (cx, cy))
                vr = float(vc.get("radius", 2.0))
                painter.drawEllipse(QPointF(vcx, vcy), vr, vr)

        # 判断该焊球是否需要贴标牌：
        # 核心逻辑：若该球【仅作为桥连对】受波及，且自身没有任何其他缺陷 (无超标空洞、无少锡)，
        # 则不需要贴单独标牌！因为桥连短路框上已经统一标明了球对或已排除！这样直接消除一个短路冒出 3 个标题的问题！
        is_pure_bridge_ball = (
            (rec.is_bridge or rec.index in active_bridge_ball_indices or rec.index in reviewed_bridge_ball_indices)
            and not rec.is_void_ng
            and not rec.is_insufficient
        )

        if not is_pure_bridge_ball:
            defect_records_to_label.append(rec)

    # --------------------------------------------------------------
    # 步骤 C: 绘制桥连短路 ROI 框及紧贴放置的标牌 (包含活跃短路与已排除短路)
    # --------------------------------------------------------------
    # C1. 活跃桥连短路 (纯正警戒鲜红)
    for b in active_bridge_defects:
        roi_box = b.get("roi_box", (0, 0, 0, 0))
        rx, ry, rw, rh = roi_box
        if rw <= 0 or rh <= 0:
            continue

        # 绘制警戒鲜红矩形框
        painter.setPen(QPen(col_bridge, pen_thick))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(rx, ry, rw, rh))

        # 标牌文本：若包含涉及球对则标明如 "#191↔#312 短路"
        pair_indices = b.get("ball_indices", [])
        if len(pair_indices) >= 2:
            p_sorted = sorted(pair_indices[:2])
            b_text = f"#{p_sorted[0]}↔#{p_sorted[1]} 短路"
        elif len(pair_indices) == 1:
            b_text = f"#{pair_indices[0]} 桥连短路"
        else:
            b_text = "桥连短路"

        tw = fm.horizontalAdvance(b_text) + 8 * scale
        th = fm.height() + 3 * scale

        badge_rect = _find_best_badge_rect_for_box(
            rx=rx,
            ry=ry,
            rw=rw,
            rh=rh,
            badge_w=tw,
            badge_h=th,
            img_w=w,
            img_h=h,
            occupied_rects=occupied_badge_rects,
            gap=4.0 * scale,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(15, 23, 42, 190)))
        painter.drawRoundedRect(badge_rect, 3 * scale, 3 * scale)

        painter.setPen(QPen(col_bridge, 1.2))
        painter.drawRoundedRect(badge_rect, 3 * scale, 3 * scale)
        painter.setPen(QPen(col_bridge, 1.0))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, b_text)

    # C2. 已人工复核排除的桥连缺陷 (高对比电光青虚线框 + [已排除] 标牌)
    for b in reviewed_bridge_defects:
        roi_box = b.get("roi_box", (0, 0, 0, 0))
        rx, ry, rw, rh = roi_box
        if rw <= 0 or rh <= 0:
            continue

        # 绘制电光青色虚线矩形框
        painter.setPen(QPen(col_review, pen_thick, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(rx, ry, rw, rh))

        pair_indices = b.get("ball_indices", [])
        if len(pair_indices) >= 2:
            p_sorted = sorted(pair_indices[:2])
            b_text = f"#{p_sorted[0]}↔#{p_sorted[1]} [已排除]"
        elif len(pair_indices) == 1:
            b_text = f"#{pair_indices[0]} [已排除]"
        else:
            b_text = "[已排除]"

        tw = fm.horizontalAdvance(b_text) + 8 * scale
        th = fm.height() + 3 * scale

        badge_rect = _find_best_badge_rect_for_box(
            rx=rx,
            ry=ry,
            rw=rw,
            rh=rh,
            badge_w=tw,
            badge_h=th,
            img_w=w,
            img_h=h,
            occupied_rects=occupied_badge_rects,
            gap=4.0 * scale,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(15, 23, 42, 190)))
        painter.drawRoundedRect(badge_rect, 3 * scale, 3 * scale)

        painter.setPen(QPen(col_review, 1.2))
        painter.drawRoundedRect(badge_rect, 3 * scale, 3 * scale)
        painter.setPen(QPen(col_review, 1.0))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, b_text)

    # --------------------------------------------------------------
    # 步骤 D: 绘制有自身缺陷焊球的标牌 (复合缺陷智能合并 + 紧贴避让)
    # --------------------------------------------------------------
    for rec in defect_records_to_label:
        is_ball_rev_pass = (rec.is_manually_reviewed and rec.manual_status == "PASS")
        is_bridge_cleared = (getattr(rec, "is_bridge_cleared", False) and not rec.final_is_ng)
        cx, cy, r = rec.cx, rec.cy, rec.radius

        # 1. 复合缺陷合并逻辑：一个焊球最多只产生一个紧凑文本
        def_parts = []
        if is_ball_rev_pass:
            def_parts.append("复核PASS")
            badge_col = col_review
        elif is_bridge_cleared:
            def_parts.append("桥连排除PASS")
            badge_col = col_review
        else:
            if rec.is_void_ng:
                def_parts.append(f"空洞{rec.void_rate * 100:.1f}%")
            if rec.is_insufficient:
                def_parts.append(f"少锡-{rec.reduction_percent:.1f}%")
            if getattr(rec, "has_active_bridge", False) or (rec.is_bridge and not getattr(rec, "is_bridge_cleared", False)):
                def_parts.append("桥连")

            # 标牌颜色 (优先：桥连大红 > 空洞纯黄 > 虚焊紫)
            if getattr(rec, "has_active_bridge", False) or (rec.is_bridge and not getattr(rec, "is_bridge_cleared", False)):
                badge_col = col_bridge
            elif rec.is_void_ng:
                badge_col = col_void
            else:
                badge_col = col_insuff

        desc_str = "+".join(def_parts) if def_parts else "异常"
        badge_text = f"#{rec.index} {desc_str}"

        # 2. 标牌尺寸
        tw = fm.horizontalAdvance(badge_text) + 8 * scale
        th = fm.height() + 3 * scale

        # 3. 紧贴焊球圆周放置 (间隙仅 3px，上下左右优先选择最空旷方位)
        pref_dirs = ("top", "bottom", "right", "left")

        badge_rect = _find_best_badge_rect_for_ball(
            center_x=cx,
            center_y=cy,
            radius=r,
            badge_w=tw,
            badge_h=th,
            img_w=w,
            img_h=h,
            occupied_rects=occupied_badge_rects,
            preferred_dirs=pref_dirs,
            gap=3.0 * scale,
        )

        # 4. 绘制半透明微型胶囊标牌
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(15, 23, 42, 190)))
        painter.drawRoundedRect(badge_rect, 3 * scale, 3 * scale)

        painter.setPen(QPen(badge_col, 1.2))
        painter.drawRoundedRect(badge_rect, 3 * scale, 3 * scale)
        painter.setPen(QPen(badge_col, 1.0))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

    # --------------------------------------------------------------
    # 步骤 E: 若全板合格 (无任何缺陷)，在左上角打上精致良品角标
    # --------------------------------------------------------------
    if not has_defects:
        pass_font = QFont("Microsoft YaHei", max(9, int(10.5 * scale)), QFont.Weight.Bold)
        painter.setFont(pass_font)
        p_fm = QFontMetrics(pass_font)
        p_text = "整板质量合格 (PASS) - 未检出异常"
        pw = p_fm.horizontalAdvance(p_text) + 16 * scale
        ph = p_fm.height() + 8 * scale
        px = 12 * scale
        py = 12 * scale

        painter.setPen(QPen(QColor(34, 197, 94, 220), 1.2))
        painter.setBrush(QBrush(QColor(6, 78, 59, 210)))
        painter.drawRoundedRect(QRectF(px, py, pw, ph), 4 * scale, 4 * scale)

        painter.setPen(QPen(QColor(220, 252, 231), 1.0))
        painter.drawText(QRectF(px, py, pw, ph), Qt.AlignmentFlag.AlignCenter, p_text)

    painter.end()

    # 输出高保真紧凑 JPEG 文件 (针对 PDF 工业报告排版进行分辨率适配与极速 DCT 流优化)
    if output_dir is None:
        output_dir = os.path.join(tempfile.gettempdir(), "xray_clean_reports")
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(image_path))[0]
    stamp = int(time.time() * 1000)
    out_path = os.path.join(output_dir, f"vis_clean_{base_name}_{stamp}.jpg")

    # 针对超大图像做适度上限约束 (最大边 1600px 对应 A4 版面 250+ DPI，既高精度又大幅降低 PDF 构建延迟)
    max_dim = 1600
    if q_img.width() > max_dim or q_img.height() > max_dim:
        q_save = q_img.scaled(
            max_dim,
            max_dim,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        q_save.save(out_path, "JPEG", 92)
    else:
        q_img.save(out_path, "JPEG", 92)

    return out_path
