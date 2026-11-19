# -*- coding: utf-8 -*-
"""
🌟 客户端风格高保真质检标注图渲染器 (Client-Style Inspection Result Image Renderer)
-----------------------------------------------------------------------------------
将 X 射线 BGA 检测结果以完全匹配客户端 GUI 视口的高清矢量质感渲染并输出为图像文件：
1. 双视口模式支持：
   - all_outline (客户端默认): 细翠绿圈展示全局焊球网格阵列，微气泡细青圈，超标缺陷高亮着色；
   - defect_only (纯缺陷专注): 100% 保持正常焊点原始底图，仅醒目突出超标缺陷焊点与桥连框；
2. 工业级高对比色彩系统：
   - 正常焊点：极细翠绿 (#10b981)
   - 空洞超标：高亮明黄 (#ffd000) + 内部气泡填充
   - 桥连短路：纯正大红 (#dc2626) + 虚线 ROI 框与球对指示
   - 少锡虚焊：电光紫罗兰 (#a855f7) + 缩减同心虚环
   - 工艺微气泡：极细电光青 (#00f2fe)
3. 智能防碰撞微型标牌体系：
   - 4-Way 自动探测避让，紧贴对象边缘；
   - 复合缺陷智能合并，消除标签重复叠放；
4. 客户端级工业 HUD 状态看板 (可选)：
   - 顶部深色 Slate 仪表带，集成 PASS / REJECT 结论徽章与缺陷分项统计；
5. 底部工业图例指南 (可选)：
   - 标准化图例与 IPC-A-610 工业标准标头。
"""
from __future__ import annotations

import os
import sys
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
from desktop_app.core.inspection_manager import InspectionSession, SolderBallRecord
from desktop_app.ui.styles.color_palette import DefectColors


def _ensure_gui_application() -> QGuiApplication:
    """确保存在 QGuiApplication 实例以正常执行字体度量与离屏矢量绘图"""
    app = QGuiApplication.instance()
    if app is None:
        app = QGuiApplication(sys.argv if hasattr(sys, "argv") and sys.argv else ["xray_client_renderer"])
    return app


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
    """针对矩形 ROI 框紧凑贴边放置标牌 (4 向避让)"""
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


def _find_best_badge_rect_for_ball(
    center_x: float,
    center_y: float,
    radius: float,
    badge_w: float,
    badge_h: float,
    img_w: int,
    img_h: int,
    occupied_rects: List[QRectF],
    gap: float = 3.0,
) -> QRectF:
    """针对圆形焊点紧贴圆周放置标牌 (4 方向防碰撞)"""
    preferred_dirs = ("top", "bottom", "right", "left")
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

        if rect.left() < 2.0:
            penalty += (2.0 - rect.left()) * 150.0
        if rect.top() < 2.0:
            penalty += (2.0 - rect.top()) * 150.0
        if rect.right() > img_w - 2.0:
            penalty += (rect.right() - (img_w - 2.0)) * 150.0
        if rect.bottom() > img_h - 2.0:
            penalty += (rect.bottom() - (img_h - 2.0)) * 150.0

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


