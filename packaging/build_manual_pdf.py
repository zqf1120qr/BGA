# -*- coding: utf-8 -*-
"""
X射线智能工业质检工作站 - 用户操作与部署手册 PDF 生成器
----------------------------------------------------------------
功能：
- 将 docs/用户操作与部署手册.md 渲染为高颜值企业级 A4 PDF 文档；
- 独立矢量渲染（基于 ReportLab + 微软雅黑中文字体），零浏览器/外部工具依赖；
- 支持 PDF 侧边栏章节书签（一级章节 + 二级小节）及目录页内部点击跳转；
- 封面独占一页、目录独占一页、正文每一章自动新起一页；
- 4.1 主界面功能分区采用矢量合并单元格布局图，彻底消除字符对齐错位。
"""
from __future__ import annotations

import os
import re
import sys
from html import escape
from pathlib import Path
from typing import List, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# 保证 UTF-8 控制台输出
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MD_PATH = PROJECT_ROOT / "docs" / "用户操作与部署手册.md"
DEFAULT_PDF_PATH = PROJECT_ROOT / "docs" / "用户操作与部署手册.pdf"

# 视觉配色方案
COLOR_NAVY = colors.HexColor("#0f172a")       # 深海蓝（封面/主标题/表头）
COLOR_PRIMARY = colors.HexColor("#0284c7")    # 工业科技蓝（强调线/二级标题）
COLOR_TEXT = colors.HexColor("#1e293b")       # 正文深灰
COLOR_MUTED = colors.HexColor("#64748b")      # 页眉页脚次级灰
COLOR_BORDER = colors.HexColor("#cbd5e1")     # 表格细边框
COLOR_ZEBRA = colors.HexColor("#f8fafc")      # 表格斑马纹底色
COLOR_CODE_BG = colors.HexColor("#f1f5f9")    # 代码块底色
COLOR_QUOTE_BG = colors.HexColor("#eff6ff")   # 提示框底色
COLOR_QUOTE_BAR = colors.HexColor("#2563eb")  # 提示框左边框


class ManualDocTemplate(SimpleDocTemplate):
    """支持自动生成 PDF 章节书签（Outlines）的自定义文档模板"""

    def afterFlowable(self, flowable):
        bm_key = getattr(flowable, "_bookmark_key", None)
        bm_title = getattr(flowable, "_bookmark_title", None)
        bm_level = getattr(flowable, "_bookmark_level", None)
        if bm_key and bm_title is not None and bm_level is not None:
            self.canv.bookmarkPage(bm_key)
            self.canv.addOutlineEntry(bm_title, bm_key, level=int(bm_level), closed=False)


def _register_fonts() -> Tuple[str, str]:
    """注册 Windows 中文字体（微软雅黑常规 + 粗体，回退黑体/宋体）"""
    candidates_reg = [
        ("MSYH", r"C:\Windows\Fonts\msyh.ttc", 0),
        ("SimHei", r"C:\Windows\Fonts\simhei.ttf", None),
        ("SimSun", r"C:\Windows\Fonts\simsun.ttc", 0),
    ]
    candidates_bold = [
        ("MSYH-Bold", r"C:\Windows\Fonts\msyhbd.ttc", 0),
        ("SimHei", r"C:\Windows\Fonts\simhei.ttf", None),
    ]

    reg_name = "Helvetica"
    for name, path, sub_idx in candidates_reg:
        if os.path.exists(path):
            if name not in pdfmetrics.getRegisteredFontNames():
                if sub_idx is not None:
                    pdfmetrics.registerFont(TTFont(name, path, subfontIndex=sub_idx))
                else:
                    pdfmetrics.registerFont(TTFont(name, path))
            reg_name = name
            break

    bold_name = reg_name
    for name, path, sub_idx in candidates_bold:
        if os.path.exists(path):
            if name not in pdfmetrics.getRegisteredFontNames():
                if sub_idx is not None:
                    pdfmetrics.registerFont(TTFont(name, path, subfontIndex=sub_idx))
                else:
                    pdfmetrics.registerFont(TTFont(name, path))
            bold_name = name
            break

    try:
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        registerFontFamily(
            reg_name,
            normal=reg_name,
            bold=bold_name,
            italic=reg_name,
            boldItalic=bold_name,
        )
    except Exception:
        pass

    return reg_name, bold_name


