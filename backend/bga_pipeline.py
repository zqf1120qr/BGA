# -*- coding: utf-8 -*-
"""
🌟 BGA 一体化工业质检流水线系统 (BGA Inspection Pipeline)
-------------------------------------------------------------
支持四种清晰独立的质检维度 (模式)：
1. 气泡质检 (Void Only)             : inspect_bga_void()
2. 桥连质检 (Bridge Only)           : inspect_bga_bridge()
3. 虚焊质检 (Insufficient Only)     : inspect_bga_insufficient()
4. 综合质检 (Comprehensive / All)    : inspect_bga_comprehensive() [或 inspect_bga()]
"""
from __future__ import annotations

import os
import sys
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TypedDict

import cv2
import numpy as np

# 保证在 Windows 控制台下正常输出 UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 引入已有检测器与气泡分割模块
from detector import BGADetector, result_to_objects
from utils.grid_node_refiner import (
    GridNodeRefineConfig,
    apply_grid_node_refine_to_result_item,
)
from bga_void_seg import (
    PredictionResult,
    get_detector_instance,
    predict_and_generate_mask,
    COLOR_SOLDER,
    COLOR_VOID_NG,
    COLOR_VOID_PASS,
    COLOR_TEXT_NG,
    COLOR_TEXT_PASS,
    GRID_REFINE_CFG,
    SOLDER_MIN_RADIUS,
)
from bga_bridge_detect import (
    BridgeDefect,
    detect_bga_bridges,
    COLOR_BRIDGE_BOX,
    COLOR_BRIDGE_BALL,
)
from bga_insufficient_detect import (
    InsufficientSolderDefect,
    SolderAreaStats,
    detect_insufficient_solders,
    draw_insufficient_defects,
    COLOR_INSUFFICIENT_BOX,
    COLOR_INSUFFICIENT_RING,
    COLOR_INSUFFICIENT_TEXT,
)


# ==============================================================
# ================= 🌟 [质检模式枚举与数据模型] ==================
# ==============================================================
class InspectionMode(str, Enum):
    VOID = "void"                   # 仅气泡检测
    BRIDGE = "bridge"               # 仅桥连检测
    INSUFFICIENT = "insufficient"   # 仅虚焊检测 (面积比平均值小)
    COMPREHENSIVE = "comprehensive" # 全项综合检测 (气泡 + 桥连 + 虚焊)


class BoardInspectionResult(TypedDict):
    mode: str                                             # 质检模式: "void" | "bridge" | "insufficient" | "comprehensive"
    board_status: str                                     # 整板判定: "PASS" 或 "NG"
    ng_reasons: List[str]                                 # 不合格原因列表
    summary: Dict[str, Any]                               # 汇总统计数据
    void_details: List[PredictionResult]                  # 各焊球气泡详细信息 (仅气泡/综合模式提供)
    bridge_details: List[BridgeDefect]                    # 桥连缺陷详细信息 (仅桥连/综合模式提供)
    insufficient_details: List[InsufficientSolderDefect]  # 虚焊缺陷详细信息 (仅虚焊/综合模式提供)
    visual_output_path: Optional[str]                     # 最终合成质检标注图路径


def _get_safe_output_dir(sub_mode: str) -> str:
    """获取安全的输出目录 (兼容源码模式与 PyInstaller 打包环境)"""
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "output", sub_mode)


