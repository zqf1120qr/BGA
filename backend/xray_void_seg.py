import sys
import os
import math
import concurrent.futures
import cv2
import numpy as np
from typing import TypedDict, List, Optional

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 引入检测模型的接口 (确保 detector.py 与 grid_node_refiner 可正常导入)
try:
    from detector import BGADetector, result_to_objects
    from utils.grid_node_refiner import (
        GridNodeRefineConfig,
        apply_grid_node_refine_to_result_item
    )
except ImportError:
    print("[WARNING] 未找到 detector 模块，请确保项目结构正确或其在系统路径下。")

def _get_safe_debug_out_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "debug_out")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_out")

# ==============================================================
# ================= 🌟 [数据模型定义] 对齐后端接口 =================
# ==============================================================
class Circle(TypedDict):
    center: tuple[float, float] # 圆心: (x, y) 坐标
    radius: float               # 半径

class PredictionResult(TypedDict):
    image_size: tuple[int, int]      # 图片尺寸: (width, height)
    solder_circle: Circle            # 焊盘圆
    void_circle: list[Circle]        # 空洞圆
    void_rate: float                 # 空洞率: 0.0 ~ 1.0 (如 0.3)
    confidence: float                # 置信度: 0.0 ~ 1.0

# ==============================================================
# ================= 🌟 [调参配置区] 核心阈值字典 =================
# ==============================================================

# --- [A] 焊点过滤与定位参数 ---
SOLDER_MIN_RADIUS = 5           # (像素) 最小允许的 YOLO 焊点半径。小于此值直接作为噪点忽略。
FAKE_HOLE_TOLERANCE = 1.0       # (倍数) 假孔拦截宽容度 (基于全局大津法)。
DONUT_OUTER_RATIO = 0.9         # (比例) 甜甜圈测光法的外圈半径比例。
DONUT_INNER_RATIO = 0.5         # (比例) 甜甜圈测光法的挖空内圈半径比例。
CUT_MASK_RATIO = 1.05           # (比例) 物理剪刀范围。用于切除外部走线。
SOLDER_SHRINK_RATIO = 0.98      # (比例) 焊球外圈收缩系数，严格紧贴焊点真实轮廓，禁止向外扩张。
SAFE_ZONE_RATIO = 0.84          # (比例) 气泡搜索物理核心安全区。放宽至0.84挽救真实边缘气泡，内切算法保证绝不溢出。

# --- [B] 气泡提取与形态学参数 (Recall 优先，同时杜绝假大圆与重叠乱圈) ---
TOPHAT_KERNEL_RATIO = 1.5       # (倍数) 顶帽变换内核比例。
MIN_TOPHAT_KERNEL = 11          # (像素) 顶帽变换内核的最小绝对尺寸。
DEFAULT_VOID_THRESH_OFFSET = 7.0 # (亮度值) 默认气泡门槛基准偏移量 (将由图像噪声与直方图自适应动态调谐)。
MIN_VOID_AREA = 2               # (像素) 最小气泡面积。挽救微小真实微孔。
MAX_VOID_AREA_RATIO = 0.25      # (比例) 单个气泡连通域占焊球最大面积比例 (防止大面积亮斑误分割)。
MIN_VOID_SOLIDITY = 0.28        # (比例 0~1) 坚实度门槛。
MIN_VOID_DENSITY = 0.38         # (比例 0~1) 轮廓内部像素密度 (彻底消除中空环状外包轮廓)。
VOID_RADIUS_COMP = 1.02         # (倍数) 气泡红圈拟合补偿系数。
MAX_VOID_RADIUS_RATIO = 0.50    # (比例) 气泡最大半径相对焊球半径上限 (GT 最大 0.56，99%分位 0.42)。
MAX_VOID_RADIUS_ABSOLUTE = 15.0 # (像素) 气泡绝对最大物理半径 (GT 最大仅 11.4px)。