def _plain_title(text: str) -> str:
    """去除标题中的 Markdown 符号，用于生成清爽的 PDF 书签标题"""
    t = re.sub(r"`([^`]+)`", r"\1", text)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    return t.strip()


def _format_inline_md(text: str, bold_font: str) -> str:
    """将行内 Markdown（加粗、行内代码、链接、色值标签）转为 ReportLab XML 标记"""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = escape(text)
    code_tokens: List[str] = []

    def _repl_code(m: re.Match) -> str:
        raw = m.group(1)
        if re.fullmatch(r"#[0-9a-fA-F]{6}", raw):
            token = (
                f'<font color="{raw}">●</font> '
                f'<font backColor="#e2e8f0" color="#0f172a"> {raw} </font>'
            )
        else:
            token = f'<font backColor="#e2e8f0" color="#0369a1"> {raw} </font>'
        code_tokens.append(token)
        return f"@@CODE{len(code_tokens) - 1}@@"

    text = re.sub(r"`([^`]+)`", _repl_code, text)
    text = re.sub(r"\*\*([^*]+)\*\*", rf'<font name="{bold_font}">\1</font>', text)
    text = text.replace("☐", "□")

    for idx, tok in enumerate(code_tokens):
        text = text.replace(f"@@CODE{idx}@@", tok)

    return text


def _estimate_display_len(s: str) -> float:
    """估算单元格文本视觉宽度（中文计 2，ASCII 计 1）"""
    clean = re.sub(r"\*\*|`|\[([^\]]+)\]\([^)]+\)", lambda m: m.group(1) if m.lastindex else "", s)
    w = 0.0
    for ch in clean:
        w += 2.0 if ord(ch) > 127 else 1.0
    return max(w, 4.0)


