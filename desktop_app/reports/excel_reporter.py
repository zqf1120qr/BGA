# -*- coding: utf-8 -*-
"""
BGA 质检数据 Excel 结构化报表生成器
转发至 desktop_app.utils.excel_reporter 保持统一架构
"""
from desktop_app.utils.excel_reporter import (
    export_inspection_excel,
    export_batch_inspection_excel,
)

__all__ = ["export_inspection_excel", "export_batch_inspection_excel"]
