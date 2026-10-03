# -*- coding: utf-8 -*-
"""
🌟 BGA 焊球虚焊/少锡缺陷高精度检测模块 (BGA Insufficient Solder Detection Module)
-------------------------------------------------------------------------
设计定位:
1. 独立纯算法模块，与气泡分割、桥连检测解耦；
2. 工业物理依据:
   - 在 X 射线透射 (X-Ray) 图像中，BGA 焊球在正常回流焊接后应均匀坍塌形成饱满圆球，投影面积高度稳定一致；
   - 当发生锡膏印刷不足、引脚翘曲不平或冷焊润湿不良时，焊球无法充分坍落或严重少锡，其 2D 投影面积显著萎缩；
3. 科学量化判据:
   - 提取各焊球亚像素物理收缩半径与投影面积: Area = π * r^2；
   - 计算整板正常焊球基准面积 (支持算术均值 Mean 与稳健中位数 Median)；
   - 面积相对比率 R = Area / Area_ref；
   - 当面积缩小幅度超过设定阈值 (例如比均值小 20% 以上，即 R < 0.80) 时，判定为虚焊/少锡缺陷。
"""
from __future__ import annotations

import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple, TypedDict

import cv2
import numpy as np

# 保证在 Windows 控制台下正常输出 UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


# ==============================================================
# ================= 🌟 [数据模型定义] 对齐接口规范 =================
# ==============================================================
class InsufficientSolderDefect(TypedDict):
    solder_index: int                       # 焊球在整板中的编号 (1-based)
    center: Tuple[float, float]             # 焊球圆心坐标 (x, y)
    radius: float                           # 焊球实测半径 (px)
    area: float                             # 焊球实测投影面积 (px^2)
    reference_area: float                   # 整板基准参考面积 (px^2)
    area_ratio: float                       # 相对参考面积的比例 (如 0.748 即 74.8%)
    reduction_percent: float                # 相比均值缩小的百分比 (如 25.2%)
    roi_box: Tuple[int, int, int, int]      # 焊球包围框 (x, y, w, h)
    confidence: float                       # 焊点置信度


class SolderAreaStats(TypedDict):
    total_solders: int                      # 有效焊球总数
    mean_radius: float                      # 平均半径
    median_radius: float                    # 中位数半径
    mean_area: float                        # 平均面积 (px^2)
    median_area: float                      # 中位数面积 (px^2)
    min_area: float                         # 最小焊球面积
    max_area: float                         # 最大焊球面积
    std_area: float                         # 面积标准差
    reference_area: float                   # 最终选用的基准参考面积
    reference_mode: str                     # 基准计算模式 ("mean" 或 "median")
    undersize_threshold: float              # 判定的缩小比例阈值 (如 0.20)


# 可视化标注颜色 (BGR 格式: 醒目亮橙色，与绿焊盘、红/黄气泡、红色桥连形成清晰区分)
COLOR_INSUFFICIENT_BOX = (0, 140, 255)    # 亮橙色
COLOR_INSUFFICIENT_TEXT = (0, 140, 255)   # 亮橙色
COLOR_INSUFFICIENT_RING = (0, 100, 255)   # 橙红圈


