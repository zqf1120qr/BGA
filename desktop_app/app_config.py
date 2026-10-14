# -*- coding: utf-8 -*-
"""
X射线 桌面工作站配置管理模块 (App Configuration)
"""
from __future__ import annotations
import json
import os
import sys
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
        if getattr(sys, "frozen", False):
            self.base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
            self.app_dir = os.path.dirname(sys.executable)
        else:
            self.desktop_dir = os.path.dirname(os.path.abspath(__file__))
            self.base_dir = os.path.dirname(self.desktop_dir)
            self.app_dir = self.base_dir

        self.config_file = os.path.join(self.app_dir, "settings.json")
        self.config = InspectionConfig()
        
        # 寻找默认权重路径 (优先外部同级目录，回退内部嵌入资源)
        weights_candidates = [
            os.path.join(self.app_dir, "backend", "best.pt"),
            os.path.join(self.app_dir, "best.pt"),
            os.path.join(self.base_dir, "backend", "best.pt"),
            os.path.join(self.base_dir, "best.pt"),
        ]
        for w in weights_candidates:
            if os.path.exists(w):
                self.config.weights_path = os.path.abspath(w)
                break

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

    def save(self) -> bool:
        """保存当前配置到 settings.json"""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config.to_dict(), f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[WARN] 保存配置文件失败: {e}")
            return False

    def save_as_default(self) -> bool:
        """将当前内存中的质检参数保存为最佳默认配置"""
        return self.save()

    def reset_to_defaults(self):
        """恢复系统出厂基准默认质检参数"""
        self.config.conf_threshold = 0.20
        self.config.ng_void_threshold = 0.25
        self.config.undersize_threshold = 0.20
        self.config.inspection_mode = "comprehensive"
        self.config.overlay_alpha = 1.0
        self.config.view_mode = "all_outline"
        self.save()

    def export_recipe_json(self, export_path: str) -> bool:
        """导出当前核心质检判废阈值与配方至指定 JSON 文件"""
        try:
            recipe = {
                "format": "X_RAY_INSPECTOR_RECIPE_V1",
                "description": "X射线芯片智能工业质检工作站 - 工艺阈值配方文件",
                "params": {
                    "conf_threshold": round(float(self.config.conf_threshold), 4),
                    "ng_void_threshold": round(float(self.config.ng_void_threshold), 4),
                    "undersize_threshold": round(float(self.config.undersize_threshold), 4),
                    "inspection_mode": self.config.inspection_mode,
                    "area_reference_mode": self.config.area_reference_mode,
                    "overlay_alpha": round(float(self.config.overlay_alpha), 2),
                    "view_mode": self.config.view_mode,
                }
            }
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(recipe, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[ERROR] 导出参数配方失败: {e}")
            return False

    def import_recipe_json(self, import_path: str) -> bool:
        """从外部 JSON 文件载入工艺阈值配方并验证"""
        try:
            if not os.path.exists(import_path):
                return False
            with open(import_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            params = data.get("params", data)
            if "conf_threshold" in params:
                self.config.conf_threshold = max(0.05, min(0.95, float(params["conf_threshold"])))
            if "ng_void_threshold" in params:
                self.config.ng_void_threshold = max(0.01, min(0.90, float(params["ng_void_threshold"])))
            if "undersize_threshold" in params:
                self.config.undersize_threshold = max(0.01, min(0.90, float(params["undersize_threshold"])))
            if "inspection_mode" in params and params["inspection_mode"] in ("comprehensive", "void", "bridge", "insufficient"):
                self.config.inspection_mode = str(params["inspection_mode"])
            if "overlay_alpha" in params:
                self.config.overlay_alpha = max(0.1, min(1.0, float(params["overlay_alpha"])))
            if "view_mode" in params:
                self.config.view_mode = str(params["view_mode"])

            self.save()
            return True
        except Exception as e:
            print(f"[ERROR] 导入参数配方失败: {e}")
            return False


# 全局单例
app_config_mgr = AppConfigManager()
