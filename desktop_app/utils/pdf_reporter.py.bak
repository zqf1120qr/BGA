# -*- coding: utf-8 -*-
"""
BGA 工业级 PDF 质检单报表生成器 (PDF Reporter)
-------------------------------------------------
使用 reportlab 渲染规范的 A4 工业质检报告单：
1. 完整书签目录体系 (PDF Outlines/Bookmarks)：PDF 阅读器侧边栏支持一键定位任意工件，首页总览清单支持点击超链接直达对应页面；
2. 高清全景标注图渲染：仅高亮显示真实缺陷与复核焊点 (合格焊点保持纯净底图)，原图分辨率无损保真，杜绝模糊；
3. 工业级版式规范：整板 PASS / NG 鲜明印章、多维指标卡片、缺陷明细清单与工艺签字栏。
"""
from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

from desktop_app.core.inspection_manager import SolderBallRecord
from desktop_app.utils.defect_renderer import render_defect_only_preview

FONT_NAME = "Helvetica"


from reportlab.platypus.flowables import Flowable


class BookmarkFlowable(Flowable):
    """PDF 书签大纲标记元 (用于在 PDF 左侧目录导航树注册书签项)"""
    def __init__(self, title: str, key: str, level: int = 0):
        super().__init__()
        self.title = title
        self.key = key
        self.level = level
        self.width = 0
        self.height = 0

    def wrap(self, availWidth, availHeight):
        return 0, 0

    def draw(self):
        self.canv.bookmarkPage(self.key)
        self.canv.addOutlineEntry(self.title, self.key, level=self.level, closed=False)


def _ensure_font_registered() -> str:
    """注册中文字体 (Windows 标配黑体/微软雅黑/宋体)，防止乱码"""
    global FONT_NAME
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_candidates = [
        ("SimHei", os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "simhei.ttf")),
        ("MicrosoftYaHei", os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "msyh.ttc")),
        ("SimSun", os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "simsun.ttc")),
    ]
    for fname, fpath in font_candidates:
        if os.path.exists(fpath):
            try:
                pdfmetrics.registerFont(TTFont(fname, fpath))
                FONT_NAME = fname
                return fname
            except Exception:
                continue
    FONT_NAME = "Helvetica"
    return "Helvetica"


def _get_styles(font_name: str):
    """获取/初始化报告段落样式，安全防止多次创建同名样式抛出 KeyError"""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base_styles = getSampleStyleSheet()

    def _get_or_create(name: str, **kwargs) -> ParagraphStyle:
        if name in base_styles:
            s = base_styles[name]
            for k, v in kwargs.items():
                setattr(s, k, v)
            return s
        s = ParagraphStyle(name, **kwargs)
        base_styles.add(s)
        return s

    style_title = _get_or_create(
        "BgaReportTitle",
        fontName=font_name,
        fontSize=18,
        leading=22,
        alignment=1,  # 居中
        textColor=colors.HexColor("#1e3a8a"),
        spaceAfter=10,
    )
    style_subtitle = _get_or_create(
        "BgaReportSubTitle",
        fontName=font_name,
        fontSize=13,
        leading=17,
        alignment=0,  # 居左
        textColor=colors.HexColor("#1e3a8a"),
        spaceBefore=6,
        spaceAfter=8,
    )
    style_h2 = _get_or_create(
        "BgaSectionH2",
        fontName=font_name,
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=8,
        spaceAfter=4,
    )
    style_cell = _get_or_create(
        "BgaCellText",
        fontName=font_name,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
    )
    style_cell_center = _get_or_create(
        "BgaCellCenter",
        fontName=font_name,
        fontSize=9,
        leading=12,
        alignment=1,
        textColor=colors.HexColor("#334155"),
    )
    style_cell_bold = _get_or_create(
        "BgaCellBold",
        fontName=font_name,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#0f172a"),
    )
    style_stamp = _get_or_create(
        "BgaStatusStamp",
        fontName=font_name,
        fontSize=16,
        leading=20,
        alignment=1,
        spaceBefore=4,
        spaceAfter=4,
    )

    return {
        "title": style_title,
        "subtitle": style_subtitle,
        "h2": style_h2,
        "cell": style_cell,
        "cell_center": style_cell_center,
        "cell_bold": style_cell_bold,
        "stamp": style_stamp,
    }