def _attach_top_banner_hud(
    vis_img: np.ndarray,
    mode_title: str,
    status: str,
    metrics_text: str,
    banner_h: int = 52,
) -> np.ndarray:
    """
    🌟 在图像上方开辟专属空白仪表板 (Top Banner HUD)，实现对原始图像 0 遮挡：
    - 在图像上方扩展高度为 banner_h 的深灰色仪表带；
    - 左侧配置红/绿状态胶囊标签 (PASS / NG Badge)；
    - 中间显示当前质检维度与指标数值；
    - 底部搭配 2px 分割边线，外观精致整洁。
    """
    h_orig, w_orig = vis_img.shape[:2]
    canvas = cv2.copyMakeBorder(
        vis_img, banner_h, 0, 0, 0, cv2.BORDER_CONSTANT, value=(30, 30, 30)
    )
    is_ng = (status == "NG")
    badge_bg = (0, 0, 220) if is_ng else (0, 180, 0)
    line_color = (0, 0, 200) if is_ng else (0, 180, 0)

    if w_orig >= 760:
        # 宽图 (> 760px): 单行流线型布局
        badge_w, badge_h = 75, 26
        bx, by = 15, 13
        cv2.rectangle(canvas, (bx, by), (bx + badge_w, by + badge_h), badge_bg, -1)
        cv2.putText(canvas, status, (bx + (16 if is_ng else 10), by + 19),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 255), 2, cv2.LINE_AA)

        cv2.putText(canvas, mode_title, (bx + badge_w + 15, by + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, (210, 210, 210), 1, cv2.LINE_AA)

        div_x = bx + badge_w + 175
        cv2.line(canvas, (div_x, by + 4), (div_x, by + badge_h - 4), (80, 80, 80), 1)

        font_scale = 0.40 if len(metrics_text) > 55 else 0.44
        cv2.putText(canvas, metrics_text, (div_x + 15, by + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (240, 240, 240), 1, cv2.LINE_AA)
    else:
        # 中窄图 (<= 760px): 紧凑两行布局，自适应不溢出
        badge_w, badge_h = 60, 20
        bx, by = 10, 6
        cv2.rectangle(canvas, (bx, by), (bx + badge_w, by + badge_h), badge_bg, -1)
        cv2.putText(canvas, status, (bx + (13 if is_ng else 8), by + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

        cv2.putText(canvas, mode_title, (bx + badge_w + 12, by + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (210, 210, 210), 1, cv2.LINE_AA)

        font_scale = 0.36 if len(metrics_text) > 58 else 0.38
        cv2.putText(canvas, metrics_text, (10, 42),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (230, 230, 230), 1, cv2.LINE_AA)

    # 顶部 Banner 与原始图像之间的精致分界线
    cv2.line(canvas, (0, banner_h - 1), (w_orig, banner_h - 1), line_color, 2)
    return canvas


# ==============================================================
# ================= 🌟 [核心质检功能 1: 仅气泡质检] =============
# ==============================================================
def inspect_bga_void(
    input_image_path: str,
    weights_path: str,
    conf_threshold: Optional[float] = None,
    ng_void_threshold: float = 0.25,     # 气泡超标门槛 (默认 25%)
    device: str = "0",
    save_debug_image: bool = True,
    debug_output_dir: Optional[str] = None,
) -> BoardInspectionResult:
    """
    🔍 功能一：BGA 焊球【仅气泡/空洞率】质检 (Void Only Inspection)
    - 专注定位焊球并精确计算单球内部空洞率 (Void Rate)；
    - 不耗费算力进行相邻焊球桥连巡检；
    - 整板判定标准：无任何焊球气泡率超过 ng_void_threshold 则 PASS，否则 NG。
    """
    t_start = time.time()
    if not os.path.exists(input_image_path):
        raise FileNotFoundError(f"未找到输入图片: {input_image_path}")

    img = cv2.imdecode(np.fromfile(input_image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"无法读取图片数据: {input_image_path}")
    vis_img = img.copy() if save_debug_image else None

    # 调用底层气泡分割 (关闭内部写盘，由流水线统一渲染)
    void_results: List[PredictionResult] = predict_and_generate_mask(
        model=weights_path,
        input_image_path=input_image_path,
        conf_threshold=conf_threshold,
        ng_threshold=ng_void_threshold * 100.0,
        device=device,
        save_debug_image=False,
    )

    ng_reasons: List[str] = []
    void_ng_count = 0
    max_void_rate = 0.0

    for idx, item in enumerate(void_results):
        vr = item["void_rate"]
        if vr > max_void_rate:
            max_void_rate = vr
        if vr > ng_void_threshold:
            void_ng_count += 1
            cx, cy = item["solder_circle"]["center"]
            ng_reasons.append(f"焊球 #{idx+1} ({cx:.0f},{cy:.0f}) 气泡率超标: {vr*100:.1f}% > {ng_void_threshold*100:.0f}%")

    board_status = "NG" if void_ng_count > 0 else "PASS"

    summary: Dict[str, Any] = {
        "mode": InspectionMode.VOID.value,
        "board_status": board_status,
        "solder_count": len(void_results),
        "void_pass_count": len(void_results) - void_ng_count,
        "void_ng_count": void_ng_count,
        "max_void_rate": float(max_void_rate),
        "bridge_defect_count": 0,
        "elapsed_ms": round((time.time() - t_start) * 1000, 1),
    }

    out_vis_path = None
    if save_debug_image and vis_img is not None:
        for idx, item in enumerate(void_results):
            cx = int(round(item["solder_circle"]["center"][0]))
            cy = int(round(item["solder_circle"]["center"][1]))
            r = int(round(item["solder_circle"]["radius"]))
            vr = item["void_rate"]
            is_void_ng = vr > ng_void_threshold

            cv2.circle(vis_img, (cx, cy), r, COLOR_SOLDER, 1)
            txt_color = COLOR_TEXT_NG if is_void_ng else COLOR_TEXT_PASS
            cv2.putText(vis_img, f"{vr * 100:.1f}%", (cx - r, max(12, cy - r - 2)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, txt_color, 1, cv2.LINE_AA)

            v_color = COLOR_VOID_NG if is_void_ng else COLOR_VOID_PASS
            for vc in item["void_circle"]:
                vcx, vcy = int(round(vc["center"][0])), int(round(vc["center"][1]))
                vr_px = max(1, int(round(vc["radius"])))
                cv2.circle(vis_img, (vcx, vcy), vr_px, v_color, 1)

        # 在图像上方开辟专属空白状态栏，彻底消除对原始图像的遮挡
        metrics_text = f"Solders: {len(void_results)} | Void-NG: {void_ng_count} | Max-Void: {max_void_rate*100:.1f}%"
        vis_img = _attach_top_banner_hud(vis_img, "VOID ONLY", board_status, metrics_text)

        if debug_output_dir is None:
            debug_output_dir = _get_safe_output_dir("void_only")
        os.makedirs(debug_output_dir, exist_ok=True)
        base_stem = os.path.splitext(os.path.basename(input_image_path))[0]
        out_vis_path = os.path.join(debug_output_dir, f"{base_stem}_void_inspected.jpg")
        cv2.imencode(".jpg", vis_img)[1].tofile(out_vis_path)

    return {
        "mode": InspectionMode.VOID.value,
        "board_status": board_status,
        "ng_reasons": ng_reasons,
        "summary": summary,
        "void_details": void_results,
        "bridge_details": [],
        "insufficient_details": [],
        "visual_output_path": out_vis_path,
    }


# ==============================================================
# ================= 🌟 [核心质检功能 2: 仅桥连质检] =============
# ==============================================================
def inspect_bga_bridge(
    input_image_path: str,
    weights_path: str,
    conf_threshold: Optional[float] = None,
    device: str = "0",
    save_debug_image: bool = True,
    debug_output_dir: Optional[str] = None,
) -> BoardInspectionResult:
    """
    🔍 功能二：BGA 焊球【仅桥连短路】质检 (Bridge Only Inspection)
    - 快速定位焊球后直接执行球间桥连短路巡检；
    - 跳过内部气泡分割算法，速度极快（轻量高效）；
    - 整板判定标准：整板存在 0 处桥连则 PASS，发现任何一处桥连直接判 NG。
    """
    t_start = time.time()
    if not os.path.exists(input_image_path):
        raise FileNotFoundError(f"未找到输入图片: {input_image_path}")

    img = cv2.imdecode(np.fromfile(input_image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"无法读取图片数据: {input_image_path}")
    vis_img = img.copy() if save_debug_image else None

    # 1. 快速定位焊点 (YOLO 推理 + 网格自适应精修)
    detector = get_detector_instance(weights_path=weights_path, device=device)
    item = detector.infer_one(input_image_path)
    refined_item = apply_grid_node_refine_to_result_item(item, cfg=GRID_REFINE_CFG)
    data_list = result_to_objects(refined_item, lowercase_keys=True, include_meta=True)

    solder_points = []
    for idx, d in enumerate(data_list):
        conf = float(d.get("conf", 1.0))
        is_grid_added = bool(d.get("added_by_grid", False) or d.get("recovered_by_grid", False))
        if conf_threshold is not None and not is_grid_added and conf < conf_threshold:
            continue
        r = float(d.get("radius", 0))
        if r < 3.5:
            continue
        solder_points.append({
            "CenterX": float(d.get("center_x", 0)),
            "CenterY": float(d.get("center_y", 0)),
            "Radius": r,
            "draw_radius": float(d.get("draw_radius", r) or r),
            "conf": conf,
            "orig_index": idx
        })

    # 2. 桥连缺陷巡检 (紧凑安全 ROI + 实心小锡球测谎 + 双端边缘连通判定)
    bridge_defects: List[BridgeDefect] = detect_bga_bridges(
        image=img,
        solder_points=solder_points,
        result_img=None,
        draw_on_result=False,
    )

    ng_reasons: List[str] = []
    bridge_count = len(bridge_defects)
    for b_idx, bd in enumerate(bridge_defects):
        ng_reasons.append(
            f"焊球对之间存在桥连短路缺陷 #{b_idx+1} [走向: {bd['orientation']}]: "
            f"小锡球中心: {bd['small_ball'][:2]}, 框: {bd['roi_box']}"
        )

    board_status = "NG" if bridge_count > 0 else "PASS"

    summary: Dict[str, Any] = {
        "mode": InspectionMode.BRIDGE.value,
        "board_status": board_status,
        "solder_count": len(solder_points),
        "void_pass_count": len(solder_points),
        "void_ng_count": 0,
        "max_void_rate": 0.0,
        "bridge_defect_count": bridge_count,
        "elapsed_ms": round((time.time() - t_start) * 1000, 1),
    }

    out_vis_path = None
    if save_debug_image and vis_img is not None:
        # A. 绘制焊球外圈
        for p in solder_points:
            cx, cy = int(round(p["CenterX"])), int(round(p["CenterY"]))
            r = int(round(p.get("draw_radius", p["Radius"])))
            cv2.circle(vis_img, (cx, cy), r, COLOR_SOLDER, 1)

        # B. 绘制桥连缺陷 (红色长方形框 + 黄色小锡球 + BRIDGE 标识)
        for bd in bridge_defects:
            rx, ry, rw, rh = bd["roi_box"]
            cv2.rectangle(vis_img, (rx, ry), (rx + rw, ry + rh), COLOR_BRIDGE_BOX, 1)
            bx, by, br = bd["small_ball"]
            cv2.circle(vis_img, (bx, by), br, COLOR_BRIDGE_BALL, 1)
            cv2.putText(vis_img, "BRIDGE", (rx, max(12, ry - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, COLOR_BRIDGE_BOX, 1, cv2.LINE_AA)

        # 在图像上方开辟专属空白状态栏，彻底消除对原始图像的遮挡
        metrics_text = f"Solders: {len(solder_points)} | Bridges: {bridge_count}"
        vis_img = _attach_top_banner_hud(vis_img, "BRIDGE ONLY", board_status, metrics_text)

        if debug_output_dir is None:
            debug_output_dir = _get_safe_output_dir("bridge_only")
        os.makedirs(debug_output_dir, exist_ok=True)
        base_stem = os.path.splitext(os.path.basename(input_image_path))[0]
        out_vis_path = os.path.join(debug_output_dir, f"{base_stem}_bridge_inspected.jpg")
        cv2.imencode(".jpg", vis_img)[1].tofile(out_vis_path)

    return {
        "mode": InspectionMode.BRIDGE.value,
        "board_status": board_status,
        "ng_reasons": ng_reasons,
        "summary": summary,
        "void_details": [],
        "bridge_details": bridge_defects,
        "insufficient_details": [],
        "visual_output_path": out_vis_path,
    }


# ==============================================================
# ==============================================================
# ================= 🌟 [核心质检功能 3: 仅虚焊/少锡质检] =======
# ==============================================================
def inspect_bga_insufficient(
    input_image_path: str,
    weights_path: str,
    conf_threshold: Optional[float] = None,
    undersize_threshold: float = 0.20,     # 面积比基准小 20% 以上判为虚焊 (默认 20%)
    reference_mode: str = "mean",          # 基准模式: "mean" (算术均值) 或 "median" (稳健中位数)
    device: str = "0",
    save_debug_image: bool = True,
    debug_output_dir: Optional[str] = None,
) -> BoardInspectionResult:
    """
    🔍 功能三：BGA 焊球【仅虚焊/少锡】质检 (Insufficient Solder Only Inspection)
    - 快速定位焊球并提取亚像素真实物理收缩半径与面积；
    - 计算整板焊球基准面积 (支持均值/中位数)，计算面积比率；
    - 整板判定标准：整板存在 0 处虚焊则 PASS，存在任何焊球面积比均值小超过 undersize_threshold 则判 NG。
    """
    t_start = time.time()
    if not os.path.exists(input_image_path):
        raise FileNotFoundError(f"未找到输入图片: {input_image_path}")

    img = cv2.imdecode(np.fromfile(input_image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"无法读取图片数据: {input_image_path}")
    vis_img = img.copy() if save_debug_image else None

    # 1. 快速定位焊点并经由亚像素梯度通量精修真实半径
    void_results: List[PredictionResult] = predict_and_generate_mask(
        model=weights_path,
        input_image_path=input_image_path,
        conf_threshold=conf_threshold,
        device=device,
        save_debug_image=False,
    )

    # 2. 虚焊缺陷巡检 (统计基准均值与相对缩小百分比)
    insufficient_defects, area_stats = detect_insufficient_solders(
        solder_points=void_results,
        undersize_threshold=undersize_threshold,
        reference_mode=reference_mode,
    )

    ng_reasons: List[str] = []
    insufficient_count = len(insufficient_defects)
    for defect in insufficient_defects:
        cx, cy = defect["center"]
        ng_reasons.append(
            f"焊球 #{defect['solder_index']} ({cx:.0f},{cy:.0f}) 面积严重偏小 (虚焊/少锡): "
            f"{defect['area']:.1f}px² < 均值 {defect['reference_area']:.1f}px² (缩小 -{defect['reduction_percent']:.1f}%)"
        )

    board_status = "NG" if insufficient_count > 0 else "PASS"

    summary: Dict[str, Any] = {
        "mode": InspectionMode.INSUFFICIENT.value,
        "board_status": board_status,
        "solder_count": len(void_results),
        "void_pass_count": len(void_results),
        "void_ng_count": 0,
        "max_void_rate": 0.0,
        "bridge_defect_count": 0,
        "insufficient_solder_count": insufficient_count,
        "mean_solder_area": area_stats["mean_area"],
        "median_solder_area": area_stats["median_area"],
        "max_reduction_percent": round(max([d["reduction_percent"] for d in insufficient_defects], default=0.0), 1),
        "elapsed_ms": round((time.time() - t_start) * 1000, 1),
    }

    out_vis_path = None
    if save_debug_image and vis_img is not None:
        # A. 绘制常规焊球轮廓 (绿色)
        for v in void_results:
            sc = v["solder_circle"]
            cx, cy = int(round(sc["center"][0])), int(round(sc["center"][1]))
            r = int(round(sc["radius"]))
            cv2.circle(vis_img, (cx, cy), r, COLOR_SOLDER, 1)

        # B. 绘制虚焊缺陷 (橙色双圈 + 矩形框 + 缩减百分比)
        vis_img = draw_insufficient_defects(vis_img, insufficient_defects, draw_box=True, draw_label=True)

        # C. 顶部 Banner HUD 看板 (0 遮挡)
        metrics_text = (
            f"Solders: {len(void_results)} | Undersize-NG: {insufficient_count} | "
            f"Mean-Area: {area_stats['mean_area']:.0f}px² | Max-Red: {summary['max_reduction_percent']:.1f}%"
        )
        vis_img = _attach_top_banner_hud(vis_img, "UNDERSIZE ONLY", board_status, metrics_text)

        if debug_output_dir is None:
            debug_output_dir = _get_safe_output_dir("insufficient_only")
        os.makedirs(debug_output_dir, exist_ok=True)
        base_stem = os.path.splitext(os.path.basename(input_image_path))[0]
        out_vis_path = os.path.join(debug_output_dir, f"{base_stem}_insufficient_inspected.jpg")
        cv2.imencode(".jpg", vis_img)[1].tofile(out_vis_path)

    return {
        "mode": InspectionMode.INSUFFICIENT.value,
        "board_status": board_status,
        "ng_reasons": ng_reasons,
        "summary": summary,
        "void_details": [],
        "bridge_details": [],
        "insufficient_details": insufficient_defects,
        "visual_output_path": out_vis_path,
    }


# ==============================================================
# ================= 🌟 [核心质检功能 4: 全项综合质检] ===========
# ==============================================================
def inspect_bga_comprehensive(
    input_image_path: str,
    weights_path: str,
    conf_threshold: Optional[float] = None,
    ng_void_threshold: float = 0.25,     # 气泡超标门槛 (默认 25%)
    undersize_threshold: float = 0.20,   # 虚焊面积缩减门槛 (默认 20%)
    area_reference_mode: str = "mean",    # 虚焊基准模式: "mean" 或 "median"
    device: str = "0",
    save_debug_image: bool = True,
    debug_output_dir: Optional[str] = None,
) -> BoardInspectionResult:
    """
    🔍 功能四：BGA 全项【气泡 + 桥连 + 虚焊】综合质检 (Comprehensive Inspection)
    - 一站式同步执行焊球定位、气泡空洞率分割、球间桥连检测与虚焊面积巡检；
    - 算力高效复用：YOLO 目标检测仅推理 1 次；
    - 整板三重综合判定：气泡率超标 OR 存在桥连短路缺陷 OR 焊球面积严重偏小 (虚焊)，直接判定为 NG；
    - 多图层全景可视化：绿圈焊球 + 红/黄气泡圈 + 红框桥连 + 橙框/双圈虚焊 + 工业 HUD 看板。
    """
    t_start = time.time()
    if not os.path.exists(input_image_path):
        raise FileNotFoundError(f"未找到输入图片: {input_image_path}")

    img = cv2.imdecode(np.fromfile(input_image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"无法读取图片数据: {input_image_path}")
    vis_img = img.copy() if save_debug_image else None

    # 1. 气泡与焊球定位 (内部高精度亚像素拟合真实收缩半径)
    void_results: List[PredictionResult] = predict_and_generate_mask(
        model=weights_path,
        input_image_path=input_image_path,
        conf_threshold=conf_threshold,
        ng_threshold=ng_void_threshold * 100.0,
        device=device,
        save_debug_image=False,
    )

    # 2. 桥连缺陷巡检
    solder_points = []
    for idx, v_item in enumerate(void_results):
        sc = v_item["solder_circle"]
        solder_points.append({
            "CenterX": sc["center"][0],
            "CenterY": sc["center"][1],
            "Radius": sc["radius"],
            "draw_radius": sc["radius"],
            "conf": v_item.get("confidence", 1.0),
            "orig_index": idx
        })

    bridge_defects: List[BridgeDefect] = detect_bga_bridges(
        image=img,
        solder_points=solder_points,
        result_img=None,
        draw_on_result=False,
    )

    # 3. 虚焊缺陷巡检 (全面复用高精度精修半径)
    insufficient_defects, area_stats = detect_insufficient_solders(
        solder_points=void_results,
        undersize_threshold=undersize_threshold,
        reference_mode=area_reference_mode,
    )

    # 4. 三重综合判定与归因
    ng_reasons: List[str] = []
    void_ng_count = 0
    max_void_rate = 0.0
    for idx, item in enumerate(void_results):
        vr = item["void_rate"]
        if vr > max_void_rate:
            max_void_rate = vr
        if vr > ng_void_threshold:
            void_ng_count += 1
            cx, cy = item["solder_circle"]["center"]
            ng_reasons.append(f"焊球 #{idx+1} ({cx:.0f},{cy:.0f}) 气泡率超标: {vr*100:.1f}% > {ng_void_threshold*100:.0f}%")

    bridge_count = len(bridge_defects)
    for b_idx, bd in enumerate(bridge_defects):
        ng_reasons.append(
            f"焊球对之间存在桥连短路缺陷 #{b_idx+1} [走向: {bd['orientation']}]: "
            f"小锡球中心: {bd['small_ball'][:2]}, 框: {bd['roi_box']}"
        )

    insufficient_count = len(insufficient_defects)
    for defect in insufficient_defects:
        cx, cy = defect["center"]
        ng_reasons.append(
            f"焊球 #{defect['solder_index']} ({cx:.0f},{cy:.0f}) 面积严重偏小 (虚焊/少锡): "
            f"{defect['area']:.1f}px² < 均值 {defect['reference_area']:.1f}px² (缩小 -{defect['reduction_percent']:.1f}%)"
        )

    board_status = "NG" if (void_ng_count > 0 or bridge_count > 0 or insufficient_count > 0) else "PASS"

    summary: Dict[str, Any] = {
        "mode": InspectionMode.COMPREHENSIVE.value,
        "board_status": board_status,
        "solder_count": len(void_results),
        "void_pass_count": len(void_results) - void_ng_count,
        "void_ng_count": void_ng_count,
        "max_void_rate": float(max_void_rate),
        "bridge_defect_count": bridge_count,
        "insufficient_solder_count": insufficient_count,
        "mean_solder_area": area_stats["mean_area"],
        "median_solder_area": area_stats["median_area"],
        "max_reduction_percent": round(max([d["reduction_percent"] for d in insufficient_defects], default=0.0), 1),
        "elapsed_ms": round((time.time() - t_start) * 1000, 1),
    }

    # 5. 多图层全景可视化合成
    out_vis_path = None
    if save_debug_image and vis_img is not None:
        # A. 焊球与气泡
        for idx, item in enumerate(void_results):
            cx = int(round(item["solder_circle"]["center"][0]))
            cy = int(round(item["solder_circle"]["center"][1]))
            r = int(round(item["solder_circle"]["radius"]))
            vr = item["void_rate"]
            is_void_ng = vr > ng_void_threshold

            cv2.circle(vis_img, (cx, cy), r, COLOR_SOLDER, 1)
            txt_color = COLOR_TEXT_NG if is_void_ng else COLOR_TEXT_PASS
            cv2.putText(vis_img, f"{vr * 100:.1f}%", (cx - r, max(12, cy - r - 2)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, txt_color, 1, cv2.LINE_AA)

            v_color = COLOR_VOID_NG if is_void_ng else COLOR_VOID_PASS
            for vc in item["void_circle"]:
                vcx, vcy = int(round(vc["center"][0])), int(round(vc["center"][1]))
                vr_px = max(1, int(round(vc["radius"])))
                cv2.circle(vis_img, (vcx, vcy), vr_px, v_color, 1)

        # B. 桥连缺陷 (红色框 + 黄色小球)
        for bd in bridge_defects:
            rx, ry, rw, rh = bd["roi_box"]
            cv2.rectangle(vis_img, (rx, ry), (rx + rw, ry + rh), COLOR_BRIDGE_BOX, 1)
            bx, by, br = bd["small_ball"]
            cv2.circle(vis_img, (bx, by), br, COLOR_BRIDGE_BALL, 1)
            cv2.putText(vis_img, "BRIDGE", (rx, max(12, ry - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, COLOR_BRIDGE_BOX, 1, cv2.LINE_AA)

        # C. 虚焊缺陷 (橙色外框 + 双圈 + 负缩减比例标签)
        vis_img = draw_insufficient_defects(vis_img, insufficient_defects, draw_box=True, draw_label=True)

        # D. 顶部空白状态栏 HUD 看板 (四项全景统计指标)
        metrics_text = (
            f"Solders: {len(void_results)} | Void-NG: {void_ng_count} | Bridges: {bridge_count} | Undersize: {insufficient_count}"
        )
        vis_img = _attach_top_banner_hud(vis_img, "COMPREHENSIVE", board_status, metrics_text)

        if debug_output_dir is None:
            debug_output_dir = _get_safe_output_dir("comprehensive")
        os.makedirs(debug_output_dir, exist_ok=True)
        base_stem = os.path.splitext(os.path.basename(input_image_path))[0]
        out_vis_path = os.path.join(debug_output_dir, f"{base_stem}_all_inspected.jpg")
        cv2.imencode(".jpg", vis_img)[1].tofile(out_vis_path)

    return {
        "mode": InspectionMode.COMPREHENSIVE.value,
        "board_status": board_status,
        "ng_reasons": ng_reasons,
        "summary": summary,
        "void_details": void_results,
        "bridge_details": bridge_defects,
        "insufficient_details": insufficient_defects,
        "visual_output_path": out_vis_path,
    }


# ==============================================================
# ================= 🌟 [统一总入口函数] =========================
# ==============================================================
def inspect_bga(
    input_image_path: str,
    weights_path: str,
    mode: str = "comprehensive",          # 可选: "comprehensive"(综合) | "void"(仅气泡) | "bridge"(仅桥连) | "insufficient"(仅虚焊)
    conf_threshold: Optional[float] = None,
    ng_void_threshold: float = 0.25,
    undersize_threshold: float = 0.20,
    area_reference_mode: str = "mean",
    device: str = "0",
    save_debug_image: bool = True,
    debug_output_dir: Optional[str] = None,
) -> BoardInspectionResult:
    """
    🌟 BGA 质检统一总入口 (支持 mode 切换):
    - mode="comprehensive" (默认): 全项综合质检 (气泡 + 桥连 + 虚焊)
    - mode="void": 仅气泡质检
    - mode="bridge": 仅桥连质检
    - mode="insufficient" (或 "undersize"): 仅虚焊/少锡质检
    """
    clean_mode = str(mode).strip().lower()
    if clean_mode in ("void", "void_only"):
        return inspect_bga_void(
            input_image_path=input_image_path,
            weights_path=weights_path,
            conf_threshold=conf_threshold,
            ng_void_threshold=ng_void_threshold,
            device=device,
            save_debug_image=save_debug_image,
            debug_output_dir=debug_output_dir,
        )
    elif clean_mode in ("bridge", "bridge_only"):
        return inspect_bga_bridge(
            input_image_path=input_image_path,
            weights_path=weights_path,
            conf_threshold=conf_threshold,
            device=device,
            save_debug_image=save_debug_image,
            debug_output_dir=debug_output_dir,
        )
    elif clean_mode in ("insufficient", "insufficient_only", "undersize", "undersize_only"):
        return inspect_bga_insufficient(
            input_image_path=input_image_path,
            weights_path=weights_path,
            conf_threshold=conf_threshold,
            undersize_threshold=undersize_threshold,
            reference_mode=area_reference_mode,
            device=device,
            save_debug_image=save_debug_image,
            debug_output_dir=debug_output_dir,
        )
    else:  # 默认 comprehensive
        return inspect_bga_comprehensive(
            input_image_path=input_image_path,
            weights_path=weights_path,
            conf_threshold=conf_threshold,
            ng_void_threshold=ng_void_threshold,
            undersize_threshold=undersize_threshold,
            area_reference_mode=area_reference_mode,
            device=device,
            save_debug_image=save_debug_image,
            debug_output_dir=debug_output_dir,
        )


# 向后兼容别名 (保持旧代码调用不报错)
inspect_bga_board = inspect_bga_comprehensive

