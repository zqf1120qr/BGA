# -*- coding: utf-8 -*-
"""
BGA 工业级 PDF 质检单报表生成器
转发至 desktop_app.utils.pdf_reporter 保持统一架构
"""
from desktop_app.utils.pdf_reporter import (
    export_inspection_pdf,
    export_batch_inspection_pdf,
)

__all__ = ["export_inspection_pdf", "export_batch_inspection_pdf"]