def render_client_style_inspection_image(
    image_path: str,
    session: InspectionSession,
    output_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    view_mode: str = "all_outline",     # "all_outline" (默认) | "defect_only"
    include_banner: bool = True,       # 是否包含顶部客户端 HUD 状态看板
    include_legend: bool = True,       # 是否包含底部工业图例栏
    image_quality: int = 95,           # JPEG 保存质量 (1-100)
    chip_label: Optional[str] = None,
) -> str:
    """
    🌟 核心渲染入口：将检测会话数据绘制为完全类似于客户端视口的超高清图像。

    参数:
        image_path: 待测原始 X-Ray 图像路径
        session: 质检会话实例 (包含焊球记录、桥连缺陷列表、判废状态与耗时等)
        output_path: 具体输出文件路径 (若指定则优先使用)
        output_dir: 输出目录 (若未指定具体文件名，自动按规则命名并保存于此)
        view_mode: 视图模式 ("all_outline" 全部焊球细绿圈 | "defect_only" 仅高亮缺陷)
        include_banner: 是否附加客户端风格顶部 HUD 看板
        include_legend: 是否附加底部工业图例指南
        image_quality: JPEG 输出质量
        chip_label: 芯片/工单名称 (默认使用输入图片文件名)

    返回:
        生成图片的绝对路径
    """
    _ensure_gui_application()

    if not os.path.exists(image_path):
        raise FileNotFoundError(f"未找到输入图片: {image_path}")

    # 1. 读入原始高清图像
    raw_bgr = load_image_unicode(image_path)
    if raw_bgr is None or raw_bgr.size == 0:
        raise ValueError(f"无法读取图片数据: {image_path}")

    orig_h, orig_w = raw_bgr.shape[:2]
    if len(raw_bgr.shape) == 2:
        rgb_img = cv2.cvtColor(raw_bgr, cv2.COLOR_GRAY2RGB)
    else:
        rgb_img = cv2.cvtColor(raw_bgr, cv2.COLOR_BGR2RGB)

    # 2. 动态比例尺计算 (适应 600px ~ 4000px 各分辨率图像)
    base_dim = max(orig_w, orig_h)
    scale = max(0.8, min(3.5, base_dim / 1300.0))

    # 自适应两行或单行 Banner 高度
    is_compact_banner = (orig_w < 820)
    if include_banner:
        banner_h = int((86 if is_compact_banner else 66) * scale)
    else:
        banner_h = 0

    legend_h = int(36 * scale) if include_legend else 0
    canvas_w = orig_w
    canvas_h = orig_h + banner_h + legend_h

    # 3. 创建 Qt 离屏画板并开启硬件级抗锯齿
    q_canvas = QImage(canvas_w, canvas_h, QImage.Format.Format_RGB888)
    q_canvas.fill(QColor(11, 15, 25))  # 客户端深邃底色 (#0b0f19)

    painter = QPainter(q_canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    # 将原始图像贴在画布主体位置 (y 偏移 banner_h)
    q_raw = QImage(rgb_img.data, orig_w, orig_h, 3 * orig_w, QImage.Format.Format_RGB888)
    painter.drawImage(0, banner_h, q_raw)

    # 4. 色彩定义 (统一复用客户端 DefectColors)
    col_normal = DefectColors.NORMAL_COLOR          # 翠绿 (#10b981)
    col_void_ng = DefectColors.VOID_NG_COLOR        # 纯明黄 (#ffd000)
    col_void_normal = DefectColors.VOID_NORMAL_COLOR# 微气泡青 (#00f2fe)
    col_bridge_ng = DefectColors.BRIDGE_NG_COLOR    # 警戒鲜红 (#dc2626)
    col_insuff_ng = DefectColors.INSUFF_NG_COLOR    # 电光紫罗兰 (#a855f7)
    col_review = DefectColors.REVIEW_PASS_COLOR      # 复核青蓝 (#06b6d4)

    pen_thick = max(1.8, 2.3 * scale)
    pen_medium = max(1.3, 1.6 * scale)
    pen_thin = max(1.0, 1.2 * scale)

    font_badge_size = max(8, int(9.2 * scale))
    badge_font = QFont("Microsoft YaHei", font_badge_size, QFont.Weight.Bold)
    badge_fm = QFontMetrics(badge_font)

    occupied_badge_rects: List[QRectF] = []
    records = session.solder_records
    bridge_defects = session.bridge_defects

    # --------------------------------------------------------------
    # 步骤 A: 预处理桥连缺陷信息
    # --------------------------------------------------------------
    active_bridge_defects = []
    reviewed_bridge_defects = []
    active_bridge_ball_indices = set()
    reviewed_bridge_ball_indices = set()

    for b in bridge_defects:
        if b.get("is_reviewed_pass", False):
            reviewed_bridge_defects.append(b)
            for s_idx in b.get("ball_indices", []):
                reviewed_bridge_ball_indices.add(s_idx)
        else:
            active_bridge_defects.append(b)
            for s_idx in b.get("ball_indices", []):
                active_bridge_ball_indices.add(s_idx)

    # --------------------------------------------------------------
    # 步骤 B: 绘制焊球外圈与内部气泡
    # --------------------------------------------------------------
    defect_records_to_label: List[SolderBallRecord] = []

    for rec in records:
        cx = rec.cx
        cy = rec.cy + banner_h  # 注意 Y 轴加上 banner 偏移
        r = rec.radius

        is_ball_rev_pass = (rec.is_manually_reviewed and rec.manual_status == "PASS")
        is_bridge_cleared = (getattr(rec, "is_bridge_cleared", False) and not rec.final_is_ng)
        is_cleared = is_ball_rev_pass or is_bridge_cleared
        is_ng = rec.final_is_ng

        if not is_ng and not is_cleared:
            # 合格正常焊球
            if view_mode == "all_outline":
                # 绘制客户端标志性的极细半透明翠绿外圈
                painter.setPen(QPen(QColor(16, 185, 129, 210), pen_thin))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(cx, cy), r, r)

                # 绘制正常微小气泡 (极细电光青圈)
                if rec.void_circles:
                    painter.setPen(QPen(QColor(0, 242, 254, 180), max(0.8, 1.0 * scale)))
                    for vc in rec.void_circles:
                        vcx, vcy = vc.get("center", (rec.cx, rec.cy))
                        vr = float(vc.get("radius", 1.5))
                        painter.drawEllipse(QPointF(vcx, vcy + banner_h), vr, vr)
            continue

        # --- 缺陷焊点或复核焊点 ---
        # 1. 主轮廓颜色
        if is_ng:
            if getattr(rec, "has_active_bridge", False) or rec.index in active_bridge_ball_indices:
                pen_c = col_bridge_ng
            elif rec.is_void_ng:
                pen_c = col_void_ng
            elif rec.is_insufficient:
                pen_c = col_insuff_ng
            else:
                pen_c = col_void_ng
        else:
            pen_c = col_review

        # 2. 焊球外圈
        if is_cleared:
            painter.setPen(QPen(pen_c, pen_thick, Qt.PenStyle.DashLine))
        else:
            painter.setPen(QPen(pen_c, pen_thick))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r, r)

        # 3. 少锡虚焊焊球：额外绘制同心虚线缩减指示环
        if rec.is_insufficient and not is_cleared:
            inner_r = max(2.0, r * (1.0 - (rec.reduction_percent / 100.0) ** 0.5))
            painter.setPen(QPen(col_insuff_ng, pen_thin, Qt.PenStyle.DashLine))
            painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        # 4. 空洞超标焊球：绘制内部微气泡并着色微填充
        if rec.is_void_ng and rec.void_circles:
            painter.setPen(QPen(col_void_ng, pen_medium))
            painter.setBrush(QBrush(QColor(255, 208, 0, 50)))
            for vc in rec.void_circles:
                vcx, vcy = vc.get("center", (rec.cx, rec.cy))
                vr = float(vc.get("radius", 2.0))
                painter.drawEllipse(QPointF(vcx, vcy + banner_h), vr, vr)
            painter.setBrush(Qt.BrushStyle.NoBrush)

        # 5. 过滤仅涉及桥连的纯受累球，其余加入待贴标牌列表
        is_pure_bridge_ball = (
            (rec.is_bridge or rec.index in active_bridge_ball_indices or rec.index in reviewed_bridge_ball_indices)
            and not rec.is_void_ng
            and not rec.is_insufficient
        )
        if not is_pure_bridge_ball:
            defect_records_to_label.append(rec)

    # --------------------------------------------------------------
    # 步骤 C: 绘制桥连短路 ROI 框及标牌
    # --------------------------------------------------------------
    painter.setFont(badge_font)

    # C1. 活跃桥连短路 (警戒红虚线框)
    for b in active_bridge_defects:
        rx, ry, rw, rh = b.get("roi_box", (0, 0, 0, 0))
        if rw <= 0 or rh <= 0:
            continue
        ry_offset = ry + banner_h

        painter.setPen(QPen(col_bridge_ng, pen_thick, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(rx, ry_offset, rw, rh))

        pair_indices = b.get("ball_indices", [])
        if len(pair_indices) >= 2:
            p_sorted = sorted(pair_indices[:2])
            b_text = f"#{p_sorted[0]}↔#{p_sorted[1]} 桥连短路"
        elif len(pair_indices) == 1:
            b_text = f"#{pair_indices[0]} 桥连短路"
        else:
            b_text = "桥连短路"

        tw = badge_fm.horizontalAdvance(b_text) + 10 * scale
        th = badge_fm.height() + 4 * scale

        badge_rect = _find_best_badge_rect_for_box(
            rx=rx,
            ry=ry_offset,
            rw=rw,
            rh=rh,
            badge_w=tw,
            badge_h=th,
            img_w=canvas_w,
            img_h=orig_h + banner_h,
            occupied_rects=occupied_badge_rects,
            gap=4.0 * scale,
        )

        # 胶囊深色背景与描边
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(15, 23, 42, 220)))
        painter.drawRoundedRect(badge_rect, 4 * scale, 4 * scale)

        painter.setPen(QPen(col_bridge_ng, 1.4 * scale))
        painter.drawRoundedRect(badge_rect, 4 * scale, 4 * scale)

        painter.setPen(QPen(QColor(254, 242, 242), 1.0))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, b_text)

    # C2. 复核排除的桥连短路 (电光青虚线框)
    for b in reviewed_bridge_defects:
        rx, ry, rw, rh = b.get("roi_box", (0, 0, 0, 0))
        if rw <= 0 or rh <= 0:
            continue
        ry_offset = ry + banner_h

        painter.setPen(QPen(col_review, pen_thick, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(rx, ry_offset, rw, rh))

        pair_indices = b.get("ball_indices", [])
        if len(pair_indices) >= 2:
            p_sorted = sorted(pair_indices[:2])
            b_text = f"#{p_sorted[0]}↔#{p_sorted[1]} [已排除]"
        else:
            b_text = "[已排除]"

        tw = badge_fm.horizontalAdvance(b_text) + 10 * scale
        th = badge_fm.height() + 4 * scale

        badge_rect = _find_best_badge_rect_for_box(
            rx=rx,
            ry=ry_offset,
            rw=rw,
            rh=rh,
            badge_w=tw,
            badge_h=th,
            img_w=canvas_w,
            img_h=orig_h + banner_h,
            occupied_rects=occupied_badge_rects,
            gap=4.0 * scale,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(15, 23, 42, 220)))
        painter.drawRoundedRect(badge_rect, 4 * scale, 4 * scale)

        painter.setPen(QPen(col_review, 1.4 * scale))
        painter.drawRoundedRect(badge_rect, 4 * scale, 4 * scale)

        painter.setPen(QPen(col_review, 1.0))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, b_text)

    # --------------------------------------------------------------
    # 步骤 D: 绘制焊球缺陷紧凑胶囊标牌 (复合缺陷合并 + 4 向避让)
    # --------------------------------------------------------------
    for rec in defect_records_to_label:
        cx = rec.cx
        cy = rec.cy + banner_h
        r = rec.radius

        is_ball_rev_pass = (rec.is_manually_reviewed and rec.manual_status == "PASS")
        is_bridge_cleared = (getattr(rec, "is_bridge_cleared", False) and not rec.final_is_ng)

        def_parts = []
        if is_ball_rev_pass:
            def_parts.append("复核PASS")
            badge_col = col_review
        elif is_bridge_cleared:
            def_parts.append("桥连排除")
            badge_col = col_review
        else:
            if rec.is_void_ng:
                def_parts.append(f"空洞{rec.void_rate * 100:.1f}%")
            if rec.is_insufficient:
                def_parts.append(f"少锡-{rec.reduction_percent:.1f}%")
            if getattr(rec, "has_active_bridge", False) or (rec.is_bridge and not getattr(rec, "is_bridge_cleared", False)):
                def_parts.append("桥连")

            if getattr(rec, "has_active_bridge", False) or (rec.is_bridge and not getattr(rec, "is_bridge_cleared", False)):
                badge_col = col_bridge_ng
            elif rec.is_void_ng:
                badge_col = col_void_ng
            else:
                badge_col = col_insuff_ng

        desc_str = "+".join(def_parts) if def_parts else "异常"
        # 优先使用 BGA 标准引脚位号 (如 A1, C12)
        pin_lbl = rec.pin_name if getattr(rec, "pin_name", "") else f"#{rec.index}"
        badge_text = f"{pin_lbl} {desc_str}"

        tw = badge_fm.horizontalAdvance(badge_text) + 10 * scale
        th = badge_fm.height() + 4 * scale

        badge_rect = _find_best_badge_rect_for_ball(
            center_x=cx,
            center_y=cy,
            radius=r,
            badge_w=tw,
            badge_h=th,
            img_w=canvas_w,
            img_h=orig_h + banner_h,
            occupied_rects=occupied_badge_rects,
            gap=3.5 * scale,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(15, 23, 42, 220)))
        painter.drawRoundedRect(badge_rect, 4 * scale, 4 * scale)

        painter.setPen(QPen(badge_col, 1.3 * scale))
        painter.drawRoundedRect(badge_rect, 4 * scale, 4 * scale)

        painter.setPen(QPen(badge_col, 1.0))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

    # --------------------------------------------------------------
    # 步骤 E: 绘制客户端级工业顶部 HUD 状态看板 (Top Banner)
    # --------------------------------------------------------------
    if include_banner and banner_h > 0:
        _render_top_hud_banner(
            painter=painter,
            width=canvas_w,
            banner_h=banner_h,
            scale=scale,
            session=session,
            image_path=image_path,
            chip_label=chip_label,
        )

    # --------------------------------------------------------------
    # 步骤 F: 绘制底部工业图例指南 (Bottom Legend)
    # --------------------------------------------------------------
    if include_legend and legend_h > 0:
        _render_bottom_legend(
            painter=painter,
            width=canvas_w,
            y_start=orig_h + banner_h,
            legend_h=legend_h,
            scale=scale,
        )

    painter.end()

    # 5. 确定保存路径并写盘
    base_stem = os.path.splitext(os.path.basename(image_path))[0]
    if output_path is None:
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "output", "client_inspected")
        os.makedirs(output_dir, exist_ok=True)
        status_tag = session.board_status.upper()
        output_path = os.path.join(output_dir, f"{base_stem}_inspected_{status_tag}.jpg")
    else:
        out_parent = os.path.dirname(os.path.abspath(output_path))
        if out_parent:
            os.makedirs(out_parent, exist_ok=True)

    # 保存高保真 JPEG
    q_canvas.save(output_path, "JPEG", max(70, min(100, image_quality)))
    return os.path.abspath(output_path)