def _build_single_item_flowables(
    image_name: str,
    summary_stats: Dict[str, Any],
    records: List[SolderBallRecord],
    preview_img_path: Optional[str],
    styles: Dict[str, Any],
    font_name: str,
    item_index: Optional[int] = None,
    total_items: Optional[int] = None,
    bookmark_key: Optional[str] = None,
    back_to_overview_key: Optional[str] = None,
) -> list:
    """构建单个工件图像的质检报告页流元素"""
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

    flowables = []

    # 0. 书签锚点
    if bookmark_key:
        if item_index is not None:
            bm_title = f"工件 [{item_index:02d}]: {image_name} ({summary_stats.get('board_status', 'UNKNOWN')})"
        else:
            bm_title = f"工件质检报告: {image_name} ({summary_stats.get('board_status', 'UNKNOWN')})"
        flowables.append(BookmarkFlowable(
            title=bm_title,
            key=bookmark_key,
            level=0,
        ))

    # 1. 标题与返回总览微链接
    if item_index is not None and total_items is not None:
        title_text = f"BGA 工件质检明细单 [{item_index}/{total_items}]: {image_name}"
        flowables.append(Paragraph(title_text, styles["title"]))
        if back_to_overview_key:
            back_link = f"<a href='#{back_to_overview_key}'><font color='#2563eb'>◀ 返回批次检测总览</font></a>"
            flowables.append(Paragraph(back_link, styles["cell"]))
            flowables.append(Spacer(1, 4))
    else:
        flowables.append(Paragraph("BGA 工业检测分析报告单", styles["title"]))

    # 2. 基础信息与整板大判定栏
    board_status = summary_stats.get("board_status", "UNKNOWN")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if board_status.startswith("PASS"):
        status_color = colors.HexColor("#16a34a")
        status_bg = colors.HexColor("#dcfce7")
    elif "PASS (人工复核)" in board_status:
        status_color = colors.HexColor("#0891b2")
        status_bg = colors.HexColor("#cffafe")
    else:
        status_color = colors.HexColor("#dc2626")
        status_bg = colors.HexColor("#fee2e2")

    info_data = [
        [
            Paragraph(f"<b>待测图片:</b> {image_name}", styles["cell"]),
            Paragraph("<b>检测模式:</b> 全项综合检测 (空洞+连锡+虚焊)", styles["cell"]),
            Paragraph("<b>整板最终判定:</b>", styles["cell_bold"]),
        ],
        [
            Paragraph(f"<b>检验时间:</b> {now_str}", styles["cell"]),
            Paragraph(f"<b>检测用时:</b> {float(summary_stats.get('elapsed_ms') or 0.0):.1f} ms", styles["cell"]),
            Paragraph(f"<font color='{status_color.hexval()}'><b>{board_status}</b></font>", styles["stamp"]),
        ],
    ]

    t_info = Table(info_data, colWidths=[6.5 * cm, 7.0 * cm, 4.5 * cm])
    t_info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (2, 0), (2, 1), status_bg),
        ("ALIGN", (2, 0), (2, 1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    flowables.append(t_info)
    flowables.append(Spacer(1, 6))

    # 3. 汇总统计指标表格
    flowables.append(Paragraph("【多维指标统计】", styles["h2"]))
    v_ng = summary_stats.get("void_ng_count", 0)
    b_ng = summary_stats.get("bridge_count", 0)
    i_ng = summary_stats.get("insufficient_count", 0)
    c_rev = summary_stats.get("manual_cleared_count", 0)

    stats_data = [
        ["检测焊球数", "空洞超标", "桥连短路", "虚焊少锡", "排除误检(复核)", "最大空洞比"],
        [
            str(summary_stats.get("total_solders", 0)),
            f"{v_ng} 处" if v_ng > 0 else "0",
            f"{b_ng} 处" if b_ng > 0 else "0",
            f"{i_ng} 处" if i_ng > 0 else "0",
            f"{c_rev} 处" if c_rev > 0 else "0",
            f"{float(summary_stats.get('max_void_rate') or 0.0) * 100:.1f}%",
        ],
    ]
    t_stats = Table(stats_data, colWidths=[3.0 * cm] * 6)
    t_stats.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
    ]))
    flowables.append(t_stats)
    flowables.append(Spacer(1, 6))

    # 4. 嵌入质检全景标注图像 (高清原图保真，仅突出显示缺陷异常)
    img_rendered = False
    if preview_img_path and os.path.exists(preview_img_path):
        try:
            flowables.append(Paragraph("【全景检测标注图 (仅高亮显示异常与复核部位)】", styles["h2"]))
            # 精确根据图像实际分辨率计算等比最佳缩放尺寸
            from PIL import Image as PILImage
            with PILImage.open(preview_img_path) as pil_im:
                pw, ph = pil_im.size
            aspect = float(pw) / float(ph) if ph > 0 else 1.5

            max_w_cm = 16.0
            max_h_cm = 9.2
            if aspect >= (max_w_cm / max_h_cm):
                render_w = max_w_cm * cm
                render_h = (max_w_cm / aspect) * cm
            else:
                render_h = max_h_cm * cm
                render_w = (max_h_cm * aspect) * cm

            img_item = Image(preview_img_path, width=render_w, height=render_h)
            flowables.append(img_item)
            flowables.append(Spacer(1, 4))

            # 🌟 图例条 (直接呈现在 PDF 报表页面中，100% 释放图片原始视野)
            legend_cells = [
                [
                    Paragraph("<font color='#ffd000'><b>●</b></font> 空洞超标", styles["cell"]),
                    Paragraph("<font color='#dc2626'><b>●</b></font> 桥连短路", styles["cell"]),
                    Paragraph("<font color='#a855f7'><b>●</b></font> 虚焊少锡", styles["cell"]),
                    Paragraph("<font color='#06b6d4'><b>●</b></font> 人工排除", styles["cell"]),
                    Paragraph("<font color='#10b981'><b>○</b></font> 正常合格(底图零遮挡)", styles["cell"]),
                ]
            ]
            t_leg = Table(legend_cells, colWidths=[3.2 * cm, 3.2 * cm, 3.2 * cm, 3.2 * cm, 5.2 * cm])
            t_leg.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            flowables.append(t_leg)
            flowables.append(Spacer(1, 6))
            img_rendered = True
        except Exception as e:
            print(f"[WARN] 无法嵌入 PDF 图像 {preview_img_path}: {e}")

    # 5. 缺陷明细表 (包含 AI 检出异常与人工复核审计结果，完整呈现绝无遗漏)
    flowables.append(Paragraph("【不良与复核焊点明细清单】", styles["h2"]))
    defect_records = [r for r in records if r.is_ng or r.is_manually_reviewed]

    if defect_records:
        defect_data = [["序号", "中心坐标(X, Y)", "空洞占比", "少锡缩减", "桥连短路", "初始原因", "最终结论"]]
        # 完整输出所有缺陷与复核记录 (极端超出 150 条才启动保护)
        max_show = 150
        records_to_show = defect_records[:max_show]
        for r in records_to_show:
            is_rev = (r.is_manually_reviewed and r.manual_status == "PASS")
            concl = "已排除误检(PASS)" if is_rev else "NG 不良"
            rcx = float(r.cx) if r.cx is not None else 0.0
            rcy = float(r.cy) if r.cy is not None else 0.0
            r_void = float(r.void_rate) if r.void_rate is not None else 0.0
            r_reduct = float(r.reduction_percent) if r.reduction_percent is not None else 0.0
            defect_data.append([
                f"#{r.index}",
                f"({rcx:.1f}, {rcy:.1f})",
                f"{r_void * 100:.1f}%",
                f"-{r_reduct:.1f}%" if r_reduct > 0 else "0.0%",
                "桥连短路NG" if r.is_bridge else "正常",
                ", ".join(r.ng_reasons) if r.ng_reasons else "异常",
                concl,
            ])
        # repeatRows=1：当表格跨页时，新页面顶部自动重新打印表头，格式整洁
        t_defect = Table(
            defect_data,
            colWidths=[1.6 * cm, 2.8 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm, 4.0 * cm, 3.0 * cm],
            repeatRows=1,
        )
        t_defect_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#475569")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ]
        for row_i, r in enumerate(records_to_show, start=1):
            if r.is_manually_reviewed and r.manual_status == "PASS":
                t_defect_style.append(("BACKGROUND", (0, row_i), (-1, row_i), colors.HexColor("#cffafe")))
            else:
                t_defect_style.append(("BACKGROUND", (0, row_i), (-1, row_i), colors.HexColor("#fff1f2")))

        t_defect.setStyle(TableStyle(t_defect_style))
        flowables.append(t_defect)

        if len(defect_records) > max_show:
            flowables.append(Spacer(1, 4))
            flowables.append(Paragraph(
                f"<font color='#64748b'><i>(注：当前工件共检出 {len(defect_records)} 处不良/复核焊点，上述已列出前 {max_show} 项，完整海量数据请查阅配套 Excel 报表)</i></font>",
                styles["cell"]
            ))
    else:
        flowables.append(Paragraph("<font color='#16a34a'><b>全板未检出任何空洞、桥连或少锡缺陷，整板符合工业质量标准。</b></font>", styles["cell_bold"]))

    flowables.append(Spacer(1, 8))

    # 6. 底部签字栏
    sign_data = [
        [
            Paragraph("<b>品质检验员 (Inspector):</b> ________________", styles["cell"]),
            Paragraph("<b>人工复核员 (Reviewer):</b> ________________", styles["cell"]),
            Paragraph("<b>审核日期 (Date):</b> ____年__月__日", styles["cell"]),
        ]
    ]
    t_sign = Table(sign_data, colWidths=[6.0 * cm, 6.0 * cm, 6.0 * cm])
    t_sign.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    flowables.append(t_sign)

    return flowables