def _build_table(
    rows_raw: List[List[str]],
    avail_w: float,
    reg_font: str,
    bold_font: str,
) -> Table:
    """构建带自适应列宽、深蓝表头与斑马纹的表格"""
    ncols = max(len(r) for r in rows_raw)
    norm_rows = [r + [""] * (ncols - len(r)) for r in rows_raw]

    col_weights = []
    for c in range(ncols):
        col_cells = [r[c] for r in norm_rows]
        lens = sorted(_estimate_display_len(s) for s in col_cells)
        w_val = max(lens[0], lens[int(0.85 * (len(lens) - 1))])
        max_token = 0.0
        for s in col_cells:
            for tok in re.findall(r"[A-Za-z0-9_#.\-]+", s):
                extra = 3.0 if tok.startswith("#") else 1.2
                max_token = max(max_token, len(tok) + extra)
        w_val = max(w_val, max_token * 1.15)
        col_weights.append(min(max(w_val, 8.0), 54.0))

    total_w = sum(col_weights) or 1.0
    col_widths = [avail_w * (w / total_w) for w in col_weights]

    th_style = ParagraphStyle(
        "TH",
        fontName=bold_font,
        fontSize=9.0,
        leading=13.0,
        textColor=colors.white,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )
    td_style = ParagraphStyle(
        "TD",
        fontName=reg_font,
        fontSize=8.5,
        leading=13.0,
        textColor=COLOR_TEXT,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )
    td_center = ParagraphStyle("TDC", parent=td_style, alignment=TA_CENTER)

    table_data = []
    for r_idx, row in enumerate(norm_rows):
        p_row = []
        for cell in row:
            cell_s = cell.strip()
            xml = _format_inline_md(cell_s, bold_font)
            if r_idx == 0:
                p_row.append(Paragraph(xml, th_style))
            elif cell_s in ("☐", "□", "✓", "√"):
                p_row.append(Paragraph(xml, td_center))
            else:
                p_row.append(Paragraph(xml, td_style))
        table_data.append(p_row)

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, COLOR_BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, COLOR_PRIMARY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for r_idx in range(1, len(table_data)):
        if r_idx % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, r_idx), (-1, r_idx), COLOR_ZEBRA))
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def _build_ui_layout_diagram(avail_w: float, reg_font: str, bold_font: str) -> Table:
    """用矢量合并单元格精准绘制 4.1 主界面功能分区示意图，彻底避免字符错位"""
    s_bar_title = ParagraphStyle(
        "UIBarTitle", fontName=bold_font, fontSize=8.5, leading=12.5, textColor=colors.white
    )
    s_panel_hdr = ParagraphStyle(
        "UIPanelHdr", fontName=bold_font, fontSize=8.6, leading=13.0, textColor=COLOR_NAVY
    )
    s_panel_item = ParagraphStyle(
        "UIPanelItem", fontName=reg_font, fontSize=8.2, leading=13.0, textColor=COLOR_TEXT
    )
    s_strip_dark = ParagraphStyle(
        "UIStripDark", fontName=reg_font, fontSize=8.2, leading=12.5, textColor=COLOR_NAVY
    )
    s_status = ParagraphStyle(
        "UIStatus", fontName=reg_font, fontSize=8.0, leading=12.0, textColor=colors.HexColor("#e2e8f0")
    )

    col_w = [avail_w * 0.25, avail_w * 0.46, avail_w * 0.29]

    top_bar = Paragraph(
        f'<font name="{bold_font}">顶部自定义标题栏</font>　|　产品标识 · 视口模式与透明度 · 适应窗口 / 1:1 / 放大 / 缩小 / 恢复标注 · 窗口控制',
        s_bar_title,
    )
    left_panel = Paragraph(
        f'<font name="{bold_font}" color="#0284c7">左侧控制面板</font><br/>'
        '• 打开单张图片<br/>'
        '• 批量检测目录<br/>'
        '• 框选局部区域 (ROI)<br/>'
        '• 开始 / 终止质检任务<br/>'
        '• 导出 PDF / Excel 报表',
        s_panel_item,
    )
    center_panel = Paragraph(
        f'<font name="{bold_font}" color="#0284c7">中央高清交互视口</font><br/>'
        '• 矢量抗锯齿高清渲染画布<br/>'
        '• 滚轮焦点缩放 / 拖拽无级漫游<br/>'
        '• 焊球悬停微探针悬浮卡 (Hover HUD)<br/>'
        '• 长按 Space 空格键瞬时原图透视对比<br/>'
        '• R 键快捷切换人工复核状态',
        s_panel_item,
    )
    right_panel = Paragraph(
        f'<font name="{bold_font}" color="#0284c7">右侧质检与参数面板</font><br/>'
        '• 检测模式与阈值调谐<br/>'
        '• 配方保存 / 恢复 / 导入导出<br/>'
        '• 整板 PASS / NG 结论卡<br/>'
        '• 缺陷分类统计仪表盘<br/>'
        '• 缺陷焊球明细定位表',
        s_panel_item,
    )
    thumb_bar = Paragraph(
        f'<font name="{bold_font}" color="#0f172a">底部批量缩略图栏</font>　|　多图队列快速预览与 PASS / NG 状态角标（支持 ← / → 方向键极速切图）',
        s_strip_dark,
    )
    status_bar = Paragraph(
        f'<font name="{bold_font}">底部状态栏</font>　|　实时操作提示　·　当前缩放比例　·　硬件加速引擎状态徽章（GPU / CPU）',
        s_status,
    )

    data = [
        [top_bar, "", ""],
        [left_panel, center_panel, right_panel],
        [thumb_bar, "", ""],
        [status_bar, "", ""],
    ]
    tbl = Table(data, colWidths=col_w)
    tbl.setStyle(TableStyle([
        ("SPAN", (0, 0), (2, 0)),
        ("SPAN", (0, 2), (2, 2)),
        ("SPAN", (0, 3), (2, 3)),
        ("BACKGROUND", (0, 0), (2, 0), COLOR_NAVY),
        ("BACKGROUND", (0, 1), (0, 1), colors.HexColor("#f8fafc")),
        ("BACKGROUND", (1, 1), (1, 1), colors.white),
        ("BACKGROUND", (2, 1), (2, 1), colors.HexColor("#f8fafc")),
        ("BACKGROUND", (0, 2), (2, 2), colors.HexColor("#e0f2fe")),
        ("BACKGROUND", (0, 3), (2, 3), colors.HexColor("#1e293b")),
        ("BOX", (0, 0), (-1, -1), 1.0, COLOR_NAVY),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return tbl


def _build_code_block(code_lines: List[str], avail_w: float, reg_font: str) -> Table:
    """构建带浅灰底纹与左侧蓝条的代码/命令行区块"""
    code_style = ParagraphStyle(
        "CodeBlock",
        fontName=reg_font,
        fontSize=8.0,
        leading=12.0,
        textColor=COLOR_NAVY,
        alignment=TA_LEFT,
    )
    rendered_lines = []
    for ln in code_lines:
        esc = escape(ln.rstrip("\r\n"))
        esc = esc.replace(" ", "&nbsp;")
        rendered_lines.append(esc if esc else "&nbsp;")
    html_code = "<br/>".join(rendered_lines)
    tbl = Table([[Paragraph(html_code, code_style)]], colWidths=[avail_w])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_CODE_BG),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, COLOR_PRIMARY),
        ("BOX", (0, 0), (-1, -1), 0.3, COLOR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return tbl


def _build_quote_block(quote_lines: List[str], avail_w: float, reg_font: str, bold_font: str) -> Table:
    """构建带淡蓝底纹与左侧深蓝竖条的提示框"""
    q_style = ParagraphStyle(
        "QuoteBlock",
        fontName=reg_font,
        fontSize=8.6,
        leading=13.2,
        textColor=COLOR_TEXT,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )
    html_q = "<br/>".join(_format_inline_md(ln, bold_font) for ln in quote_lines)
    tbl = Table([[Paragraph(html_q, q_style)]], colWidths=[avail_w])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_QUOTE_BG),
        ("LINEBEFORE", (0, 0), (0, -1), 3.0, COLOR_QUOTE_BAR),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return tbl


def _build_h2_banner(
    title_text: str,
    avail_w: float,
    bold_font: str,
    bookmark_key: str,
) -> Table:
    """构建带左侧科技蓝竖条的一级章节标题栏，并挂载 PDF 书签"""
    h2_style = ParagraphStyle(
        "H2Banner",
        fontName=bold_font,
        fontSize=13.0,
        leading=18.0,
        textColor=COLOR_NAVY,
        keepWithNext=True,
    )
    anchor_html = f'<a name="{bookmark_key}"/>{_format_inline_md(title_text, bold_font)}'
    tbl = Table([[Paragraph(anchor_html, h2_style)]], colWidths=[avail_w])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f9ff")),
        ("LINEBEFORE", (0, 0), (0, -1), 3.5, COLOR_PRIMARY),
        ("LINEBELOW", (0, 0), (-1, -1), 0.6, colors.HexColor("#bae6fd")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    tbl.keepWithNext = True
    tbl._bookmark_key = bookmark_key
    tbl._bookmark_title = _plain_title(title_text)
    tbl._bookmark_level = 0
    return tbl


def build_manual_pdf(
    md_path: Path | str = DEFAULT_MD_PATH,
    pdf_path: Path | str = DEFAULT_PDF_PATH,
) -> Path:
    """将 Markdown 操作手册转换为带章节书签的企业级交付 PDF"""
    md_path = Path(md_path)
    pdf_path = Path(pdf_path)
    if not md_path.exists():
        raise FileNotFoundError(f"未找到 Markdown 手册源文件: {md_path}")

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    reg_font, bold_font = _register_fonts()

    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    page_w, page_h = A4
    margin_x = 18 * mm
    margin_top = 20 * mm
    margin_bottom = 17 * mm
    avail_w = page_w - 2 * margin_x

    # 样式定义（统一启用 wordWrap="CJK"，确保中英混排满行自动折行，不在英文词后留下大段空白）
    style_body = ParagraphStyle(
        "Body",
        fontName=reg_font,
        fontSize=9.2,
        leading=14.8,
        textColor=COLOR_TEXT,
        spaceAfter=4,
        wordWrap="CJK",
    )
    style_bullet = ParagraphStyle(
        "Bullet",
        parent=style_body,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=3,
        wordWrap="CJK",
    )
    style_toc_item = ParagraphStyle(
        "TocItem",
        fontName=reg_font,
        fontSize=10.5,
        leading=22.0,
        textColor=COLOR_NAVY,
        leftIndent=6,
        wordWrap="CJK",
    )
    style_h3 = ParagraphStyle(
        "H3",
        fontName=bold_font,
        fontSize=10.6,
        leading=15.0,
        textColor=COLOR_PRIMARY,
        spaceBefore=7,
        spaceAfter=3,
        keepWithNext=True,
        wordWrap="CJK",
    )

    # 提取文档顶部标题与元数据表用于封面页
    cover_title = "X射线智能工业质检工作站（X-ray AI Inspector）"
    cover_subtitle = "用户操作与部署手册"
    meta_rows: List[List[str]] = []

    idx = 0
    h1_list = []
    while idx < len(lines) and (not lines[idx].strip() or lines[idx].startswith("# ")):
        if lines[idx].startswith("# "):
            h1_list.append(lines[idx][2:].strip())
        idx += 1
    if len(h1_list) >= 1:
        cover_title = h1_list[0]
    if len(h1_list) >= 2:
        cover_subtitle = h1_list[1].replace("企业级", "")

    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx < len(lines) and lines[idx].strip().startswith("|"):
        raw_meta = []
        while idx < len(lines) and lines[idx].strip().startswith("|"):
            cells = [c.strip() for c in lines[idx].strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                raw_meta.append(cells)
            idx += 1
        meta_rows = raw_meta

    while idx < len(lines) and (not lines[idx].strip() or lines[idx].strip() == "---"):
        idx += 1

    # 预扫描所有二级标题 (##) 以建立稳定的书签键 sec_1, sec_2, ...
    chapter_titles: List[str] = []
    for ln in lines[idx:]:
        st = ln.strip()
        if st.startswith("## ") and st[3:].strip() != "目录":
            chapter_titles.append(st[3:].strip())

    story = []

    # ==================== 第 1 页：封面页 ====================
    story.append(Spacer(1, 34 * mm))
    cover_title_style = ParagraphStyle(
        "CoverTitle",
        fontName=bold_font,
        fontSize=19.5,
        leading=28,
        textColor=COLOR_NAVY,
        alignment=TA_LEFT,
    )
    cover_sub_style = ParagraphStyle(
        "CoverSub",
        fontName=bold_font,
        fontSize=15,
        leading=22,
        textColor=COLOR_PRIMARY,
        alignment=TA_LEFT,
        spaceBefore=6,
    )
    cover_tag_style = ParagraphStyle(
        "CoverTag",
        fontName=reg_font,
        fontSize=10,
        leading=15,
        textColor=COLOR_MUTED,
        alignment=TA_LEFT,
        spaceBefore=8,
    )
    p_cover = Paragraph(escape(cover_title), cover_title_style)
    p_cover._bookmark_key = "cover"
    p_cover._bookmark_title = "封面"
    p_cover._bookmark_level = 0
    story.append(p_cover)
    story.append(Paragraph(escape(cover_subtitle), cover_sub_style))
    story.append(Paragraph("SMT / 半导体封装 BGA 焊点自动化 X-Ray 智能探伤解决方案 · 独立二进制交付版", cover_tag_style))
    story.append(Spacer(1, 18 * mm))

    if meta_rows:
        story.append(_build_table(meta_rows, avail_w, reg_font, bold_font))
    story.append(Spacer(1, 55 * mm))

    cover_note_style = ParagraphStyle(
        "CoverNote",
        fontName=reg_font,
        fontSize=8.5,
        leading=13.5,
        textColor=COLOR_MUTED,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )
    story.append(Paragraph(
        "说明：本手册面向生产现场操作员（OP）、品保工程师（QE）及 IT 运维部署人员编写，"
        "全面覆盖独立离线发行包（X-Ray_AI_Inspector）的安装部署、日常作业 SOP、参数配方、"
        "合规报表导出、模型热替换及出厂静默自检验收规范。",
        cover_note_style,
    ))
    story.append(PageBreak())

    # ==================== 第 2 页：目录页（独占一页 + 可点击跳转） ====================
    story.append(_build_h2_banner("目录", avail_w, bold_font, bookmark_key="toc"))
    story.append(Spacer(1, 8))
    for ch_idx, ch_title in enumerate(chapter_titles, start=1):
        sec_key = f"sec_{ch_idx}"
        clean_t = _format_inline_md(ch_title, bold_font)
        toc_line = f'<a href="#{sec_key}" color="#0f172a">{clean_t}</a>'
        story.append(Paragraph(toc_line, style_toc_item))
    story.append(PageBreak())

    # 跳过 Markdown 源文件里的原始目录区（直到第一个正文 ## 章节）
    n = len(lines)
    while idx < n:
        st = lines[idx].strip()
        if st.startswith("## ") and st[3:].strip() != "目录":
            break
        idx += 1

    # ==================== 正文解析（每章新起一页 + 完整章节/小节书签） ====================
    ch_counter = 0
    sub_counter = 0

    while idx < n:
        line = lines[idx]
        stripped = line.strip()

        if not stripped or stripped == "---":
            idx += 1
            continue

        # 1. 代码块 ```
        if stripped.startswith("```"):
            idx += 1
            code_lines = []
            while idx < n and not lines[idx].strip().startswith("```"):
                code_lines.append(lines[idx])
                idx += 1
            idx += 1
            if code_lines:
                raw_code_joined = "\n".join(code_lines)
                # 特殊优化：4.1 主界面功能分区框图用矢量合并单元格表格渲染，彻底对齐
                if "[顶部自定义标题栏]" in raw_code_joined and "[左侧控制面板]" in raw_code_joined:
                    story.append(Spacer(1, 4))
                    story.append(_build_ui_layout_diagram(avail_w, reg_font, bold_font))
                    story.append(Spacer(1, 8))
                else:
                    story.append(Spacer(1, 3))
                    story.append(_build_code_block(code_lines, avail_w, reg_font))
                    story.append(Spacer(1, 6))
            continue

        # 2. Markdown 表格
        if stripped.startswith("|"):
            tbl_rows = []
            while idx < n and lines[idx].strip().startswith("|"):
                cells = [c.strip() for c in lines[idx].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    tbl_rows.append(cells)
                idx += 1
            if tbl_rows:
                story.append(Spacer(1, 3))
                story.append(_build_table(tbl_rows, avail_w, reg_font, bold_font))
                story.append(Spacer(1, 6))
            continue

        # 3. 引用提示块 >
        if stripped.startswith(">"):
            q_lines = []
            while idx < n and lines[idx].strip().startswith(">"):
                q_lines.append(lines[idx].strip().lstrip(">").strip())
                idx += 1
            if q_lines:
                story.append(Spacer(1, 3))
                story.append(_build_quote_block(q_lines, avail_w, reg_font, bold_font))
                story.append(Spacer(1, 5))
            continue

        # 4. 二级标题 ##（每章自动新起一页 + 一级书签）
        if stripped.startswith("## "):
            title_t = stripped[3:].strip()
            ch_counter += 1
            if ch_counter > 1:
                story.append(PageBreak())
            sec_key = f"sec_{ch_counter}"
            story.append(_build_h2_banner(title_t, avail_w, bold_font, bookmark_key=sec_key))
            story.append(Spacer(1, 5))
            idx += 1
            continue

        # 5. 三级标题 ###（二级子书签）
        if stripped.startswith("### "):
            title_t = stripped[4:].strip()
            sub_counter += 1
            sub_key = f"sub_{sub_counter}"
            p_h3 = Paragraph(f'<a name="{sub_key}"/>{_format_inline_md(title_t, bold_font)}', style_h3)
            p_h3._bookmark_key = sub_key
            p_h3._bookmark_title = _plain_title(title_t)
            p_h3._bookmark_level = 1
            story.append(p_h3)
            idx += 1
            continue

        # 6. 无序列表 - / *
        if re.match(r"^[-*]\s+", stripped):
            item_t = re.sub(r"^[-*]\s+", "", stripped)
            story.append(Paragraph(f"• {_format_inline_md(item_t, bold_font)}", style_bullet))
            idx += 1
            continue

        # 7. 有序列表 1.
        m_ol = re.match(r"^(\d+)\.\s+(.*)", stripped)
        if m_ol:
            num, item_t = m_ol.group(1), m_ol.group(2)
            story.append(Paragraph(f'<font name="{bold_font}">{num}.</font> {_format_inline_md(item_t, bold_font)}', style_bullet))
            idx += 1
            continue

        # 8. 普通段落
        para_lines = [stripped]
        idx += 1
        while idx < n:
            nxt = lines[idx].strip()
            if (
                not nxt
                or nxt == "---"
                or nxt.startswith(("#", "|", ">", "```"))
                or re.match(r"^([-*]|\d+\.)\s+", nxt)
            ):
                break
            para_lines.append(nxt)
            idx += 1
        story.append(Paragraph(_format_inline_md(" ".join(para_lines), bold_font), style_body))

    # ==================== 页眉与页脚绘制回调 ====================
    def _draw_cover_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(COLOR_NAVY)
        canvas.rect(0, page_h - 18 * mm, page_w, 18 * mm, fill=1, stroke=0)
        canvas.setFillColor(COLOR_PRIMARY)
        canvas.rect(0, page_h - 19.5 * mm, page_w, 1.5 * mm, fill=1, stroke=0)
        canvas.setFont(bold_font, 10)
        canvas.setFillColor(colors.white)
        canvas.drawString(margin_x, page_h - 11.5 * mm, "X-RAY AI INSPECTOR  |  INDUSTRIAL AOI WORKSTATION")
        canvas.setStrokeColor(COLOR_BORDER)
        canvas.setLineWidth(0.6)
        canvas.line(margin_x, 15 * mm, page_w - margin_x, 15 * mm)
        canvas.setFont(reg_font, 8)
        canvas.setFillColor(COLOR_MUTED)
        canvas.drawString(margin_x, 10.5 * mm, "客户交付技术文档 · 严禁未经授权外传")
        canvas.drawRightString(page_w - margin_x, 10.5 * mm, "v1.0 工业二进制发行版")
        canvas.restoreState()

    def _draw_later_pages(canvas, doc):
        canvas.saveState()
        canvas.setFont(reg_font, 8)
        canvas.setFillColor(COLOR_MUTED)
        canvas.drawString(margin_x, page_h - 12 * mm, "X射线智能工业质检工作站（X-ray AI Inspector）")
        canvas.drawRightString(page_w - margin_x, page_h - 12 * mm, "用户操作与部署手册")
        canvas.setStrokeColor(COLOR_BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(margin_x, page_h - 14.5 * mm, page_w - margin_x, page_h - 14.5 * mm)

        canvas.line(margin_x, 13 * mm, page_w - margin_x, 13 * mm)
        canvas.drawString(margin_x, 9 * mm, "客户交付文档 · 独立离线发行版")
        canvas.drawRightString(page_w - margin_x, 9 * mm, f"第 {doc.page} 页")
        canvas.restoreState()

    doc = ManualDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=margin_x,
        rightMargin=margin_x,
        topMargin=margin_top,
        bottomMargin=margin_bottom,
        title="X射线智能工业质检工作站 - 用户操作与部署手册",
        author="X-ray AI Inspector Engineering",
    )
    doc.build(story, onFirstPage=_draw_cover_page, onLaterPages=_draw_later_pages)
    return pdf_path


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MD_PATH
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PDF_PATH
    out = build_manual_pdf(src, dst)
    print(f"[OK] 已生成带章节书签的 PDF 操作手册: {out} ({out.stat().st_size / 1024:.1f} KB)")
