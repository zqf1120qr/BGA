# -*- coding: utf-8 -*-
"""
🌟 后台异步推理工作线程 (Worker Thread)
----------------------------------------
通过 QThread + 信号槽异步调度深度学习与计算机视觉检测流水线：
1. 绝对避免主 UI 线程出现“未响应 / 白屏”假死；
2. 调度 hardware_sniffer 自适应硬件能力（GPU/CPU）；
3. 支持单张即时检测与多图批量队列并发调度；
4. 支持随时一键安全中断/取消任务。
"""
from __future__ import annotations

import os
import sys
import time
from typing import List, Optional

from PySide6.QtCore import QThread, Signal

# 确保 backend 模块可被导入
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
backend_dir = os.path.join(project_root, "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from bga_pipeline import inspect_bga
from desktop_app.app_config import InspectionConfig
from desktop_app.core.hardware_sniff import hardware_sniffer


class InspectionWorker(QThread):
    """单张 / 批量质检工作线程"""
    sig_started = Signal(str)                  # 当前正在质检的图片路径
    sig_single_finished = Signal(dict)         # 单张质检完成 (携带 result 字典)
    sig_progress = Signal(int, int, str)       # 进度 (当前张数, 总张数, 当前文件名)
    sig_batch_finished = Signal(list)          # 批量完成 (携带全部 result 列表)
    sig_error = Signal(str, str)               # 异常告警 (文件名, 错误描述)
    sig_log = Signal(str)                      # 状态日志

    def __init__(
        self,
        image_paths: List[str],
        config: InspectionConfig,
        parent=None,
    ):
        super().__init__(parent)
        self.image_paths = list(image_paths)
        self.config = config
        self._is_cancelled = False

    def cancel(self):
        """外部请求取消当前任务队列"""
        self._is_cancelled = True
        self.sig_log.emit("🛑 正在停止质检队列...")

    def run(self):
        total = len(self.image_paths)
        if total == 0:
            self.sig_log.emit("⚠️ 待检测图片列表为空")
            return

        # 1. 硬件自适应解析
        target_device, status_text, _ = hardware_sniffer.resolve_device(self.config.hardware_device)
        self.sig_log.emit(f"⚙️ 运算引擎激活: {status_text}")

        results_list = []
        for idx, img_path in enumerate(self.image_paths, start=1):
            if self._is_cancelled:
                self.sig_log.emit("🛑 任务已被用户手动终止")
                break

            fname = os.path.basename(img_path)
            self.sig_started.emit(img_path)
            self.sig_progress.emit(idx, total, fname)
            self.sig_log.emit(f"[{idx}/{total}] 正在质检: {fname} (模式: {self.config.inspection_mode})...")

            t_start = time.time()
            try:
                # 调用核心质检函数
                result = inspect_bga(
                    input_image_path=img_path,
                    weights_path=self.config.weights_path,
                    mode=self.config.inspection_mode,
                    conf_threshold=self.config.conf_threshold,
                    ng_void_threshold=self.config.ng_void_threshold,
                    undersize_threshold=self.config.undersize_threshold,
                    area_reference_mode=self.config.area_reference_mode,
                    device=target_device,
                    save_debug_image=True,
                )
                elapsed_ms = (time.time() - t_start) * 1000.0
                result["elapsed_ms"] = round(elapsed_ms, 1)
                result["input_image_path"] = img_path

                results_list.append(result)
                self.sig_single_finished.emit(result)
                self.sig_log.emit(f"✅ {fname} 完成: {result.get('board_status')} (耗时 {elapsed_ms:.1f}ms)")

            except Exception as e:
                err_msg = str(e)
                self.sig_error.emit(fname, err_msg)
                self.sig_log.emit(f"❌ {fname} 质检失败: {err_msg}")

        self.sig_batch_finished.emit(results_list)