# --- [C] 绘制与颜色参数 (BGR 格式) ---
COLOR_SOLDER = (0, 255, 0)        # 焊点外圈颜色 (绿色)
COLOR_VOID_NG = (0, 0, 255)       # 气泡圈颜色 - 占比超标 NG (红色)
COLOR_VOID_PASS = (0, 255, 255)   # 气泡圈颜色 - 占比正常 PASS (黄色)
COLOR_TEXT_NG = (0, 0, 255)       # 文本颜色 - NG (红色)
COLOR_TEXT_PASS = (0, 255, 0)     # 文本颜色 - PASS (绿色)

NG_RATIO_THRESH = 25.0          # NG 判定阈值百分比

# --- [D] 网格节点优化配置 ---
GRID_REFINE_CFG = GridNodeRefineConfig(
    enable_multi_grid=True,
    forbid_add_on_grid_boundary=True,
    forbid_add_boundary_margin=1,
    disable_large_gap_add_on_boundary=True,
    use_dark_blob_evidence=True,
    require_add_visual_evidence=True,
    add_require_blob=True,
    add_require_solid_evidence=True,
    enable_void_mask=True,
    use_solid_evidence_for_void=True,
    void_min_component_nodes=6,
    void_min_span_rows=2,
    void_min_span_cols=2,
    void_dilate_iter=1,
    void_remove_existing=True,
    void_forbid_add=True,
    add_allow_large_gap_with_strong_visual=True,
    add_min_row_line_support=3,
    add_min_col_line_support=3,
    max_add_gap_nodes=2,
    add_min_direct_neighbor=2,
    keep_strong_visual_offgrid=True,
    protect_dense_on_grid=True,
    dense_neighbor_protect_min=5,
    remove_oversize_boundary_on_grid=True,
    oversize_radius_ratio=1.45,
    keep_uncertain_on_grid=True,
    remove_strong_via_on_grid=True,
    remove_blank_on_grid=True,
)

# ==============================================================
# ================= 🌟 [全局模型缓存] ===========================
# ==============================================================
_detector_cache = {}

def get_detector_instance(weights_path: str, device: str = "0"):
    """加载并缓存检测器"""
    if weights_path not in _detector_cache:
        _detector_cache[weights_path] = BGADetector(weights=weights_path, device=device)
    return _detector_cache[weights_path]

# ==============================================================
# ================= 🌟 [圆形 NMS 与嵌套抑制算法] ===================
# ==============================================================
def circle_nms(circles: List[Circle]) -> List[Circle]:
    """
    对单个焊球内检出的所有候选气泡圆执行严格抑制：
    1. 按半径降序排列；
    2. 彻底消除圈内有圈 (Nesting)：小圆心落在大圆内，或 dist + r_small <= r_large * 1.02 则滤除小圆；
    3. 彻底消除重叠乱圈 (Heavy Overlap)：两圆圆心相距过近 (dist < r_large * 0.65 或 dist < (r1 + r2) * 0.55) 则滤除较小圆。
    """
    if not circles:
        return []
    sorted_circles = sorted(circles, key=lambda c: c["radius"], reverse=True)
    kept: List[Circle] = []
    for c in sorted_circles:
        cx, cy = c["center"]
        r = c["radius"]
        suppress = False
        for kc in kept:
            kcx, kcy = kc["center"]
            kr = kc["radius"]
            dist = math.hypot(cx - kcx, cy - kcy)
            # 条件 1: 圈内套圈 (小圆几乎完全在大圆内)
            if dist + r <= kr * 1.02:
                suppress = True
                break
            # 条件 2: 严重重叠 (两圆圆心相距过近或重叠深度过大)
            if dist < kr * 0.65 or dist < (kr + r) * 0.55:
                suppress = True
                break
        if not suppress:
            kept.append(c)
    return kept