def _render_top_hud_banner(
    painter: QPainter,
    width: int,
    banner_h: int,
    scale: float,
    session: InspectionSession,
    image_path: str,
    chip_label: Optional[str] = None,
):
    """绘制客户端专业工业级 HUD 看板 (自适应单行/双行排版)"""
    is_ng = (session.board_status == "NG")
    line_col = QColor(220, 38, 38) if is_ng else QColor(16, 185, 129)

    # 1. 看板背景与底部分割线
    banner_rect = QRectF(0, 0, width, banner_h)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(15, 23, 42)))  # Slate 900
    painter.drawRect(banner_rect)

    # 底部分割边线
    painter.setPen(QPen(line_col, max(2.0, 2.5 * scale)))
    painter.drawLine(0, banner_h - 1, width, banner_h - 1)

    fname = chip_label or os.path.basename(image_path)
    records = session.solder_records
    void_ng_count = sum(1 for r in records if r.final_is_ng and r.is_void_ng)
    insuff_count = sum(1 for r in records if r.final_is_ng and r.is_insufficient)
    bridge_count = len([b for b in session.bridge_defects if not b.get("is_reviewed_pass", False)])
    elapsed_ms = getattr(session, "elapsed_ms", 0.0)

    title_font = QFont("Microsoft YaHei", max(9, int(11.5 * scale)), QFont.Weight.Bold)
    sub_font = QFont("Microsoft YaHei", max(8, int(9.2 * scale)), QFont.Weight.Normal)
    status_font = QFont("Microsoft YaHei", max(9, int(11.5 * scale)), QFont.Weight.Bold)

    pad_left = 14 * scale
    pad_right = 14 * scale

    # 判断是否为中窄图 (两行紧凑布局)
    is_compact = (width < 820)

    if is_compact:
        # === 紧凑双行布局 ===
        # 第一行 (Y ~ 0..42*scale): 左侧标题，右侧大 PASS/NG 徽章
        painter.setFont(title_font)
        painter.setPen(QPen(QColor(248, 250, 252)))
        painter.drawText(QPointF(pad_left, 26 * scale), "🔬 X-ray AI Inspector")

        badge_w = min(120 * scale, width * 0.32)
        badge_h = 28 * scale
        badge_x = width - pad_right - badge_w
        badge_y = 10 * scale
        b_rect = QRectF(badge_x, badge_y, badge_w, badge_h)

        if is_ng:
            painter.setPen(QPen(QColor(220, 38, 38), 1.5 * scale))
            painter.setBrush(QBrush(QColor(127, 29, 29, 230)))
            b_text = "▲ REJECT 缺陷"
            t_col = QColor(254, 242, 242)
        else:
            painter.setPen(QPen(QColor(16, 185, 129), 1.5 * scale))
            painter.setBrush(QBrush(QColor(6, 78, 59, 230)))
            b_text = "● PASS 合格"
            t_col = QColor(240, 253, 244)

        painter.drawRoundedRect(b_rect, 5 * scale, 5 * scale)
        painter.setFont(status_font)
        painter.setPen(QPen(t_col, 1.0))
        painter.drawText(b_rect, Qt.AlignmentFlag.AlignCenter, b_text)

        # 第二行 (Y ~ 48*scale..80*scale): 指标横向流动排布
        chips = [
            ("工件", fname, QColor(148, 163, 184)),
            ("焊球", str(len(records)), QColor(16, 185, 129)),
            ("空洞NG", str(void_ng_count), QColor(255, 208, 0) if void_ng_count > 0 else QColor(148, 163, 184)),
            ("桥连", str(bridge_count), QColor(220, 38, 38) if bridge_count > 0 else QColor(148, 163, 184)),
            ("少锡", str(insuff_count), QColor(168, 85, 247) if insuff_count > 0 else QColor(148, 163, 184)),
        ]
        if elapsed_ms > 0:
            chips.append(("耗时", f"{elapsed_ms:.0f}ms", QColor(148, 163, 184)))

        cur_x = pad_left
        painter.setFont(sub_font)
        chip_fm = QFontMetrics(sub_font)
        row2_y = 48 * scale
        chip_h = 24 * scale

        for lbl, val, val_col in chips:
            text = f"{lbl}:{val}"
            cw = chip_fm.horizontalAdvance(text) + 12 * scale
            if cur_x + cw > width - pad_right:
                break  # 避免超出画布右边界
            c_rect = QRectF(cur_x, row2_y, cw, chip_h)
            painter.setPen(QPen(QColor(51, 65, 85), 1.0))
            painter.setBrush(QBrush(QColor(30, 41, 59, 210)))
            painter.drawRoundedRect(c_rect, 3 * scale, 3 * scale)

            painter.setPen(QPen(val_col, 1.0))
            painter.drawText(c_rect, Qt.AlignmentFlag.AlignCenter, text)
            cur_x += cw + 6 * scale

    else:
        # === 宽屏标准单行流线型布局 ===
        # 1. 左侧标题与工件名
        painter.setFont(title_font)
        painter.setPen(QPen(QColor(248, 250, 252)))
        painter.drawText(QPointF(pad_left, 26 * scale), "🔬 X-ray AI Inspector")

        painter.setFont(sub_font)
        painter.setPen(QPen(QColor(148, 163, 184)))
        painter.drawText(QPointF(pad_left, 52 * scale), f"工件: {fname}  |  IPC-A-610 工业标准")

        # 2. 右侧指标胶囊 (从右往左流式排布)
        cur_right = width - pad_right

        def _draw_metric_pill(lbl: str, val: str, val_col: QColor) -> float:
            nonlocal cur_right
            p_fm = QFontMetrics(sub_font)
            text = f"{lbl} {val}"
            pw = p_fm.horizontalAdvance(text) + 16 * scale
            ph = 26 * scale
            px = cur_right - pw
            py = (banner_h - ph) / 2.0

            painter.setPen(QPen(QColor(51, 65, 85), 1.0))
            painter.setBrush(QBrush(QColor(30, 41, 59, 210)))
            painter.drawRoundedRect(QRectF(px, py, pw, ph), 4 * scale, 4 * scale)

            painter.setPen(QPen(val_col, 1.0))
            painter.setFont(sub_font)
            painter.drawText(QRectF(px, py, pw, ph), Qt.AlignmentFlag.AlignCenter, text)

            cur_right = px - 8 * scale
            return pw

        if elapsed_ms > 0:
            _draw_metric_pill("耗时", f"{elapsed_ms:.0f}ms", QColor(148, 163, 184))
        _draw_metric_pill("少锡", str(insuff_count), QColor(168, 85, 247) if insuff_count > 0 else QColor(148, 163, 184))
        _draw_metric_pill("桥连", str(bridge_count), QColor(220, 38, 38) if bridge_count > 0 else QColor(148, 163, 184))
        _draw_metric_pill("空洞NG", str(void_ng_count), QColor(255, 208, 0) if void_ng_count > 0 else QColor(148, 163, 184))
        _draw_metric_pill("焊球", str(len(records)), QColor(16, 185, 129))

        # 3. 状态大徽章 (居于中间/统计数据左侧)
        badge_w = 125 * scale
        badge_h = 36 * scale
        badge_y = (banner_h - badge_h) / 2.0
        badge_x = cur_right - badge_w - 14 * scale

        if badge_x > pad_left + 220 * scale:
            b_rect = QRectF(badge_x, badge_y, badge_w, badge_h)
            if is_ng:
                painter.setPen(QPen(QColor(220, 38, 38), 1.6 * scale))
                painter.setBrush(QBrush(QColor(127, 29, 29, 230)))
                b_text = "▲ REJECT 缺陷"
                t_col = QColor(254, 242, 242)
            else:
                painter.setPen(QPen(QColor(16, 185, 129), 1.6 * scale))
                painter.setBrush(QBrush(QColor(6, 78, 59, 230)))
                b_text = "● PASS 合格"
                t_col = QColor(240, 253, 244)

            painter.drawRoundedRect(b_rect, 6 * scale, 6 * scale)
            painter.setFont(status_font)
            painter.setPen(QPen(t_col, 1.0))
            painter.drawText(b_rect, Qt.AlignmentFlag.AlignCenter, b_text)


