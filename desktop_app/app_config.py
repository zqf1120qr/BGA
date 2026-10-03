# -*- coding: utf-8 -*-
"""
🌟 BGA 桌面工作站配置管理模块 (App Configuration)
"""
from __future__ import annotations
import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass
class InspectionConfig:
    weights_path: str = ""
    conf_threshold: float = 0.20
    ng_void_threshold: float = 0.25
    undersize_threshold: float = 0.20
    area_reference_mode: str = "mean"
    inspection_mode: str = "comprehensive"  # "comprehensive" | "void" | "bridge" | "insufficient"
    hardware_device: str = "auto"           # "auto" | "0" (GPU) | "cpu"
    overlay_alpha: float = 1.0              # 标注透明度 0.1 ~ 1.0 (默认 100%)
    view_mode: str = "all_outline"          # "all_outline" (全部细轮廓) | "defect_only" (仅高亮缺陷) | "raw_image" (纯原图)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AppConfigManager:
    """管理并持久化桌面端配置"""
    def __init__(self):
        self.desktop_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.dirname(self.desktop_dir)
        self.config_file = os.path.join(self.desktop_dir, "settings.json")
        self.config = InspectionConfig()
        
        # 默认权重路径
        default_weights = os.path.join(self.project_root, "backend", "best.pt")
        if os.path.exists(default_weights):
            self.config.weights_path = default_weights

        self.load()

    def load(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if hasattr(self.config, k):
                            setattr(self.config, k, v)
            except Exception as e:
                print(f"[WARN] 读取配置文件失败: {e}")

    def save(self):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WARN] 保存配置文件失败: {e}")


# 全局单例
app_config_mgr = AppConfigManager()