# ==============================================================
# ================= 🌟 [径向梯度边缘自适应精修算法] =================
# ==============================================================
def refine_solder_ball_radial_vectorized(
    roi: np.ndarray,
    gx: np.ndarray,
    gy: np.ndarray,
    local_cx: float,
    local_cy: float,
    nom_r: float,
    search_dxy: float = 6.0,
    search_dr: float = 2.5
) -> tuple[float, float, float]:
    """
    基于径向梯度通量 (Daugman-like Radial Gradient Flux) 的亚像素高鲁棒焊球边缘拟合算法：
    保持 100% 原生工业高精度数学逻辑，依靠外层多核线程池并发获得极致加速。
    """
    roi_h, roi_w = roi.shape
    if roi_h < 5 or roi_w < 5 or nom_r < 3:
        return float(local_cx), float(local_cy), float(nom_r)

    angles = np.linspace(0, 2 * np.pi, 28, endpoint=False, dtype=np.float32)
    cos_a = np.cos(angles)
    sin_a = np.sin(angles)

    # 针对超大焊球对上限做轻微限幅，防止大图内存暴增
    dxy = min(float(search_dxy), 6.5)
    dr = min(float(search_dr), 3.0)

    dx = np.arange(-dxy, dxy + 0.51, 0.5, dtype=np.float32)
    dy = np.arange(-dxy, dxy + 0.51, 0.5, dtype=np.float32)
    dr_arr = np.arange(-dr, dr + 0.51, 0.5, dtype=np.float32)

    DX, DY, DR = np.meshgrid(dx, dy, dr_arr, indexing='ij')
    cands_dx = DX.ravel()
    cands_dy = DY.ravel()
    cands_r = (nom_r + DR).ravel()

    cands_cx = (local_cx + cands_dx)[:, None]
    cands_cy = (local_cy + cands_dy)[:, None]
    cands_r_2d = cands_r[:, None]

    px = np.clip(np.round(cands_cx + cands_r_2d * cos_a[None, :]).astype(np.int32), 0, roi_w - 1)
    py = np.clip(np.round(cands_cy + cands_r_2d * sin_a[None, :]).astype(np.int32), 0, roi_h - 1)

    sample_gx = gx[py, px]
    sample_gy = gy[py, px]

    rad_grad = sample_gx * cos_a[None, :] + sample_gy * sin_a[None, :]

    # 取 35 分位数：消除单侧走线、贴片引脚或背景明暗阶跃干扰
    scores = np.percentile(rad_grad, 35, axis=1)

    # 中心漂移与半径偏离惩罚
    dist = np.hypot(cands_dx, cands_dy)
    r_penalty = 0.5 * np.abs(cands_r - nom_r)
    final_scores = scores - 0.7 * dist - r_penalty

    best_idx = int(np.argmax(final_scores))
    return float(local_cx + cands_dx[best_idx]), float(local_cy + cands_dy[best_idx]), float(cands_r[best_idx])


# ==============================================================
# ================= 🌟 [核心算法 API] 供评估与后端调用 ===========
# ==============================================================