def _render_bottom_legend(
    painter: QPainter,
    width: int,
    y_start: int,
    legend_h: int,
    scale: float,
):
    """绘制底部工业标准图例栏"""
    rect = QRectF(0, y_start, width, legend_h)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(11, 15, 25)))
    painter.drawRect(rect)

    # 顶部细分割线
    painter.setPen(QPen(QColor(30, 41, 59), 1.0))
    painter.drawLine(0, y_start, width, y_start)

    leg_font = QFont("Microsoft YaHei", max(8, int(8.8 * scale)), QFont.Weight.Normal)
    painter.setFont(leg_font)

    items = [
        ("● 正常焊点 (PASS)", QColor(16, 185, 129)),
        ("● 空洞超标 (NG)", QColor(255, 208, 0)),
        ("■ 桥连短路 (NG)", QColor(220, 38, 38)),
        ("◎ 少锡虚焊 (NG)", QColor(168, 85, 247)),
        ("○ 工艺微气泡", QColor(0, 242, 254)),
    ]

    fm = QFontMetrics(leg_font)
    total_w = sum(fm.horizontalAdvance(t) + 24 * scale for t, _ in items)
    start_x = max(16 * scale, (width - total_w) / 2.0)

    cur_x = start_x
    for text, col in items:
        tw = fm.horizontalAdvance(text)
        painter.setPen(QPen(col, 1.0))
        painter.drawText(QRectF(cur_x, y_start, tw, legend_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        cur_x += tw + 24 * scale