def _normalize_solder_inputs(solder_inputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    统一焊球输入数据格式，兼容:
    1. bga_void_seg.py 的 PredictionResult 字典 (包含 solder_circle.center, solder_circle.radius)；
    2. detector.py 的 PointDict (包含 CenterX, CenterY, Radius, draw_radius, conf 等)；
    3. 标称坐标 json 字典或标准点位字典。
    """
    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(solder_inputs):
        # 提取中心坐标与半径
        if "solder_circle" in item and isinstance(item["solder_circle"], dict):
            sc = item["solder_circle"]
            cx = float(sc["center"][0])
            cy = float(sc["center"][1])
            r = float(sc["radius"])
            conf = float(item.get("confidence", 1.0))
        else:
            cx = float(item.get("CenterX", item.get("center_x", item.get("x", 0.0))))
            cy = float(item.get("CenterY", item.get("center_y", item.get("y", 0.0))))
            # 优先使用真实拟合半径 Radius，若无则使用 draw_radius
            raw_r = float(item.get("radius", item.get("Radius", 0.0)) or 0.0)
            draw_r = float(item.get("draw_radius", item.get("DrawRadius", 0.0)) or 0.0)
            if raw_r >= 3.0:
                r = raw_r
            elif draw_r >= 3.0:
                r = draw_r
            else:
                w = float(item.get("w", item.get("Width", 0.0)) or 0.0)
                h = float(item.get("h", item.get("Height", 0.0)) or 0.0)
                r = (w + h) / 4.0 if (w > 0 and h > 0) else 0.0
            conf = float(item.get("conf", item.get("confidence", 1.0)))

        if r < 3.0:
            continue

        normalized.append({
            "index": idx + 1,
            "x": cx,
            "y": cy,
            "r": r,
            "area": float(np.pi * (r ** 2)),
            "conf": conf,
            "raw_item": item,
        })
    return normalized


def detect_insufficient_solders(
    solder_points: List[Dict[str, Any]],
    undersize_threshold: float = 0.20,
    reference_mode: str = "mean",
    min_solder_count: int = 4,
) -> Tuple[List[InsufficientSolderDefect], SolderAreaStats]:
    """
    🌟 BGA 焊球虚焊/少锡缺陷高精度检测核心函数
    
    参数:
        solder_points: 焊球列表 (支持 detector 字典列表或 PredictionResult 列表)
        undersize_threshold: 判定门槛比例 (默认 0.20，即面积比基准均值小 20% 以上判定为虚焊)
        reference_mode: 基准计算方式，可选:
            - "mean": 算术均值 (严格契合“面积比平均值小”的标准工业定义)
            - "median": 稳健中位数 (抗极端异形球干扰)
        min_solder_count: 参与统计分析的最小焊球数量门槛 (少于此值不执行统计判定)
        
    返回:
        (defects, stats): 
        - defects: 检出的 InsufficientSolderDefect 列表
        - stats: 焊球面积与半径的整板统计字典
    """
    norm_balls = _normalize_solder_inputs(solder_points)
    
    if len(norm_balls) < min_solder_count:
        empty_stats: SolderAreaStats = {
            "total_solders": len(norm_balls),
            "mean_radius": 0.0,
            "median_radius": 0.0,
            "mean_area": 0.0,
            "median_area": 0.0,
            "min_area": 0.0,
            "max_area": 0.0,
            "std_area": 0.0,
            "reference_area": 0.0,
            "reference_mode": reference_mode,
            "undersize_threshold": undersize_threshold,
        }
        return [], empty_stats

    radii = np.array([b["r"] for b in norm_balls], dtype=np.float64)
    areas = np.array([b["area"] for b in norm_balls], dtype=np.float64)

    mean_r = float(np.mean(radii))
    med_r = float(np.median(radii))
    mean_a = float(np.mean(areas))
    med_a = float(np.median(areas))
    min_a = float(np.min(areas))
    max_a = float(np.max(areas))
    std_a = float(np.std(areas))

    # 根据设定选取基准参考面积
    if reference_mode.lower() == "median":
        ref_area = med_a
    else:
        ref_area = mean_a

    stats: SolderAreaStats = {
        "total_solders": len(norm_balls),
        "mean_radius": round(mean_r, 2),
        "median_radius": round(med_r, 2),
        "mean_area": round(mean_a, 2),
        "median_area": round(med_a, 2),
        "min_area": round(min_a, 2),
        "max_area": round(max_a, 2),
        "std_area": round(std_a, 2),
        "reference_area": round(ref_area, 2),
        "reference_mode": reference_mode,
        "undersize_threshold": undersize_threshold,
    }

    defects: List[InsufficientSolderDefect] = []
    # 虚焊判定阈值: 面积比率下限
    ratio_cutoff = 1.0 - float(undersize_threshold)

    for b in norm_balls:
        ball_area = b["area"]
        ratio = float(ball_area / ref_area) if ref_area > 0 else 1.0

        if ratio < ratio_cutoff:
            reduction_pct = (1.0 - ratio) * 100.0
            cx, cy = b["x"], b["y"]
            r = b["r"]
            pad = int(math.ceil(r + 3))
            rx = int(round(cx - pad))
            ry = int(round(cy - pad))
            rw = pad * 2
            rh = pad * 2

            defect: InsufficientSolderDefect = {
                "solder_index": b["index"],
                "center": (cx, cy),
                "radius": round(r, 2),
                "area": round(ball_area, 1),
                "reference_area": round(ref_area, 1),
                "area_ratio": round(ratio, 4),
                "reduction_percent": round(reduction_pct, 1),
                "roi_box": (rx, ry, rw, rh),
                "confidence": b["conf"],
            }
            defects.append(defect)

    return defects, stats


def draw_insufficient_defects(
    vis_img: np.ndarray,
    defects: List[InsufficientSolderDefect],
    draw_box: bool = True,
    draw_label: bool = True,
) -> np.ndarray:
    """
    在可视化图像上绘制虚焊缺陷标记:
    - 橙色圆环/方框标定异常偏小焊球；
    - 顶部清晰打上缩减百分比标签 (如 '-25.2%') 与 'UNDERSIZE' 文本；
    - 设计风格对齐气泡与桥连标记，互不遮挡干扰。
    """
    if vis_img is None or not defects:
        return vis_img

    h_img, w_img = vis_img.shape[:2]

    for d in defects:
        cx, cy = int(round(d["center"][0])), int(round(d["center"][1]))
        r = int(round(d["radius"]))
        red_pct = d["reduction_percent"]

        # 1. 绘制虚焊专属橙色外标圆圈 (双圈突出显示)
        cv2.circle(vis_img, (cx, cy), r + 3, COLOR_INSUFFICIENT_RING, 1, cv2.LINE_AA)

        # 2. 绘制焊球外矩形指示框 (可选)
        if draw_box:
            rx, ry, rw, rh = d["roi_box"]
            rx_clamped = max(0, rx)
            ry_clamped = max(0, ry)
            rw_clamped = min(w_img - rx_clamped, rw)
            rh_clamped = min(h_img - ry_clamped, rh)
            cv2.rectangle(
                vis_img,
                (rx_clamped, ry_clamped),
                (rx_clamped + rw_clamped, ry_clamped + rh_clamped),
                COLOR_INSUFFICIENT_BOX,
                1,
                cv2.LINE_AA,
            )

        # 3. 标注缩减比例文字标签
        if draw_label:
            label_text = f"-{red_pct:.1f}%"
            # 放置在焊球下方偏左，避免与上方的气泡百分比文字重叠
            ty = min(h_img - 4, cy + r + 13)
            tx = max(2, cx - r - 4)
            cv2.putText(
                vis_img,
                label_text,
                (tx, ty),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.32,
                COLOR_INSUFFICIENT_TEXT,
                1,
                cv2.LINE_AA,
            )

    return vis_img