def predict_and_generate_mask(
    model: str,                              # YOLO 模型权重路径 (例如: "./best.pt")
    input_image_path: str,                   # 输入图片路径
    conf_threshold: Optional[float] = None,  # 置信度阈值 (默认 None: 不设限，由检测器和网格优化器自动精选)
    **kwargs                                 # 动态参数 (如 device, save_debug_image 等)
) -> list[PredictionResult]:
    """
    对单张 BGA 图像进行高召回气泡分割与检测：
    1. 结合 YOLO 与网格节点修正进行焊球高精度定位；
    2. 聚合分析当前图像所有焊球的灰度直方图分布，动态计算自适应阈值；
    3. 在焊球 ROI 内采用微孔保护的形态学与二值化流水线，最大程度消除漏检；
    4. 返回符合数据模型规范的结果列表。
    """
    # 1. 解析动态扩展参数
    device = kwargs.get('device', "0")
    save_debug_image = kwargs.get('save_debug_image', False)
    debug_output_dir = kwargs.get('debug_output_dir', _get_safe_debug_out_dir())
    min_void_area = kwargs.get('min_void_area', MIN_VOID_AREA)
    ng_thresh_ratio = kwargs.get('ng_threshold', NG_RATIO_THRESH) / 100.0

    # 2. 读取图像
    img = cv2.imdecode(np.fromfile(input_image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"无法读取图像: {input_image_path}")
        
    h_img, w_img = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    result_img = img.copy() if save_debug_image else None

    # 预计算全图高斯滤波与 Sobel 梯度，供后续向量化径向边缘精修使用
    blurred_full = cv2.GaussianBlur(gray, (3, 3), 0)
    gx_full = cv2.Sobel(blurred_full, cv2.CV_32F, 1, 0, ksize=3)
    gy_full = cv2.Sobel(blurred_full, cv2.CV_32F, 0, 1, ksize=3)

    # 3. 模型推理与网格修正
    detector = get_detector_instance(weights_path=model, device=device)
    item = detector.infer_one(input_image_path)
    refined_item = apply_grid_node_refine_to_result_item(item, cfg=GRID_REFINE_CFG)
    data_list = result_to_objects(refined_item, lowercase_keys=True, include_meta=True)

    # 🌟 4. 图像级焊球直方图统计与自适应阈值动态调谐
    # 快速采样各检出焊球内部核心区域的灰度像素
    solder_sample_pixels = []
    valid_solders = []
    for data in data_list:
        conf = float(data.get("conf", 1.0))
        is_grid_added = bool(data.get("added_by_grid", False) or data.get("recovered_by_grid", False))
        if conf_threshold is not None and not is_grid_added and conf < conf_threshold:
            continue
        r = float(data.get("radius", 0))
        if r < SOLDER_MIN_RADIUS:
            continue
        valid_solders.append(data)
        
        x_c, y_c = float(data.get("center_x", 0)), float(data.get("center_y", 0))
        r_core = max(2, int(r * 0.7))
        x1_c, y1_c = max(0, int(x_c - r_core)), max(0, int(y_c - r_core))
        x2_c, y2_c = min(w_img, int(x_c + r_core)), min(h_img, int(y_c + r_core))
        if x2_c > x1_c and y2_c > y1_c:
            solder_sample_pixels.append(gray[y1_c:y2_c, x1_c:x2_c].flatten())

    # 计算整板焊球全局基准标称半径 (抗噪统一定锚，彻底杜绝大大小小)
    all_r = [float(d["radius"]) for d in valid_solders]
    med_radius = float(np.median(all_r)) if all_r else 15.0
    detector_avg_r = float(refined_item.get("avg_radius", 0.0) or item.get("avg_radius", 0.0))
    if detector_avg_r > 0 and abs(detector_avg_r - med_radius) <= med_radius * 0.35:
        array_nominal_r = detector_avg_r
    elif med_radius > 0:
        array_nominal_r = med_radius
    else:
        array_nominal_r = 15.0

    if solder_sample_pixels:
        all_solder_vals = np.concatenate(solder_sample_pixels)
        solder_median = float(np.median(all_solder_vals))
        solder_std = float(np.std(all_solder_vals))
    else:
        solder_median = 90.0
        solder_std = 15.0

    # 🌟 噪声底噪与图像特征自适应偏移量公式 (极致高召回，进一步杜绝漏检)：
    auto_offset = float(np.clip(0.20 * solder_std + 2.2, 4.8, 9.5))
    
    # 若调用方显式指定了 void_thresh_offset 则尊重外部指定，否则采用自适应计算值
    user_void_offset = kwargs.get('void_thresh_offset')
    void_thresh_offset = float(user_void_offset) if user_void_offset is not None else auto_offset

def _process_single_solder_ball(
    data: dict,
    gray: np.ndarray,
    gx_full: np.ndarray,
    gy_full: np.ndarray,
    w_img: int,
    h_img: int,
    array_nominal_r: float,
    void_thresh_offset: float,
    min_void_area: float,
) -> Optional[PredictionResult]:
    """处理单个焊球的亚像素边缘精修与气泡高精度提取"""
    conf = float(data.get("conf", 1.0))
    x_c, y_c, r = float(data.get("center_x", 0)), float(data.get("center_y", 0)), float(data.get("radius", 0))

    # 判断当前焊球基准标称参考半径 (优先使用网格精修的标称半径，其次全局阵列均值)
    draw_r = float(data.get("draw_radius", 0.0) or 0.0)
    if draw_r > 0 and 0.65 * array_nominal_r <= draw_r <= 1.45 * array_nominal_r:
        ball_ref_r = draw_r
    elif 0.65 * array_nominal_r <= r <= 1.45 * array_nominal_r:
        ball_ref_r = array_nominal_r
    else:
        ball_ref_r = r

    # 动态裁剪焊点局部 ROI (以当前中心为基准，预留梯度搜索裕量)
    pad = int(max(ball_ref_r * 1.5, ball_ref_r + 15))
    x1 = max(0, int(round(x_c - pad)))
    y1 = max(0, int(round(y_c - pad)))
    x2 = min(w_img, int(round(x_c + pad)))
    y2 = min(h_img, int(round(y_c + pad)))
    roi = gray[y1:y2, x1:x2]
    if roi.size == 0: 
        return None

    rgx = gx_full[y1:y2, x1:x2]
    rgy = gy_full[y1:y2, x1:x2]
    local_x_c = x_c - x1
    local_y_c = y_c - y1

    # 🌟 径向梯度通量精修：高精度自适应拟合每个焊点的亚像素圆心与真实半径
    fx, fy, fr = refine_solder_ball_radial_vectorized(
        roi, rgx, rgy, local_x_c, local_y_c, ball_ref_r,
        search_dxy=max(4.5, min(8.0, ball_ref_r * 0.35)),
        search_dr=max(2.0, min(4.5, ball_ref_r * 0.15))
    )

    local_cx = int(round(fx))
    local_cy = int(round(fy))
    x_c = local_cx + x1
    y_c = local_cy + y1
    radius = int(round(fr * SOLDER_SHRINK_RATIO))

    # 顶帽变换消除背景
    tophat_k_size = max(MIN_TOPHAT_KERNEL, int(radius * TOPHAT_KERNEL_RATIO))
    tophat_k_size = tophat_k_size if tophat_k_size % 2 == 1 else tophat_k_size + 1
    roi_tophat = cv2.morphologyEx(cv2.GaussianBlur(roi, (3, 3), 0), cv2.MORPH_TOPHAT, 
                                  cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (tophat_k_size, tophat_k_size)))

    # 掩膜与安全区
    solder_mask = np.zeros_like(roi)
    cv2.circle(solder_mask, (local_cx, local_cy), radius, 255, -1)
    solder_mask_safe = np.zeros_like(roi)
    cv2.circle(solder_mask_safe, (local_cx, local_cy), max(1, int(radius * SAFE_ZONE_RATIO)), 255, -1)

    # 动态自适应阈值二值化
    bg_reference = cv2.mean(roi_tophat, mask=solder_mask_safe)[0]
    threshold_val = bg_reference + void_thresh_offset
    _, void_thresh = cv2.threshold(roi_tophat, threshold_val, 255, cv2.THRESH_BINARY) 

    # 微孔保护策略
    void_mask_raw = cv2.bitwise_and(void_thresh, solder_mask_safe)
    void_mask_closed = cv2.morphologyEx(void_mask_raw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    void_mask = cv2.bitwise_or(void_mask_raw, void_mask_closed)

    # 坚实度与密度过滤 + 尺度自适应面积约束
    raw_contours, _ = cv2.findContours(void_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidate_void_circles: List[Circle] = []
    max_allowed_area = MAX_VOID_AREA_RATIO * np.pi * radius * radius

    adaptive_min_area = max(float(min_void_area), float(min_void_area) * ((radius / 15.0) ** 1.2) * 0.7)

    for cnt in raw_contours:
        c_area = cv2.contourArea(cnt)
        if c_area < adaptive_min_area or c_area > max_allowed_area:
            continue

        single_mask = np.zeros_like(void_mask)
        cv2.drawContours(single_mask, [cnt], -1, 255, thickness=-1)
        actual_pixels = np.count_nonzero(cv2.bitwise_and(void_mask, single_mask))
        filled_area = np.count_nonzero(single_mask)
        if filled_area > 0 and (actual_pixels / filled_area) < MIN_VOID_DENSITY:
            continue

        hull_area = cv2.contourArea(cv2.convexHull(cnt))
        if hull_area > 0 and (c_area / float(hull_area)) < MIN_VOID_SOLIDITY:
            continue

        (v_x, v_y), v_radius = cv2.minEnclosingCircle(cnt)
        r_area = np.sqrt(c_area / np.pi)

        v_r_calc = min(v_radius * VOID_RADIUS_COMP, r_area * 1.35, radius * MAX_VOID_RADIUS_RATIO, MAX_VOID_RADIUS_ABSOLUTE)

        d_to_center = np.hypot(v_x - local_cx, v_y - local_cy)
        if d_to_center >= radius * SAFE_ZONE_RATIO:
            continue

        if d_to_center + v_r_calc > radius * 0.95:
            v_r_calc = max(1.0, radius * 0.95 - d_to_center)

        if v_r_calc < 1.0:
            continue

        candidate_void_circles.append({
            "center": (float(v_x + x1), float(v_y + y1)),
            "radius": float(v_r_calc)
        })

    # Circle NMS 抑制
    current_void_circles = circle_nms(candidate_void_circles)

    clean_void_mask = np.zeros_like(void_mask)
    for vc in current_void_circles:
        local_vx = int(round(vc["center"][0] - x1))
        local_vy = int(round(vc["center"][1] - y1))
        cv2.circle(clean_void_mask, (local_vx, local_vy), max(1, int(round(vc["radius"]))), 255, thickness=cv2.FILLED)

    clean_void_mask = cv2.bitwise_and(clean_void_mask, solder_mask)
    s_area = np.count_nonzero(solder_mask)
    if s_area <= 0:
        return None

    v_area = np.count_nonzero(clean_void_mask)
    void_rate = float(v_area / s_area)

    return {
        "image_size": (int(w_img), int(h_img)),
        "solder_circle": {"center": (float(x_c), float(y_c)), "radius": float(radius)},
        "void_circle": current_void_circles,
        "void_rate": void_rate,
        "confidence": conf
    }


def predict_and_generate_mask(
    model: str,                              # YOLO 模型权重路径 (例如: "./best.pt")
    input_image_path: str,                   # 输入图片路径
    conf_threshold: Optional[float] = None,  # 置信度阈值 (默认 None: 不设限，由检测器和网格优化器自动精选)
    **kwargs                                 # 动态参数 (如 device, save_debug_image 等)
) -> list[PredictionResult]:
    """
    对单张 BGA 图像进行高召回气泡分割与检测 (高性能多核并行加速版)：
    1. 结合 YOLO 与网格节点修正进行焊球高精度定位；
    2. 聚合分析当前图像所有焊球的灰度直方图分布，动态计算自适应阈值；
    3. 利用多核线程池并发执行逐焊球局部 ROI 梯度精修与气泡二值化形态学，大幅降低耗时；
    4. 返回符合数据模型规范的结果列表。
    """
    # 1. 解析动态扩展参数
    device = kwargs.get('device', "0")
    save_debug_image = kwargs.get('save_debug_image', False)
    debug_output_dir = kwargs.get('debug_output_dir', _get_safe_debug_out_dir())
    min_void_area = kwargs.get('min_void_area', MIN_VOID_AREA)
    ng_thresh_ratio = kwargs.get('ng_threshold', NG_RATIO_THRESH) / 100.0

    # 2. 读取图像
    img = cv2.imdecode(np.fromfile(input_image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"无法读取图像: {input_image_path}")
        
    h_img, w_img = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    result_img = img.copy() if save_debug_image else None

    # 预计算全图高斯滤波与 Sobel 梯度，供后续向量化径向边缘精修使用
    blurred_full = cv2.GaussianBlur(gray, (3, 3), 0)
    gx_full = cv2.Sobel(blurred_full, cv2.CV_32F, 1, 0, ksize=3)
    gy_full = cv2.Sobel(blurred_full, cv2.CV_32F, 0, 1, ksize=3)

    # 3. 模型推理与网格修正
    detector = get_detector_instance(weights_path=model, device=device)
    item = detector.infer_one(input_image_path)
    refined_item = apply_grid_node_refine_to_result_item(item, cfg=GRID_REFINE_CFG)
    data_list = result_to_objects(refined_item, lowercase_keys=True, include_meta=True)

    # 🌟 4. 图像级焊球直方图统计与自适应阈值动态调谐
    solder_sample_pixels = []
    valid_solders = []
    for data in data_list:
        conf = float(data.get("conf", 1.0))
        is_grid_added = bool(data.get("added_by_grid", False) or data.get("recovered_by_grid", False))
        if conf_threshold is not None and not is_grid_added and conf < conf_threshold:
            continue
        r = float(data.get("radius", 0))
        if r < SOLDER_MIN_RADIUS:
            continue
        valid_solders.append(data)
        
        x_c, y_c = float(data.get("center_x", 0)), float(data.get("center_y", 0))
        r_core = max(2, int(r * 0.7))
        x1_c, y1_c = max(0, int(x_c - r_core)), max(0, int(y_c - r_core))
        x2_c, y2_c = min(w_img, int(x_c + r_core)), min(h_img, int(y_c + r_core))
        if x2_c > x1_c and y2_c > y1_c:
            solder_sample_pixels.append(gray[y1_c:y2_c, x1_c:x2_c].flatten())

    # 计算整板焊球全局基准标称半径
    all_r = [float(d["radius"]) for d in valid_solders]
    med_radius = float(np.median(all_r)) if all_r else 15.0
    detector_avg_r = float(refined_item.get("avg_radius", 0.0) or item.get("avg_radius", 0.0))
    if detector_avg_r > 0 and abs(detector_avg_r - med_radius) <= med_radius * 0.35:
        array_nominal_r = detector_avg_r
    elif med_radius > 0:
        array_nominal_r = med_radius
    else:
        array_nominal_r = 15.0

    if solder_sample_pixels:
        all_solder_vals = np.concatenate(solder_sample_pixels)
        solder_median = float(np.median(all_solder_vals))
        solder_std = float(np.std(all_solder_vals))
    else:
        solder_median = 90.0
        solder_std = 15.0

    auto_offset = float(np.clip(0.20 * solder_std + 2.2, 4.8, 9.5))
    user_void_offset = kwargs.get('void_thresh_offset')
    void_thresh_offset = float(user_void_offset) if user_void_offset is not None else auto_offset

    # === 5. 并发执行逐焊球气泡分割流水线 (CPU 多核线程池加速) ===
    results: List[PredictionResult] = []

    def _worker(d):
        return _process_single_solder_ball(
            data=d,
            gray=gray,
            gx_full=gx_full,
            gy_full=gy_full,
            w_img=w_img,
            h_img=h_img,
            array_nominal_r=array_nominal_r,
            void_thresh_offset=void_thresh_offset,
            min_void_area=min_void_area,
        )

    if len(valid_solders) <= 4:
        for d in valid_solders:
            item_res = _worker(d)
            if item_res is not None:
                results.append(item_res)
    else:
        max_workers = min(8, os.cpu_count() or 4)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            thread_results = list(executor.map(_worker, valid_solders))
            results = [r for r in thread_results if r is not None]

    # 统一绘制与保存调试图 (若有请求)
    if save_debug_image and result_img is not None:
        for r_item in results:
            x_c, y_c = r_item["solder_circle"]["center"]
            radius = r_item["solder_circle"]["radius"]
            void_rate = r_item["void_rate"]
            status = 'NG' if void_rate > ng_thresh_ratio else 'PASS'
            cv2.circle(result_img, (int(round(x_c)), int(round(y_c))), int(round(radius)), COLOR_SOLDER, 1)
            current_text_color = COLOR_TEXT_NG if status == 'NG' else COLOR_TEXT_PASS
            cv2.putText(result_img, f"{void_rate * 100:.1f}%", 
                        (int(round(x_c - radius)), int(round(y_c - radius - 2))), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, current_text_color, 1)

            for void in r_item.get("void_circle", []):
                cv_v_c = (int(round(void["center"][0])), int(round(void["center"][1])))
                current_void_color = COLOR_VOID_NG if status == 'NG' else COLOR_VOID_PASS
                cv2.circle(result_img, cv_v_c, int(round(void["radius"])), current_void_color, 1)

        if not os.path.exists(debug_output_dir):
            os.makedirs(debug_output_dir)
        save_path = os.path.join(debug_output_dir, f"debug_{os.path.basename(input_image_path)}")
        cv2.imencode('.jpg', result_img)[1].tofile(save_path)

    return results
