# -*- coding: utf-8 -*-
"""
🌟 BGA 工业级 PDF 质检单报表生成器 (PDF Reporter)
-------------------------------------------------
使用 reportlab 渲染规范的 A4 工业质检报告单：
1. 包含工单标题、检测时间与整板 PASS / NG 鲜明大印章；
2. 包含指标汇总卡片、检测参数；
3. 嵌入质检全景标注图像；
4. 罗列所有异常缺陷明细清单；
5. 提供品质检验员与工艺主管签字栏。
"""
from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List

from desktop_app.core.inspection_manager import SolderBallRecord

FONT_NAME = "SimHei"


def export_inspection_pdf(
    save_path: str,
    image_name: str,
    summary_stats: Dict[str, Any],
    records: List[SolderBallRecord],
    preview_img_path: str | None = None,
):
    global FONT_NAME
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm, inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Image,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    # 注册中文字体 (Windows 标配黑体)
    font_path = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "simhei.ttf")
    if os.path.exists(font_path):
        try:
            pdfmetrics.registerFont(TTFont("SimHei", font_path))
            FONT_NAME = "SimHei"
        except Exception:
            FONT_NAME = "Helvetica"
    else:
        FONT_NAME = "Helvetica"
    doc = SimpleDocTemplate(
        save_path,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    story = []
    styles = getSampleStyleSheet()

    # 样式
    style_title = ParagraphStyle(
        "ReportTitle",
        fontName=FONT_NAME,
        fontSize=18,
        leading=22,
        alignment=1, # 居中
        textColor=colors.HexColor("#1e3a8a"),
        spaceAfter=12,
    )
    style_h2 = ParagraphStyle(
        "SectionH2",
        fontName=FONT_NAME,
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=10,
        spaceAfter=6,
    )
    style_cell = ParagraphStyle(
        "CellText",
        fontName=FONT_NAME,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
    )
    style_cell_bold = ParagraphStyle(
        "CellBold",
        fontName=FONT_NAME,
        fontSize=9,
        leading=12,
        fontNameBold=FONT_NAME,
        textColor=colors.HexColor("#0f172a"),
    )

    # 1. 主标题
    story.append(Paragraph("BGA 工业检测分析报告单", style_title))

    # 2. 基础信息与整板大判定栏
    board_status = summary_stats.get("board_status", "UNKNOWN")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    status_color = colors.HexColor("#16a34a") if board_status == "PASS" else colors.HexColor("#dc2626")
    status_bg = colors.HexColor("#dcfce7") if board_status == "PASS" else colors.HexColor("#fee2e2")

    info_data = [
        [
            Paragraph(f"<b>待测图片:</b> {image_name}", style_cell),
            Paragraph(f"<b>检测模式:</b> 全项综合检测 (气泡+连锡+虚焊)", style_cell),
            Paragraph(f"<b>整板最终判定:</b>", style_cell_bold),
        ],
        [
            Paragraph(f"<b>检验时间:</b> {now_str}", style_cell),
            Paragraph(f"<b>检测用时:</b> {summary_stats.get('elapsed_ms', 0.0):.1f} ms", style_cell),
            Paragraph(f"<font color='{status_color.hexval()}'><b>{board_status}</b></font>", style_title),
        ],
    ]

    t_info = Table(info_data, colWidths=[6.5 * cm, 7.0 * cm, 4.5 * cm])
    t_info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (2, 0), (2, 1), status_bg),
        ("ALIGN", (2, 1), (2, 1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t_info)
    story.append(Spacer(1, 10))

    # 3. 汇总统计指标表格
    story.append(Paragraph("【多维指标统计】", style_h2))
    v_ng = summary_stats.get("void_ng_count", 0)
    b_ng = summary_stats.get("bridge_count", 0)
    i_ng = summary_stats.get("insufficient_count", 0)

    stats_data = [
        ["检测焊球总数", "气泡超标焊点", "桥连短路对数", "虚焊少锡焊点", "最大气泡占比", "最大少锡缩减率"],
        [
            str(summary_stats.get("total_solders", 0)),
            f"{v_ng} 处" if v_ng > 0 else "0 (合格)",
            f"{b_ng} 处" if b_ng > 0 else "0 (合格)",
            f"{i_ng} 处" if i_ng > 0 else "0 (合格)",
            f"{summary_stats.get('max_void_rate', 0.0) * 100:.1f}%",
            f"-{summary_stats.get('max_reduction_percent', 0.0):.1f}%",
        ],
    ]
    t_stats = Table(stats_data, colWidths=[3.0 * cm] * 6)
    t_stats.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
    ]))
    story.append(t_stats)
    story.append(Spacer(1, 10))

    # 4. 嵌入质检全景标注图像 (若存在)
    if preview_img_path and os.path.exists(preview_img_path):
        story.append(Paragraph("【全景检测标注图】", style_h2))
        try:
            # 缩放到合适尺寸
            img_item = Image(preview_img_path, width=15 * cm, height=9 * cm, kind="proportional")
            story.append(img_item)
            story.append(Spacer(1, 10))
        except Exception as e:
            print(f"[WARN] 无法嵌入 PDF 图像: {e}")

    # 5. 缺陷明细表 (仅展示 NG 异常项)
    story.append(Paragraph("【不良焊点明细清单 (NG List)】", style_h2))
    defect_records = [r for r in records if r.is_ng]
    
    if defect_records:
        defect_data = [["序号", "中心坐标(X, Y)", "气泡占比", "少锡缩减率", "桥连短路", "不良原因"]]
        for r in defect_records[:25]:  # 最多展示前25项
            defect_data.append([
                f"#{r.index}",
                f"({r.cx:.1f}, {r.cy:.1f})",
                f"{r.void_rate * 100:.1f}%",
                f"-{r.reduction_percent:.1f}%" if r.reduction_percent > 0 else "0.0%",
                "桥连短路NG" if r.is_bridge else "正常",
                ", ".join(r.ng_reasons) if r.ng_reasons else "异常",
            ])
        t_defect = Table(defect_data, colWidths=[1.8 * cm, 3.2 * cm, 2.5 * cm, 2.5 * cm, 2.2 * cm, 5.8 * cm])
        t_defect.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#475569")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fff1f2")), # 淡红色背景
        ]))
        story.append(t_defect)
    else:
        story.append(Paragraph("<font color='#16a34a'><b>全板未检出任何气泡、桥连或少锡缺陷，整板符合工业质量标准。</b></font>", style_cell_bold))

    story.append(Spacer(1, 15))

    # 6. 底部签字栏
    sign_data = [
        [
            Paragraph("<b>品质检验员 (Inspector):</b> ________________", style_cell),
            Paragraph("<b>工艺工程师 (Engineer):</b> ________________", style_cell),
            Paragraph("<b>审核日期 (Date):</b> ____年__月__日", style_cell),
        ]
    ]
    t_sign = Table(sign_data, colWidths=[6.0 * cm, 6.0 * cm, 6.0 * cm])
    t_sign.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(t_sign)

    doc.build(story)
