# -*- coding: utf-8 -*-
"""
生成优化后的工业标准《X 射线检测报告.docx》模板
1. 表头纯白粗体；
2. 送检数量、送检位号内容居中，送检数量不带焊球数；
3. 符合/不符合两列只填纯片数或 /，无多余括号；
4. 检验结论粗体，内容缩进，列表圆形 ●；
5. 底部去掉检验机构，左边检验员，右边检验日期，无(Inspector)；
6. 间距优化，居中饱满。
"""
from __future__ import annotations

import os
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn


def set_cell_background(cell, hex_color: str):
    hex_color = hex_color.lstrip('#')
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)


def set_cell_margins(cell, top=140, bottom=140, left=140, right=140):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)


def set_table_borders(table, color="CBD5E1", sz="4", val="single"):
    tblPr = table._tbl.tblPr
    borders_elm = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'  <w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:left w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:right w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:insideV w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders_elm)


def build_optimized_xray_template(output_path: str):
    doc = Document()

    for section in doc.sections:
        section.top_margin = Cm(1.5)
        section.bottom_margin = Cm(1.5)
        section.left_margin = Cm(1.5)
        section.right_margin = Cm(1.5)
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)

    normal_style = doc.styles['Normal']
    normal_style.font.name = '微软雅黑'
    normal_style._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    normal_style.font.size = Pt(9.5)
    normal_style.font.color.rgb = RGBColor(0x33, 0x41, 0x55)

    # 顶部空隙优化
    p_top = doc.add_paragraph()
    p_top.paragraph_format.space_before = Pt(8)
    p_top.paragraph_format.space_after = Pt(0)

    # 标题
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(14)
    r_title = p_title.add_run("X 射线检测报告")
    r_title.font.name = '微软雅黑'
    r_title._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    r_title.font.size = Pt(20)
    r_title.font.bold = True
    r_title.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)

    # 大表格
    col_widths = [Cm(3.5), Cm(5.5), Cm(3.5), Cm(5.5)]
    tbl = doc.add_table(rows=16, cols=4)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl, color="CBD5E1")

    def _fill_cell(cell, text, bold=False, color=None, bg="FFFFFF", align=WD_ALIGN_PARAGRAPH.CENTER, font_size=9.5, pad_v=140):
        set_cell_background(cell, bg)
        set_cell_margins(cell, top=pad_v, bottom=pad_v, left=120, right=120)
        p = cell.paragraphs[0]
        p.alignment = align
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(text)
        r.font.name = '微软雅黑'
        try:
            r._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
        except Exception:
            pass
        r.font.bold = bold
        r.font.size = Pt(font_size)
        if color:
            r.font.color.rgb = color

    # 行 0~3 基本信息
    _fill_cell(tbl.cell(0, 0), "客户名称", bold=True, bg="F8FAFC", color=RGBColor(0x1E, 0x29, 0x3B), pad_v=150)
    _fill_cell(tbl.cell(0, 1), "{{CUSTOMER_NAME}}", align=WD_ALIGN_PARAGRAPH.CENTER, pad_v=150)
    _fill_cell(tbl.cell(0, 2), "批次号", bold=True, bg="F8FAFC", color=RGBColor(0x1E, 0x29, 0x3B), pad_v=150)
    _fill_cell(tbl.cell(0, 3), "{{BATCH_NO}}", align=WD_ALIGN_PARAGRAPH.CENTER, pad_v=150)

    _fill_cell(tbl.cell(1, 0), "产品名称", bold=True, bg="F8FAFC", color=RGBColor(0x1E, 0x29, 0x3B), pad_v=150)
    _fill_cell(tbl.cell(1, 1), "{{PRODUCT_NAME}}", align=WD_ALIGN_PARAGRAPH.CENTER, bold=True, pad_v=150)
    _fill_cell(tbl.cell(1, 2), "产品编号", bold=True, bg="F8FAFC", color=RGBColor(0x1E, 0x29, 0x3B), pad_v=150)
    _fill_cell(tbl.cell(1, 3), "{{PRODUCT_CODE}}", align=WD_ALIGN_PARAGRAPH.CENTER, pad_v=150)

    # 送检数量 居中，不带焊球数
    tbl.cell(2, 1).merge(tbl.cell(2, 3))
    _fill_cell(tbl.cell(2, 0), "送检数量", bold=True, bg="F8FAFC", color=RGBColor(0x1E, 0x29, 0x3B), pad_v=150)
    _fill_cell(tbl.cell(2, 1), "{{SAMPLE_COUNT}}", align=WD_ALIGN_PARAGRAPH.CENTER, bold=True, pad_v=150)

    # 送检位号 居中
    tbl.cell(3, 1).merge(tbl.cell(3, 3))
    _fill_cell(tbl.cell(3, 0), "送检位号", bold=True, bg="F8FAFC", color=RGBColor(0x1E, 0x29, 0x3B), pad_v=150)
    _fill_cell(tbl.cell(3, 1), "{{SAMPLE_LOC}}", align=WD_ALIGN_PARAGRAPH.CENTER, pad_v=150)

    # 行 4 分隔行
    tbl.cell(4, 0).merge(tbl.cell(4, 3))
    _fill_cell(tbl.cell(4, 0), "", bg="F1F5F9", pad_v=40)

    # 行 5 检验项目表头 (纯白字体)
    headers = ["检验项目", "要求指标", "符合要求", "不符合要求"]
    for i, h_title in enumerate(headers):
        _fill_cell(tbl.cell(5, i), h_title, bold=True, bg="1E293B", color=RGBColor(0xFF, 0xFF, 0xFF), font_size=10.0, pad_v=150)

    # 行 6~13 8项指标 (纯片数或/)
    items = [
        ("空洞", "≤25%", "{{VOID_PASS}}", "{{VOID_NG}}"),
        ("桥连", "无桥连", "{{BRIDGE_PASS}}", "{{BRIDGE_NG}}"),
        ("锡球状态", "锡球无缺失，\n大小均匀一致", "{{BALL_PASS}}", "{{BALL_NG}}"),
        ("虚焊", "无虚焊", "{{INSUFF_PASS}}", "{{INSUFF_NG}}"),
        ("偏移", "≤10%", "{{OFFSET_PASS}}", "{{OFFSET_NG}}"),
        ("焊球间隙", "未违反最小电气间隙", "{{GAP_PASS}}", "{{GAP_NG}}"),
        ("透锡率", "100%", "{{THRU_PASS}}", "{{THRU_NG}}"),
        ("多余物", "无多余物", "{{EXTRA_PASS}}", "{{EXTRA_NG}}"),
    ]

    for idx, (item_name, spec, pass_ph, ng_ph) in enumerate(items, start=6):
        row_bg = "F8FAFC" if idx % 2 == 1 else "FFFFFF"
        _fill_cell(tbl.cell(idx, 0), item_name, bold=True, bg=row_bg, color=RGBColor(0x1E, 0x29, 0x3B), pad_v=130)
        _fill_cell(tbl.cell(idx, 1), spec, bg=row_bg, color=RGBColor(0x47, 0x55, 0x69), pad_v=130)
        _fill_cell(tbl.cell(idx, 2), pass_ph, bg=row_bg, color=RGBColor(0x16, 0xA3, 0x4A), bold=True, pad_v=130)
        _fill_cell(tbl.cell(idx, 3), ng_ph, bg=row_bg, color=RGBColor(0xDC, 0x26, 0x26), bold=True, pad_v=130)

    # 行 14 分隔行
    tbl.cell(14, 0).merge(tbl.cell(14, 3))
    _fill_cell(tbl.cell(14, 0), "", bg="F1F5F9", pad_v=40)

    # 行 15 检验结论
    c_concl = tbl.cell(15, 0)
    c_concl.merge(tbl.cell(15, 3))
    set_cell_background(c_concl, "FFFFFF")
    set_cell_margins(c_concl, top=200, bottom=200, left=180, right=180)

    p_concl = c_concl.paragraphs[0]
    p_concl.paragraph_format.space_before = Pt(4)
    p_concl.paragraph_format.space_after = Pt(8)
    r_c_title = p_concl.add_run("检验结论：\n")
    r_c_title.font.bold = True
    r_c_title.font.size = Pt(10.5)
    r_c_title.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)

    r_c_text = p_concl.add_run("    {{INSPECT_CONCLUSION}}")
    r_c_text.font.size = Pt(9.5)
    r_c_text.font.color.rgb = RGBColor(0x33, 0x41, 0x55)

    # 规范宽度
    for row in tbl.rows:
        for idx, w in enumerate(col_widths):
            if idx < len(row.cells):
                row.cells[idx].width = w

    # 底部间距与签字行: 彻底删除“检验员”，只保留右对齐的“检验日期”
    p_space = doc.add_paragraph()
    p_space.paragraph_format.space_before = Pt(28)
    p_space.paragraph_format.space_after = Pt(0)

    p_date = doc.add_paragraph()
    p_date.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_date = p_date.add_run("检验日期: {{INSPECT_DATE}}")
    r_date.font.name = '微软雅黑'
    try:
        r_date._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    except Exception:
        pass
    r_date.font.bold = True
    r_date.font.size = Pt(10)
    r_date.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    doc.save(output_path)
    print(f"[OK] 完美优化版《X 射线检测报告.docx》已生成: {output_path}")


if __name__ == "__main__":
    target = os.path.abspath("docs/X 射线检测报告.docx")
    build_optimized_xray_template(target)
