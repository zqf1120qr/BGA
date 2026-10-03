# -*- coding: utf-8 -*-
"""
🌟 工厂硬件智能感知与自适应降级模块 (Hardware Sniffer)
------------------------------------------------------
解决工厂机台“无独显 / 仅核显 / CPU 模式”下的硬件兼容性问题：
1. 自动探测 NVIDIA CUDA 支持情况；
2. 支持 GPU -> CPU 无感平滑降级，绝不因断言报错；
3. CPU 模式下自动激活多线程并行并发优化；
4. 向主界面提供可视化状态字符串与指示灯颜色。
"""
from __future__ import annotations

import os
import platform
from typing import Tuple
import torch


class HardwareSniffer:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_hardware()
        return cls._instance

    def _init_hardware(self):
        self.has_cuda = torch.cuda.is_available()
        self.gpu_count = torch.cuda.device_count() if self.has_cuda else 0
        self.gpu_name = ""
        self.gpu_memory_gb = 0.0

        if self.has_cuda and self.gpu_count > 0:
            try:
                props = torch.cuda.get_device_properties(0)
                self.gpu_name = props.name
                self.gpu_memory_gb = round(props.total_memory / (1024 ** 3), 1)
            except Exception:
                self.gpu_name = "NVIDIA CUDA Device"

        self.cpu_cores = os.cpu_count() or 4
        self.cpu_arch = platform.processor() or "x86_64"

        # 若在 CPU 模式，默认启用全核多线程并发
        if not self.has_cuda:
            try:
                torch.set_num_threads(self.cpu_cores)
            except Exception:
                pass

    def resolve_device(self, user_preference: str = "auto") -> Tuple[str, str, str]:
        """
        根据用户偏好与实际硬件解析最终使用的推理设备。
        :param user_preference: "auto" | "0" (GPU) | "cpu"
        :return: (target_device_str, status_text, status_color)
                 status_color: "green" (GPU) | "yellow" (CPU正常) | "orange" (降级警示)
        """
        pref = str(user_preference).strip().lower()

        if pref == "auto":
            if self.has_cuda:
                return (
                    "0",
                    f"GPU 加速已就绪: {self.gpu_name} ({self.gpu_memory_gb}GB)",
                    "#22c55e"  # 绿色
                )
            else:
                return (
                    "cpu",
                    f"CPU 多核模式: {self.cpu_cores} 核并发 (硬件无独显自动适配)",
                    "#eab308"  # 黄色
                )

        elif pref in ("0", "gpu", "cuda"):
            if self.has_cuda:
                return (
                    "0",
                    f"GPU 强制指定: {self.gpu_name}",
                    "#22c55e"
                )
            else:
                # 关键防护：工厂电脑无独显但配置了 GPU 时，平滑降级，绝不崩溃
                return (
                    "cpu",
                    f"未检测到独显，已安全降级至 CPU ({self.cpu_cores}核)",
                    "#f97316"  # 橙色预警
                )

        else:  # "cpu"
            return (
                "cpu",
                f"CPU 纯处理器模式 ({self.cpu_cores}核)",
                "#94a3b8"  # 灰色/静默蓝
            )


# 单例
hardware_sniffer = HardwareSniffer()
