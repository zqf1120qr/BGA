# -*- coding: utf-8 -*-
"""
X射线 工业级 PDF 质检单报表生成器 (PDF Reporter)
-------------------------------------------------
严格遵照公司质量标准与用户定制版式渲染 A4 工业质检报告：
1. 首页: 《X 射线检测报告》标准审批单:
   - 深色表头纯白加粗显示，解决底纹发黑问题；
   - 送检数量与送检位号内容居中，送检数量不加焊球数；
   - (不)符合要求列只填纯片数或 /，无多余括号赘述；
   - 检验结论粗体，内容缩进，列表圆形 ●；
   - 底部左边检验员、右边检验日期，无检验机构无(Inspector)；
   - 页面垂直分布舒展匀称，消除底部大片空白。
2. 次页: 《X 射线检测批次工件质检清单总览》:
   - 表头纯白粗体，工件名点击跳转明细单，侧边栏书签大纲树直观呈现；
   - 彻底移除底部品质主管/工艺工程师签字栏。
3. 工件明细页: 100% 遵照 docs/bga_report_template.docx 定制规范:
   - 系统初判与人工终判表头单元格与结果单元格填充相同颜色；
   - 系统初判与人工终判只填“NG 不良”或“PASS 合格”；
   - 系统评判指标只填系统设置参数 (如 ≤15.0%)，无多余长句；
   - 系统初判与人工复判指标统计分别以两个独立 4x4 表格呈现，完整保留8项指标且白字清晰；
   - 全景高清纯缺陷图、图例条、缺陷明细清单；
   - 底部只保留“人工复核员”和“审核日期”。
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
        fontSize=20,
        leading=24,
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
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=6,
        spaceAfter=3,
    )
    style_cell = _get_or_create(
        "BgaCellText",
        fontName=font_name,
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#334155"),
    )
    style_cell_center = _get_or_create(
        "BgaCellCenter",
        fontName=font_name,
        fontSize=8.5,
        leading=11.5,
        alignment=1,
        textColor=colors.HexColor("#334155"),
    )
    style_cell_bold = _get_or_create(
        "BgaCellBold",
        fontName=font_name,
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#0f172a"),
    )
    style_cell_bold_center = _get_or_create(
        "BgaCellBoldCenter",
        fontName=font_name,
        fontSize=8.5,
        leading=11.5,
        alignment=1,
        textColor=colors.HexColor("#0f172a"),
    )
    style_cell_bold_right = _get_or_create(
        "BgaCellBoldRight",
        fontName=font_name,
        fontSize=9,
        leading=12,
        alignment=2,  # 居右
        textColor=colors.HexColor("#0f172a"),
    )
    style_header_white = _get_or_create(
        "BgaHeaderWhite",
        fontName=font_name,
        fontSize=9.5,
        leading=12.5,
        alignment=1,
        textColor=colors.white,
    )
    style_stamp = _get_or_create(
        "BgaStatusStamp",
        fontName=font_name,
        fontSize=13,
        leading=16,
        alignment=1,
        spaceBefore=2,
        spaceAfter=2,
    )

    return {
        "title": style_title,
        "subtitle": style_subtitle,
        "h2": style_h2,
        "cell": style_cell,
        "cell_center": style_cell_center,
        "cell_bold": style_cell_bold,
        "cell_bold_center": style_cell_bold_center,
        "cell_bold_right": style_cell_bold_right,
        "header_white": style_header_white,
        "stamp": style_stamp,
    }


def _build_batch_xray_cover_flowables(
    batch_title: str,
    batch_items: List[Dict[str, Any]],
    styles: Dict[str, Any],
    font_name: str,
    overview_key: str = "bga_batch_overview",
) -> list:
    """
    构建批量报告的封面/总览页: 100% 遵照优化后的《X 射线检测报告》标准格式
    涵盖：
    1. 页面垂直比例饱满，消除下部大片空白；
    2. 表头深色底纹纯白加粗显示，绝不发黑；
    3. 送检数量、送检位号内容居中，送检数量不带焊球数；
    4. (不)符合要求列只填纯片数或 /，无多余括号；
    5. 检验结论加粗，正文缩进，列表圆形 ●；
    6. 底部左边检验员、右边检验日期，无检验机构无(Inspector)。
    """
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    flowables = []

    # 注册书签
    flowables.append(BookmarkFlowable(title="【批次质检总览】(X 射线检测报告)", key=overview_key, level=0))

    # 顶部空隙与标题间距优化 (整页居中舒展，消除底部空白)
    flowables.append(Spacer(1, 20))
    flowables.append(Paragraph("X 射线检测报告", styles["title"]))
    flowables.append(Spacer(1, 16))

    # 2. 统计计算各项指标
    total_boards = len(batch_items)

    ng_void_boards = sum(1 for it in batch_items if it.get("summary_stats", {}).get("void_ng_count", 0) > 0)
    pass_void_boards = total_boards - ng_void_boards

    ng_bridge_boards = sum(1 for it in batch_items if it.get("summary_stats", {}).get("bridge_count", 0) > 0)
    pass_bridge_boards = total_boards - ng_bridge_boards

    ng_insuff_boards = sum(1 for it in batch_items if it.get("summary_stats", {}).get("insufficient_count", 0) > 0)
    pass_insuff_boards = total_boards - ng_insuff_boards

    pass_boards = sum(1 for it in batch_items if str(it.get("summary_stats", {}).get("board_status", "")).startswith("PASS"))
    ng_boards = total_boards - pass_boards
    pass_rate = (pass_boards / total_boards * 100.0) if total_boards > 0 else 0.0

    total_solders = sum(it.get("summary_stats", {}).get("total_solders", 0) for it in batch_items)
    total_void_ng = sum(it.get("summary_stats", {}).get("void_ng_count", 0) for it in batch_items)
    total_bridge = sum(it.get("summary_stats", {}).get("bridge_count", 0) for it in batch_items)
    total_insuff = sum(it.get("summary_stats", {}).get("insufficient_count", 0) for it in batch_items)
    total_cleared = sum(it.get("summary_stats", {}).get("manual_cleared_count", 0) for it in batch_items)

    # 3. 构造 16 行核心表格 (宽度 18.0 cm)
    col_w = [3.4 * cm, 5.6 * cm, 3.4 * cm, 5.6 * cm]

    def _c_bold(t): return Paragraph(f"<b>{t}</b>", styles["cell_bold_center"])
    def _c_center(t): return Paragraph(t, styles["cell_center"])
    def _c_pass(t): return Paragraph(f"<font color='#16a34a'><b>{t}</b></font>", styles["cell_center"])
    def _c_ng(t): return Paragraph(f"<font color='#dc2626'><b>{t}</b></font>", styles["cell_center"])
    def _c_head(t): return Paragraph(f"<font color='#ffffff'><b>{t}</b></font>", styles["header_white"])

    # (不)符合要求列中只填纯片数或“/”，不要括号其他内容
    v_pass_str = f"{pass_void_boards} 片"
    v_ng_str = f"{ng_void_boards} 片"

    b_pass_str = f"{pass_bridge_boards} 片"
    b_ng_str = f"{ng_bridge_boards} 片"

    i_pass_str = f"{pass_insuff_boards} 片"
    i_ng_str = f"{ng_insuff_boards} 片"

    # 综合结论文字 (加粗标题，内容缩进，列表圆形 ●)
    now_str = datetime.datetime.now().strftime("%Y年%m月%d日")
    is_all_pass = (ng_boards == 0)
    concl_verdict = f"<font color='#16a34a'><b>PASS 全部合格 (综合合格率: {pass_rate:.1f}%)</b></font>" if is_all_pass else f"<font color='#dc2626'><b>NG 检出缺陷 (合格 {pass_boards} 片 / 不良 {ng_boards} 片，综合合格率: {pass_rate:.1f}%)</b></font>"

    conclusion_html = (
        f"<font size='9.5'><b>【检验结论】</b></font><br/>"
        f"&nbsp;&nbsp;&nbsp;&nbsp;本次共送检 X射线 工件 <b>{total_boards}</b> 片，受检焊球 <b>{total_solders}</b> 点。<br/>"
        f"&nbsp;&nbsp;&nbsp;&nbsp;经 X 射线智能算法综合检测与人工复核审计：<br/>"
        f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;● <b>空洞缺陷：</b>合格 {pass_void_boards} 片，超标不良 {ng_void_boards} 片 (累计检出超标焊球 {total_void_ng} 处)；<br/>"
        f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;● <b>桥连短路：</b>合格 {pass_bridge_boards} 片，短路不良 {ng_bridge_boards} 片 (累计检出桥连短路 {total_bridge} 对)；<br/>"
        f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;● <b>虚焊少锡：</b>合格 {pass_insuff_boards} 片，少锡不良 {ng_insuff_boards} 片 (累计检出少锡缩减 {total_insuff} 处)；<br/>"
        f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;● <b>人工复核：</b>共确认排除误检 {total_cleared} 处。<br/>"
        f"&nbsp;&nbsp;&nbsp;&nbsp;<b>批次综合判定结果：{concl_verdict}</b><br/>"
        f"&nbsp;&nbsp;&nbsp;&nbsp;<font color='#64748b'><i>(注：锡球状态、偏移、焊球间隙、透锡率及多余物指标本次检验免检/不适用，统一标注为“/”)</i></font>"
    )

    table_data = [
        # 行 0
        [_c_bold("客户名称"), _c_center("/"), _c_bold("批次号"), _c_center("/")],
        # 行 1
        [_c_bold("产品名称"), Paragraph(f"<b>{batch_title}</b>", styles["cell_bold_center"]), _c_bold("产品编号"), _c_center("/")],
        # 行 2: 送检数量居中，不加焊球数量 (跨 1~3)
        [_c_bold("送检数量"), _c_center(f"{total_boards} 片"), "", ""],
        # 行 3: 送检位号居中 (跨 1~3)
        [_c_bold("送检位号"), _c_center("/"), "", ""],
        # 行 4: 分隔行
        ["", "", "", ""],
        # 行 5: 检验项目表头 (纯白字体)
        [_c_head("检验项目"), _c_head("要求指标"), _c_head("符合要求"), _c_head("不符合要求")],
        # 行 6~13: 8 项指标 (纯片数或 /)
        [_c_bold("空洞"), _c_center("≤25%"), _c_pass(v_pass_str), _c_ng(v_ng_str) if ng_void_boards > 0 else _c_center(v_ng_str)],
        [_c_bold("桥连"), _c_center("无桥连"), _c_pass(b_pass_str), _c_ng(b_ng_str) if ng_bridge_boards > 0 else _c_center(b_ng_str)],
        [_c_bold("锡球状态"), _c_center("锡球无缺失，大小均匀一致"), _c_center("/"), _c_center("/")],
        [_c_bold("虚焊"), _c_center("无虚焊"), _c_pass(i_pass_str), _c_ng(i_ng_str) if ng_insuff_boards > 0 else _c_center(i_ng_str)],
        [_c_bold("偏移"), _c_center("≤10%"), _c_center("/"), _c_center("/")],
        [_c_bold("焊球间隙"), _c_center("未违反最小电气间隙"), _c_center("/"), _c_center("/")],
        [_c_bold("透锡率"), _c_center("100%"), _c_center("/"), _c_center("/")],
        [_c_bold("多余物"), _c_center("无多余物"), _c_center("/"), _c_center("/")],
        # 行 14: 分隔行
        ["", "", "", ""],
        # 行 15: 检验结论 (跨 0~3)
        [Paragraph(conclusion_html, styles["cell"]), "", "", ""],
    ]

    t_xray = Table(table_data, colWidths=col_w)

    t_styles = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("FONTNAME", (0, 0), (-1, -1), font_name),

        # 饱满行高内边距 (进一步优化垂直空间分布，消除底部大片空白)
        ("TOPPADDING", (0, 0), (-1, 3), 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, 3), 9.5),

        # 标签背景色
        ("BACKGROUND", (0, 0), (0, 3), colors.HexColor("#f8fafc")),
        ("BACKGROUND", (2, 0), (2, 1), colors.HexColor("#f8fafc")),

        # 合并单元格
        ("SPAN", (1, 2), (3, 2)),  # 送检数量跨列
        ("SPAN", (1, 3), (3, 3)),  # 送检位号跨列
        ("SPAN", (0, 4), (3, 4)),  # 分隔行
        ("BACKGROUND", (0, 4), (3, 4), colors.HexColor("#f1f5f9")),
        ("TOPPADDING", (0, 4), (3, 4), 4),
        ("BOTTOMPADDING", (0, 4), (3, 4), 4),

        # 检验项目表头 (深色底纹 + 纯白字体)
        ("BACKGROUND", (0, 5), (3, 5), colors.HexColor("#1e293b")),
        ("TOPPADDING", (0, 5), (3, 5), 9.0),
        ("BOTTOMPADDING", (0, 5), (3, 5), 9.0),

        # 8项数据行斑马纹
        ("TOPPADDING", (0, 6), (3, 13), 8.5),
        ("BOTTOMPADDING", (0, 6), (3, 13), 8.5),
        ("BACKGROUND", (0, 6), (3, 6), colors.HexColor("#ffffff")),
        ("BACKGROUND", (0, 7), (3, 7), colors.HexColor("#f8fafc")),
        ("BACKGROUND", (0, 8), (3, 8), colors.HexColor("#ffffff")),
        ("BACKGROUND", (0, 9), (3, 9), colors.HexColor("#f8fafc")),
        ("BACKGROUND", (0, 10), (3, 10), colors.HexColor("#ffffff")),
        ("BACKGROUND", (0, 11), (3, 11), colors.HexColor("#f8fafc")),
        ("BACKGROUND", (0, 12), (3, 12), colors.HexColor("#ffffff")),
        ("BACKGROUND", (0, 13), (3, 13), colors.HexColor("#f8fafc")),

        # 分隔行 14
        ("SPAN", (0, 14), (3, 14)),
        ("BACKGROUND", (0, 14), (3, 14), colors.HexColor("#f1f5f9")),
        ("TOPPADDING", (0, 14), (3, 14), 4),
        ("BOTTOMPADDING", (0, 14), (3, 14), 4),

        # 检验结论大单元格
        ("SPAN", (0, 15), (3, 15)),
        ("BACKGROUND", (0, 15), (3, 15), colors.HexColor("#ffffff")),
        ("TOPPADDING", (0, 15), (3, 15), 18),
        ("BOTTOMPADDING", (0, 15), (3, 15), 18),
    ]

    t_xray.setStyle(TableStyle(t_styles))
    flowables.append(t_xray)
    flowables.append(Spacer(1, 28))

    # 底部签字行: 彻底删除“检验员: ”，只保留居右对齐的“检验日期”
    sign_row = [
        [
            Paragraph(f"<b>检验日期:</b> {now_str}", styles["cell_bold_right"]),
        ]
    ]
    t_sign = Table(sign_row, colWidths=[18.0 * cm])
    t_sign.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flowables.append(t_sign)

    return flowables


def _build_batch_item_list_flowables(
    batch_items: List[Dict[str, Any]],
    styles: Dict[str, Any],
    font_name: str,
    list_key: str = "bga_batch_item_list",
) -> list:
    """
    构建第二页：【X 射线检测批次工件质检清单总览】
    1. 标题更新为《X 射线检测批次工件质检清单总览》；
    2. 表头文字纯白加粗显示；
    3. 彻底移除底部品质主管/工艺工程师/批次检验日期签字栏。
    """
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    flowables = []

    flowables.append(BookmarkFlowable(title="【批次工件清单列表】(点击跳转明细)", key=list_key, level=0))
    flowables.append(Paragraph("X 射线检测批次工件质检清单总览", styles["title"]))
    flowables.append(Paragraph("【批次工件质检清单列表 (点击工件名称可直接跳至明细页)】", styles["h2"]))

    # 表头纯白
    def _th(t): return Paragraph(f"<font color='#ffffff'><b>{t}</b></font>", styles["header_white"])

    item_table_data = [
        [_th("序号"), _th("工件图片名称 (点击跳转明细)"), _th("焊点数"), _th("空洞NG"), _th("桥连短路"), _th("虚焊少锡"), _th("人工排除"), _th("最终判定")]
    ]
    item_table_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
    ]

    for idx, item in enumerate(batch_items, start=1):
        stats = item.get("summary_stats", {})
        img_name = item.get("image_name") or os.path.basename(item.get("image_path", f"item_{idx}"))
        b_status = stats.get("board_status", "UNKNOWN")
        is_p = str(b_status).startswith("PASS")
        item_anchor = f"bga_item_{idx}"

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
    flowables.append(t_item_list)
    flowables.append(Spacer(1, 14))

    # 彻底删除底部“品质主管”、“工艺工程师”、批次检验日期全部内容

    return flowables


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
    bridge_defects: Optional[List[Dict[str, Any]]] = None,
) -> list:
    """
    构建单个工件图像的质检报告页流元素:
    100% 遵照 docs/bga_report_template.docx 版式规范优化:
    1. 系统初判与人工终判单元格表头与结果填充相同颜色；
    2. 系统初判与人工终判只填“NG 不良”或“PASS 合格”；
    3. 系统评判指标只填系统设置参数 (如 ≤15.0%)；
    4. 系统初判与人工复判指标统计分别以两个独立 4x4 表格呈现，表头纯白加粗，未检测填 /；
    5. 全景标注图与明细清单；
    6. 底部只留人工复核员和审核日期。
    """
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

    flowables = []

    board_status = summary_stats.get("board_status", "UNKNOWN")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 0. 书签锚点
    if bookmark_key:
        if item_index is not None:
            bm_title = f"工件 [{item_index:02d}]: {image_name} ({board_status})"
        else:
            bm_title = f"工件明细单: {image_name} ({board_status})"
        flowables.append(BookmarkFlowable(title=bm_title, key=bookmark_key, level=0))

    # 1. 标题与返回总览微链接
    if item_index is not None and total_items is not None:
        title_text = f"X射线检测分析报告单 [{item_index:02d}/{total_items:02d}]: {image_name}"
        flowables.append(Paragraph(title_text, styles["title"]))
        if back_to_overview_key:
            back_link = f"<a href='#{back_to_overview_key}'><font color='#2563eb'>◀ 返回批次工件质检清单</font></a>"
            flowables.append(Paragraph(back_link, styles["cell"]))
            flowables.append(Spacer(1, 3))
    else:
        flowables.append(Paragraph("X射线检测分析报告单", styles["title"]))
        flowables.append(Spacer(1, 3))

    # 原始初检数据计算 (算法初始检出指标，不受人工复核扣减影响)
    raw_v_ng = summary_stats.get("raw_void_ng_count")
    if raw_v_ng is None:
        raw_v_ng = sum(1 for r in records if r.is_void_ng)

    raw_b_ng = summary_stats.get("raw_bridge_count")
    if raw_b_ng is None:
        raw_b_ng = len(bridge_defects) if bridge_defects is not None else summary_stats.get("bridge_count", 0)

    raw_i_ng = summary_stats.get("raw_insuff_count")
    if raw_i_ng is None:
        raw_i_ng = sum(1 for r in records if r.is_insufficient)

    # 人工复核后实际剩余 NG 统计
    final_void_ng = summary_stats.get("void_ng_count", 0)
    final_bridge_ng = summary_stats.get("bridge_count", 0)
    final_insuff_ng = summary_stats.get("insufficient_count", 0)

    # 判定颜色与精炼文本设定
    # 初判: 原始算法检测指标是否存在任何缺陷
    initial_has_defect = (raw_v_ng > 0 or raw_b_ng > 0 or raw_i_ng > 0) or any(r.is_ng for r in records)
    is_final_pass = str(board_status).startswith("PASS")

    # 系统初判: 只填 "NG 不良" 或 "PASS 合格"
    if initial_has_defect:
        sys_bg = colors.HexColor("#fee2e2")
        sys_color = colors.HexColor("#dc2626")
        sys_status_text = "NG 不良"
    else:
        sys_bg = colors.HexColor("#dcfce7")
        sys_color = colors.HexColor("#16a34a")
        sys_status_text = "PASS 合格"

    # 人工终判: 只填 "NG 不良" 或 "PASS 合格"
    if is_final_pass:
        manual_bg = colors.HexColor("#cffafe") if "人工复核" in str(board_status) else colors.HexColor("#dcfce7")
        manual_color = colors.HexColor("#0891b2") if "人工复核" in str(board_status) else colors.HexColor("#16a34a")
        manual_status_text = "PASS 合格"
    else:
        manual_bg = colors.HexColor("#fee2e2")
        manual_color = colors.HexColor("#dc2626")
        manual_status_text = "NG 不良"

    # 2. Table 0: 基本信息表 (3 行 6 列)
    # 系统初判、人工终判表头单元格与结果单元格填充相同颜色！
    w0 = [2.6 * cm, 4.4 * cm, 2.2 * cm, 3.8 * cm, 2.5 * cm, 2.5 * cm]
    elapsed = float(summary_stats.get('elapsed_ms') or 0.0)

    t0_data = [
        [
            Paragraph("<b>产品名称:</b>", styles["cell_bold"]),
            Paragraph(image_name, styles["cell"]),
            Paragraph("<b>批次号:</b>", styles["cell_bold"]),
            Paragraph("/", styles["cell"]),
            Paragraph("<b>产品编号:</b>", styles["cell_bold"]),
            Paragraph("/", styles["cell"]),
        ],
        [
            Paragraph("<b>送检位号:</b>", styles["cell_bold"]),
            Paragraph("/", styles["cell"]),
            Paragraph("<b>检测模式:</b>", styles["cell_bold"]),
            Paragraph("全项综合检测 (空洞+连锡+虚焊)", styles["cell"]),
            Paragraph("<b>系统初判</b>", styles["cell_bold_center"]),
            Paragraph("<b>人工终判</b>", styles["cell_bold_center"]),
        ],
        [
            Paragraph("<b>检验时间:</b>", styles["cell_bold"]),
            Paragraph(now_str, styles["cell"]),
            Paragraph("<b>检测用时:</b>", styles["cell_bold"]),
            Paragraph(f"{elapsed:.1f} ms", styles["cell"]),
            Paragraph(f"<font color='{sys_color.hexval()}'><b>{sys_status_text}</b></font>", styles["cell_bold_center"]),
            Paragraph(f"<font color='{manual_color.hexval()}'><b>{manual_status_text}</b></font>", styles["cell_bold_center"]),
        ],
    ]
    t0 = Table(t0_data, colWidths=w0)
    t0.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (0, 2), colors.HexColor("#f8fafc")),
        ("BACKGROUND", (2, 0), (2, 2), colors.HexColor("#f8fafc")),
        # 系统初判: 表头 (4, 1) 和结果 (4, 2) 均加上相同底色 sys_bg
        ("BACKGROUND", (4, 1), (4, 2), sys_bg),
        # 人工终判: 表头 (5, 1) 和结果 (5, 2) 均加上相同底色 manual_bg
        ("BACKGROUND", (5, 1), (5, 2), manual_bg),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    flowables.append(t0)
    flowables.append(Spacer(1, 4))

    # 3. 【系统评判指标】(只填参数值，无多余长句，白字表头)
    flowables.append(Paragraph("【系统评判指标】", styles["h2"]))
    v_thresh = float(summary_stats.get("void_threshold") or 0.15) * 100.0
    r_thresh = float(summary_stats.get("reduction_threshold") or 0.20) * 100.0

    t1_data = [
        [
            Paragraph("<font color='#ffffff'><b>空洞占比超标阈值</b></font>", styles["header_white"]),
            Paragraph("<font color='#ffffff'><b>虚焊少锡缺少比例</b></font>", styles["header_white"]),
        ],
        [
            Paragraph(f"<b>≤{v_thresh:.1f}%</b>", styles["cell_center"]),
            Paragraph(f"<b>≤{r_thresh:.1f}%</b>", styles["cell_center"]),
        ],
    ]
    t1 = Table(t1_data, colWidths=[9.0 * cm, 9.0 * cm])
    t1.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    flowables.append(t1)
    flowables.append(Spacer(1, 4))

    # 4. 统计数据色彩映射 (无论是否为 0，数据文字颜色均严格对应图例颜色):
    # 1. 空洞超标 -> 琥珀金黄 '#d97706' (图例 ● 空洞超标)
    # 2. 桥连短路 -> 红色 '#dc2626' (图例 ● 桥连短路)
    # 3. 虚焊少锡 -> 紫色 '#9333ea' (图例 ● 虚焊少锡)
    col_v = "#d97706"
    col_b = "#dc2626"
    col_i = "#9333ea"

    col_f_v = "#d97706"
    col_f_b = "#dc2626"
    col_f_i = "#9333ea"

    col_w4 = [4.5 * cm, 4.5 * cm, 4.5 * cm, 4.5 * cm]
    def _th_w(t): return Paragraph(f"<font color='#ffffff'><b>{t}</b></font>", styles["header_white"])

    # 4.1 表格 A: 【系统初判指标统计】(4x4, 纯白表头，显示算法初检原始指标，未检测填 /)
    flowables.append(Paragraph("【系统初判指标统计】", styles["h2"]))
    t_sys_data = [
        [_th_w("空洞超标"), _th_w("桥连短路"), _th_w("虚焊少锡"), _th_w("锡球状态")],
        [
            Paragraph(f"<font color='{col_v}'><b>{raw_v_ng} 处</b></font>", styles["cell_center"]),
            Paragraph(f"<font color='{col_b}'><b>{raw_b_ng} 对</b></font>", styles["cell_center"]),
            Paragraph(f"<font color='{col_i}'><b>{raw_i_ng} 处</b></font>", styles["cell_center"]),
            Paragraph("/", styles["cell_center"]),
        ],
        [_th_w("偏移"), _th_w("焊球间隙"), _th_w("透锡率"), _th_w("多余物")],
        [
            Paragraph("/", styles["cell_center"]),
            Paragraph("/", styles["cell_center"]),
            Paragraph("/", styles["cell_center"]),
            Paragraph("/", styles["cell_center"]),
        ],
    ]
    t_sys = Table(t_sys_data, colWidths=col_w4)
    t_sys.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#1e293b")),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    flowables.append(t_sys)
    flowables.append(Spacer(1, 4))

    # 4.2 表格 B: 【人工复判指标统计】(4x4, 纯白表头，显示人工复核排除后的当前有效指标，未检测填 /)
    flowables.append(Paragraph("【人工复判指标统计】", styles["h2"]))
    t_man_data = [
        [_th_w("空洞超标"), _th_w("桥连短路"), _th_w("虚焊少锡"), _th_w("锡球状态")],
        [
            Paragraph(f"<font color='{col_f_v}'><b>{final_void_ng} 处</b></font>", styles["cell_center"]),
            Paragraph(f"<font color='{col_f_b}'><b>{final_bridge_ng} 对</b></font>", styles["cell_center"]),
            Paragraph(f"<font color='{col_f_i}'><b>{final_insuff_ng} 处</b></font>", styles["cell_center"]),
            Paragraph("/", styles["cell_center"]),
        ],
        [_th_w("偏移"), _th_w("焊球间隙"), _th_w("透锡率"), _th_w("多余物")],
        [
            Paragraph("/", styles["cell_center"]),
            Paragraph("/", styles["cell_center"]),
            Paragraph("/", styles["cell_center"]),
            Paragraph("/", styles["cell_center"]),
        ],
    ]
    t_man = Table(t_man_data, colWidths=col_w4)
    t_man.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#1e293b")),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    flowables.append(t_man)
    flowables.append(Spacer(1, 4))

    # 5. 【全景检测标注图 (仅高亮显示异常与复核部位)】
    if preview_img_path and os.path.exists(preview_img_path):
        try:
            flowables.append(Paragraph("【全景检测标注图 (仅高亮显示异常与复核部位)】", styles["h2"]))
            from PIL import Image as PILImage
            with PILImage.open(preview_img_path) as pil_im:
                pw, ph = pil_im.size
            aspect = float(pw) / float(ph) if ph > 0 else 1.5

            max_w_cm = 16.0
            max_h_cm = 8.0
            if aspect >= (max_w_cm / max_h_cm):
                render_w = max_w_cm * cm
                render_h = (max_w_cm / aspect) * cm
            else:
                render_h = max_h_cm * cm
                render_w = (max_h_cm * aspect) * cm

            img_item = Image(preview_img_path, width=render_w, height=render_h)
            flowables.append(img_item)
            flowables.append(Spacer(1, 2.5))

            # 图例条 (颜色严格呼应: 空洞黄、桥连红、少锡紫、排除青、合格绿)
            legend_cells = [
                [
                    Paragraph("<font color='#d97706'><b>●</b></font> 空洞超标", styles["cell"]),
                    Paragraph("<font color='#dc2626'><b>●</b></font> 桥连短路", styles["cell"]),
                    Paragraph("<font color='#9333ea'><b>●</b></font> 虚焊少锡", styles["cell"]),
                    Paragraph("<font color='#0891b2'><b>●</b></font> 人工排除", styles["cell"]),
                    Paragraph("<font color='#10b981'><b>○</b></font> 正常合格(底图零遮挡)", styles["cell"]),
                ]
            ]
            t_leg = Table(legend_cells, colWidths=[3.2 * cm, 3.2 * cm, 3.2 * cm, 3.2 * cm, 5.2 * cm])
            t_leg.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            flowables.append(t_leg)
            flowables.append(Spacer(1, 4))
        except Exception as e:
            print(f"[WARN] 无法嵌入 PDF 图像 {preview_img_path}: {e}")

    # 6. 【不良与复核焊点明细清单】
    flowables.append(Paragraph("【不良与复核焊点明细清单】", styles["h2"]))
    defect_records = [
        r for r in records
        if r.final_is_ng or (r.is_manually_reviewed and r.manual_status == "PASS") or getattr(r, "is_bridge_cleared", False)
    ]

    # 检查是否存在已复核排除但未匹配到焊球的独立桥连缺陷
    extra_reviewed_bridges = []
    if bridge_defects:
        all_matched_ball_ids = {r.index for r in defect_records}
        for b_idx, b in enumerate(bridge_defects, start=1):
            if b.get("is_reviewed_pass", False):
                b_balls = b.get("ball_indices", [])
                if not any(bid in all_matched_ball_ids for bid in b_balls):
                    extra_reviewed_bridges.append((b_idx, b))

    if defect_records or extra_reviewed_bridges:
        defect_data = [
            [_th_w("序号"), _th_w("中心坐标(X, Y)"), _th_w("空洞占比"), _th_w("少锡缩减"), _th_w("桥连短路"), _th_w("初始原因"), _th_w("最终结论")]
        ]
        max_show = 150
        records_to_show = defect_records[:max_show]
        for r in records_to_show:
            is_ball_rev_pass = (r.is_manually_reviewed and r.manual_status == "PASS")
            is_bridge_cleared = (getattr(r, "is_bridge_cleared", False) and not r.final_is_ng)
            is_cleared = is_ball_rev_pass or is_bridge_cleared

            concl = "已排除误检(PASS)" if is_cleared else "NG 不良"
            rcx = float(r.cx) if r.cx is not None else 0.0
            rcy = float(r.cy) if r.cy is not None else 0.0
            r_void = float(r.void_rate) if r.void_rate is not None else 0.0
            r_reduct = float(r.reduction_percent) if r.reduction_percent is not None else 0.0

            # 桥连短路列
            if getattr(r, "has_active_bridge", False):
                bridge_str = "桥连短路NG"
            elif getattr(r, "is_bridge_cleared", False):
                bridge_str = "桥连排除"
            elif r.is_bridge:
                bridge_str = "桥连短路NG"
            else:
                bridge_str = "正常"

            # 初始原因列
            if r.ng_reasons:
                reason_str = ", ".join(r.ng_reasons)
            elif getattr(r, "is_bridge_cleared", False):
                reason_str = "桥连短路 (已排除)"
            elif r.is_manually_reviewed and r.review_reason:
                reason_str = r.review_reason
            else:
                reason_str = "异常 (已复核)" if is_cleared else "异常"

            defect_data.append([
                f"#{r.index}",
                f"({rcx:.1f}, {rcy:.1f})",
                f"{r_void * 100:.1f}%",
                f"-{r_reduct:.1f}%" if r_reduct > 0 else "0.0%",
                bridge_str,
                reason_str,
                concl,
            ])

        # 追加未匹配到焊球的独立排除桥连缺陷
        for b_idx, b in extra_reviewed_bridges:
            rx, ry, rw, rh = b.get("roi_box", (0, 0, 0, 0))
            defect_data.append([
                f"桥连#{b_idx}",
                f"({rx:.1f}, {ry:.1f})",
                "/",
                "/",
                "桥连排除",
                "焊膏粘连桥连 (已排除)",
                "已排除误检(PASS)",
            ])

        t_defect = Table(
            defect_data,
            colWidths=[1.6 * cm, 2.8 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm, 4.0 * cm, 3.0 * cm],
            repeatRows=1,
        )
        t_defect_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#475569")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ]
        row_i = 1
        for r in records_to_show:
            is_ball_rev_pass = (r.is_manually_reviewed and r.manual_status == "PASS")
            is_bridge_cleared = (getattr(r, "is_bridge_cleared", False) and not r.final_is_ng)
            if is_ball_rev_pass or is_bridge_cleared:
                t_defect_style.append(("BACKGROUND", (0, row_i), (-1, row_i), colors.HexColor("#cffafe")))
            else:
                t_defect_style.append(("BACKGROUND", (0, row_i), (-1, row_i), colors.HexColor("#fff1f2")))
            row_i += 1

        for _ in extra_reviewed_bridges:
            t_defect_style.append(("BACKGROUND", (0, row_i), (-1, row_i), colors.HexColor("#cffafe")))
            row_i += 1

        t_defect.setStyle(TableStyle(t_defect_style))
        flowables.append(t_defect)
    else:
        flowables.append(Paragraph("<font color='#16a34a'><b>全板未检出任何空洞、桥连或少锡缺陷，整板符合工业质量标准。</b></font>", styles["cell_bold"]))

    flowables.append(Spacer(1, 5))

    # 7. 底部签字栏: 只留“人工复核员”和“审核日期”
    sign_data = [
        [
            Paragraph("<b>人工复核员:</b> ________________", styles["cell_bold"]),
            Paragraph(f"<b>审核日期:</b> {now_str[:10]}", styles["cell_bold_right"]),
        ]
    ]
    t_sign = Table(sign_data, colWidths=[9.0 * cm, 9.0 * cm])
    t_sign.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
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
    progress_callback: Optional[Any] = None,
):
    """单张图像质检报告导出为 PDF (100% 遵照定制单片模板规范)"""
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

    if progress_callback:
        progress_callback(1, 2, f"正在渲染缺陷高清图: {image_name}")

    actual_preview = preview_img_path
    target_img = image_path or preview_img_path
    temp_preview_created = None
    if target_img and os.path.exists(target_img):
        try:
            actual_preview = render_defect_only_preview(
                image_path=target_img,
                records=records,
                bridge_defects=bridge_defects or [],
            )
            if actual_preview and actual_preview != target_img:
                temp_preview_created = actual_preview
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
        bridge_defects=bridge_defects,
    )

    if progress_callback:
        progress_callback(2, 2, "正在编译并保存高精度 PDF 质检单...")

    try:
        doc.build(story, onFirstPage=lambda c, d: c.showOutline())
    finally:
        if temp_preview_created and os.path.exists(temp_preview_created):
            try:
                os.remove(temp_preview_created)
            except Exception:
                pass


def export_batch_inspection_pdf(
    save_path: str,
    batch_items: List[Dict[str, Any]],
    batch_summary: Optional[Dict[str, Any]] = None,
    batch_product_name: Optional[str] = None,
    progress_callback: Optional[Any] = None,
):
    """
    批量检测结果合并导出至单一 PDF 文件 (全新工业报告体系):
    1. 首页: 【批次质检总览】(100% 遵照优化版《X 射线检测报告》审批单格式)；
    2. 次页: 【X 射线检测批次工件质检清单总览】(带点击工件名称跳转明细超链接与书签树)；
    3. 后续各页: 每一个工件独立的【X射线检测分析报告单】(100% 遵照优化版单片规范)。
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import PageBreak, SimpleDocTemplate

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

    # 1. 确定产品名称 (文件夹名)
    folder_name = batch_product_name
    if not folder_name and batch_items:
        first_img = batch_items[0].get("image_path", "")
        if first_img:
            parent_dir = os.path.basename(os.path.dirname(os.path.abspath(first_img)))
            if parent_dir:
                folder_name = parent_dir
    if not folder_name:
        folder_name = "X射线 批量送检板卡"

    overview_key = "bga_batch_overview"
    list_key = "bga_batch_item_list"

    # ==============================================================
    # 🌟 第一部分：封面/总览页 (100% 遵照优化版《X 射线检测报告》)
    # ==============================================================
    cover_flowables = _build_batch_xray_cover_flowables(
        batch_title=folder_name,
        batch_items=batch_items,
        styles=styles,
        font_name=font_name,
        overview_key=overview_key,
    )
    story.extend(cover_flowables)

    # ==============================================================
    # 🌟 第二部分：【X 射线检测批次工件质检清单总览】
    # ==============================================================
    story.append(PageBreak())
    list_flowables = _build_batch_item_list_flowables(
        batch_items=batch_items,
        styles=styles,
        font_name=font_name,
        list_key=list_key,
    )
    story.extend(list_flowables)

    # ==============================================================
    # 🌟 第三部分：各工件独立的【X射线检测分析报告单】
    # ==============================================================
    total_boards = len(batch_items)
    temp_previews_to_clean: List[str] = []

    for idx, item in enumerate(batch_items, start=1):
        img_name = item.get("image_name") or os.path.basename(item.get("image_path", f"item_{idx}"))
        if progress_callback:
            progress_callback(idx, total_boards + 1, f"正在渲染工件质检图 ({idx}/{total_boards}): {img_name}")

        story.append(PageBreak())
        stats = item.get("summary_stats", {})
        records = item.get("records", [])
        preview_path = item.get("preview_img_path")
        orig_img_path = item.get("image_path")
        bridge_defects = item.get("bridge_defects", [])

        actual_preview = preview_path
        if (orig_img_path and os.path.exists(orig_img_path)) or (preview_path and os.path.exists(preview_path)):
            target_to_render = orig_img_path if (orig_img_path and os.path.exists(orig_img_path)) else preview_path
            try:
                actual_preview = render_defect_only_preview(
                    image_path=target_to_render,
                    records=records,
                    bridge_defects=bridge_defects,
                )
                if actual_preview and actual_preview != target_to_render:
                    temp_previews_to_clean.append(actual_preview)
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
            back_to_overview_key=list_key,
            bridge_defects=bridge_defects,
        )
        story.extend(item_flowables)

    if progress_callback:
        progress_callback(total_boards, total_boards + 1, "正在排版编译高精度 PDF 工业质检文档...")

    try:
        doc.build(story, onFirstPage=lambda c, d: c.showOutline())
    finally:
        for tmp_p in temp_previews_to_clean:
            if tmp_p and os.path.exists(tmp_p):
                try:
                    os.remove(tmp_p)
                except Exception:
                    pass