def export_inspection_pdf(
    save_path: str,
    image_name: str,
    summary_stats: Dict[str, Any],
    records: List[SolderBallRecord],
    preview_img_path: str | None = None,
    image_path: str | None = None,
    bridge_defects: List[Dict[str, Any]] | None = None,
):
    """单张图像质检报告导出为 PDF (含书签目录与高清纯缺陷图)"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate

    font_name = _ensure_font_registered()
    styles = _get_styles(font_name)

    doc = SimpleDocTemplate(
        save_path,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    # 自动渲染纯缺陷高清标注图 (若未提供或需保证高清)
    actual_preview = preview_img_path
    target_img = image_path or preview_img_path
    if target_img and os.path.exists(target_img):
        try:
            actual_preview = render_defect_only_preview(
                image_path=target_img,
                records=records,
                bridge_defects=bridge_defects or [],
            )
        except Exception as e:
            print(f"[WARN] 渲染单图纯缺陷标注图失败: {e}")

    story = _build_single_item_flowables(
        image_name=image_name,
        summary_stats=summary_stats,
        records=records,
        preview_img_path=actual_preview,
        styles=styles,
        font_name=font_name,
        bookmark_key="bga_single_overview",
    )

    doc.build(story, onFirstPage=lambda c, d: c.showOutline())


def export_batch_inspection_pdf(
    save_path: str,
    batch_items: List[Dict[str, Any]],
    batch_summary: Optional[Dict[str, Any]] = None,
):
    """
    批量检测结果合并导出至单一 PDF 文件 (含书签大纲树 + 内部锚点跳转):
    - 首页/总览: [批次综合质检分析报告] (包含批次大印章、总览书签、表格点击跳转工件链接)
    - 后续各页: 每一个工件独立的 [工件质检明细单] (包含书签导航项、高清纯缺陷标注图、返回总览链接)
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font_name = _ensure_font_registered()
    styles = _get_styles(font_name)

    doc = SimpleDocTemplate(
        save_path,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    story = []

    # 1. 计算批次整体指标
    total_boards = len(batch_items)
    pass_boards = sum(1 for item in batch_items if str(item.get("summary_stats", {}).get("board_status", "")).startswith("PASS"))
    ng_boards = total_boards - pass_boards
    pass_rate = (pass_boards / total_boards * 100.0) if total_boards > 0 else 0.0

    total_solders = sum(item.get("summary_stats", {}).get("total_solders", 0) for item in batch_items)
    total_void_ng = sum(item.get("summary_stats", {}).get("void_ng_count", 0) for item in batch_items)
    total_bridge = sum(item.get("summary_stats", {}).get("bridge_count", 0) for item in batch_items)
    total_insuff = sum(item.get("summary_stats", {}).get("insufficient_count", 0) for item in batch_items)
    total_cleared = sum(item.get("summary_stats", {}).get("manual_cleared_count", 0) for item in batch_items)
    total_elapsed = sum(item.get("summary_stats", {}).get("elapsed_ms", 0.0) for item in batch_items)
    avg_elapsed = (total_elapsed / total_boards) if total_boards > 0 else 0.0

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ==============================================================
    # 🌟 批次综合总览页 (Batch Executive Overview)
    # ==============================================================
    overview_key = "bga_batch_overview"
    story.append(BookmarkFlowable(title="【批次质检总览】", key=overview_key, level=0))
    story.append(Paragraph("BGA 批量工业检测综合分析报告", styles["title"]))

    # 批次基础概况大印章栏
    is_batch_pass = (ng_boards == 0)
    stamp_text = "PASS 全部合格" if is_batch_pass else f"NG 检出缺陷 ({ng_boards}片)"
    status_color = colors.HexColor("#16a34a") if is_batch_pass else colors.HexColor("#dc2626")
    status_bg = colors.HexColor("#dcfce7") if is_batch_pass else colors.HexColor("#fee2e2")

    overview_info = [
        [
            Paragraph("<b>检验批次:</b> 全量批量检测队列", styles["cell"]),
            Paragraph(f"<b>报告生成时间:</b> {now_str}", styles["cell"]),
            Paragraph("<b>批次综合判定:</b>", styles["cell_bold"]),
        ],
        [
            Paragraph(f"<b>工件总数:</b> {total_boards} 片 (合格 {pass_boards} / 不良 {ng_boards})", styles["cell"]),
            Paragraph(f"<b>批次综合合格率:</b> <b>{pass_rate:.1f}%</b> (总耗时: {total_elapsed:.0f} ms)", styles["cell"]),
            Paragraph(f"<font color='{status_color.hexval()}'><b>{stamp_text}</b></font>", styles["stamp"]),
        ],
    ]
    t_overview = Table(overview_info, colWidths=[6.5 * cm, 7.0 * cm, 4.5 * cm])
    t_overview.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (2, 0), (2, 1), status_bg),
        ("ALIGN", (2, 0), (2, 1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t_overview)
    story.append(Spacer(1, 10))

    # 批次缺陷多维汇总表格
    story.append(Paragraph("【批次多维缺陷聚合统计】", styles["h2"]))
    batch_metrics = [
        ["受检焊球总数", "空洞超标总数", "桥连短路总数", "虚焊少锡总数", "人工排除误检", "平均单片耗时"],
        [
            str(total_solders),
            f"{total_void_ng} 处" if total_void_ng > 0 else "0",
            f"{total_bridge} 对" if total_bridge > 0 else "0",
            f"{total_insuff} 处" if total_insuff > 0 else "0",
            f"{total_cleared} 处" if total_cleared > 0 else "0",
            f"{avg_elapsed:.1f} ms",
        ],
    ]
    t_batch_metrics = Table(batch_metrics, colWidths=[3.0 * cm] * 6)
    t_batch_metrics.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
    ]))
    story.append(t_batch_metrics)
    story.append(Spacer(1, 10))

    # 批次工件质检清单总表 (包含内部点击跳转超链接)
    story.append(Paragraph("【批次工件质检清单列表 (点击工件名称可直接跳至明细页)】", styles["h2"]))
    item_table_data = [
        ["序号", "工件图片名称 (点击跳转)", "焊点数", "空洞NG", "桥连短路", "虚焊少锡", "人工排除", "最终判定"]
    ]
    item_table_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#475569")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
    ]

    for idx, item in enumerate(batch_items, start=1):
        stats = item.get("summary_stats", {})
        img_name = item.get("image_name") or os.path.basename(item.get("image_path", f"item_{idx}"))
        b_status = stats.get("board_status", "UNKNOWN")
        is_p = str(b_status).startswith("PASS")
        item_anchor = f"bga_item_{idx}"

        # 内部超链接至该工件的单页
        linked_name = Paragraph(f"<a href='#{item_anchor}'><font color='#1e3a8a'><b>{img_name} ➜</b></font></a>", styles["cell"])

        item_table_data.append([
            f"#{idx}",
            linked_name,
            str(stats.get("total_solders", 0)),
            str(stats.get("void_ng_count", 0)),
            str(stats.get("bridge_count", 0)),
            str(stats.get("insufficient_count", 0)),
            str(stats.get("manual_cleared_count", 0)),
            b_status,
        ])
        row_bg = colors.HexColor("#dcfce7") if is_p else colors.HexColor("#fee2e2")
        item_table_styles.append(("BACKGROUND", (7, idx), (7, idx), row_bg))

    t_item_list = Table(item_table_data, colWidths=[1.5 * cm, 5.5 * cm, 2.0 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm, 2.0 * cm])
    t_item_list.setStyle(TableStyle(item_table_styles))
    story.append(t_item_list)
    story.append(Spacer(1, 10))

    # 批次总览签字栏
    batch_sign_data = [
        [
            Paragraph("<b>品质主管 (QA Manager):</b> ________________", styles["cell"]),
            Paragraph("<b>工艺工程师 (Process Eng):</b> ________________", styles["cell"]),
            Paragraph("<b>批次检验日期:</b> ____年__月__日", styles["cell"]),
        ]
    ]
    t_bsign = Table(batch_sign_data, colWidths=[6.0 * cm, 6.0 * cm, 6.0 * cm])
    t_bsign.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t_bsign)

    # ==============================================================
    # 🌟 各工件独立质检单页 (每张工件独立一页 + 独立书签项 + 高清缺陷图)
    # ==============================================================
    for idx, item in enumerate(batch_items, start=1):
        story.append(PageBreak())  # 开启工件专属页
        img_name = item.get("image_name") or os.path.basename(item.get("image_path", f"item_{idx}"))
        stats = item.get("summary_stats", {})
        records = item.get("records", [])
        preview_path = item.get("preview_img_path")
        orig_img_path = item.get("image_path")
        bridge_defects = item.get("bridge_defects", [])

        # 确保使用高清纯缺陷渲染标注图
        actual_preview = preview_path
        if (orig_img_path and os.path.exists(orig_img_path)) or (preview_path and os.path.exists(preview_path)):
            target_to_render = orig_img_path if (orig_img_path and os.path.exists(orig_img_path)) else preview_path
            try:
                actual_preview = render_defect_only_preview(
                    image_path=target_to_render,
                    records=records,
                    bridge_defects=bridge_defects,
                )
            except Exception as e:
                print(f"[WARN] 批量渲染工件 #{idx} 纯缺陷图失败: {e}")

        item_flowables = _build_single_item_flowables(
            image_name=img_name,
            summary_stats=stats,
            records=records,
            preview_img_path=actual_preview,
            styles=styles,
            font_name=font_name,
            item_index=idx,
            total_items=total_boards,
            bookmark_key=f"bga_item_{idx}",
            back_to_overview_key=overview_key,
        )
        story.extend(item_flowables)

    doc.build(story, onFirstPage=lambda c, d: c.showOutline())
