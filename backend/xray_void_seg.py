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
MIN_VOID_AREA = 3.8               # (像素) 最小气泡物理面积下限 (对应 r≈1.1px 微孔，精准滤除 1~3px 散斑噪点)。
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

import threading

# ==============================================================
# ================= [全局模型缓存与线程安全池] =================
# ==============================================================
_detector_lock = threading.Lock()
_detector_cache = {}

def get_detector_instance(weights_path: str, device: str = "0"):
    """
    加载并缓存检测器 (线程安全单例池)
    缓存键使用 (weights_path, device)，确保切换计算设备时能正确构建对应实例
    """
    cache_key = (os.path.abspath(weights_path), str(device).strip())
    with _detector_lock:
        if cache_key not in _detector_cache:
            _detector_cache[cache_key] = BGADetector(weights=weights_path, device=device)
        return _detector_cache[cache_key]

# ==============================================================
# ==============================================================
# ================= 🌟 [圆形 NMS 与非交叉接壤约束算法] ============
# ==============================================================
def circle_nms(circles: List[Circle], min_void_radius: float = 1.0) -> List[Circle]:
    """
    对单个焊球内检出的所有候选气泡圆执行严格非交叉与接壤几何约束：
    1. 物理真实性：真实金属中，空洞与空洞之间在几何上绝不穿透交叉，最多相切接壤 (Tangent / Bordering)；
    2. 严格去重与去寄生：
       - 小圆心落在大圆内 (dist < kr * 0.98) 或完全被包裹 (dist + r <= kr * 1.02) 时彻底滤除；
       - 重叠深度过大 (dist < (kr + r) * 0.68 或 overlap > 0.35 * min(kr, r)) 时，滤除较小伴生圆；
    3. 几何接壤约束求解 (Enforce '最多接壤，严禁交叉'):
       - 对于真实独立的相邻双孔/多孔，若因拟合外扩出现微量重叠 (dist < r1 + r2)，
         沿连心线等比约束缩减两圆半径使其恰好相切接壤 (r1' + r2' <= dist)；
       - 彻底根除两圆交叉划破对方轮廓的非真实工业质检瑕疵。
    """
    if not circles:
        return []

    # 步骤 1: 按半径降序排列 (大空洞主峰优先)
    sorted_circles = sorted(circles, key=lambda c: c["radius"], reverse=True)
    kept: List[Circle] = []

    for c in sorted_circles:
        cx, cy = c["center"]
        r = float(c["radius"])
        suppress = False
        for kc in kept:
            kcx, kcy = kc["center"]
            kr = float(kc["radius"])
            dist = math.hypot(cx - kcx, cy - kcy)

            # 条件 1: 圈内套圈或圆心深入大圆 (属于同一空洞腔体内部的局部波动)
            if dist < kr * 0.98 or (dist + r) <= kr * 1.02:
                suppress = True
                break

            # 条件 2: 严重重叠 (两圆重叠深度过深，属于局部过分割伴生伪圆)
            overlap = (kr + r) - dist
            if overlap > 0.35 * min(kr, r) or dist < (kr + r) * 0.68:
                suppress = True
                break

        if not suppress:
            kept.append({"center": (cx, cy), "radius": r})

    if len(kept) <= 1:
        return kept

    # 步骤 2: 迭代求解多圆相切接壤几何约束 (Enforce dist >= r_i + r_j)
    # 彻底杜绝任何两圆相交穿刺
    eps = 1e-4
    for _ in range(4):
        modified = False
        for i in range(len(kept)):
            for j in range(i + 1, len(kept)):
                c1 = kept[i]["center"]
                r1 = kept[i]["radius"]
                c2 = kept[j]["center"]
                r2 = kept[j]["radius"]
                dist = math.hypot(c1[0] - c2[0], c1[1] - c2[1])

                # 若两圆存在交叉重叠
                if dist < (r1 + r2) - eps:
                    modified = True
                    # 若两圆心相距过近，无法在满足最小半径的前提下同时存在，淘汰较小圆
                    if dist < (min_void_radius * 2.0):
                        kept[j]["radius"] = 0.0
                        continue

                    # 沿连心线等比收缩半径至精确相切接壤 (r1' + r2' = dist - eps)
                    scale_factor = (dist - eps) / (r1 + r2)
                    new_r1 = max(min_void_radius, r1 * scale_factor)
                    new_r2 = max(min_void_radius, r2 * scale_factor)

                    # 若由于 min_void_radius 约束仍超界，修剪较小圆
                    if new_r1 + new_r2 > dist - eps:
                        new_r2 = max(0.0, (dist - eps) - new_r1)

                    kept[i]["radius"] = new_r1
                    kept[j]["radius"] = new_r2

        # 淘汰收缩后低于物理阈值的残影
        kept = [c for c in kept if c["radius"] >= min_void_radius]
        if not modified or len(kept) <= 1:
            break

    # 步骤 3: 最终安全校验，确保 100% 满足 '最多接壤，严禁交叉'
    final_kept: List[Circle] = []
    for c in kept:
        cx, cy = c["center"]
        r = c["radius"]
        suppress = False
        for fc in final_kept:
            fcx, fcy = fc["center"]
            fr = fc["radius"]
            dist = math.hypot(cx - fcx, cy - fcy)
            if dist < (r + fr) - eps:
                suppress = True
                break
        if not suppress:
            final_kept.append(c)

    return final_kept



def decompose_connected_component(
    cnt: np.ndarray,
    roi_tophat: np.ndarray,
    min_split_area: float = 18.0,
    min_peak_dist: float = 3.5,
) -> list[np.ndarray]:
    """
    对可能粘连的双核/哑铃形连通域执行局部极大值与距离变换分水岭解离：
    若非凸凹陷连通域内存在两个或以上明确的局部极大值中心，则将其拆分成独立的气泡子连通域，
    彻底根治“大绿圈吞小黄圈”的欠分割问题。
    """
    area = cv2.contourArea(cnt)
    if area < min_split_area:
        return [cnt]

    bx, by, bw, bh = cv2.boundingRect(cnt)
    if bw < 5 or bh < 5:
        return [cnt]

    local_mask = np.zeros((bh, bw), dtype=np.uint8)
    local_cnt = cnt - np.array([[[bx, by]]])
    cv2.drawContours(local_mask, [local_cnt], -1, 255, -1)

    dist = cv2.distanceTransform(local_mask, cv2.DIST_L2, 5)
    max_dist = float(dist.max())
    if max_dist < 1.7:
        return [cnt]

    dilated_dist = cv2.dilate(dist, np.ones((3, 3), np.uint8))
    is_peak = (dist == dilated_dist) & (dist >= 1.4) & (dist >= 0.40 * max_dist)

    num_peaks, peak_labels, stats, centroids = cv2.connectedComponentsWithStats(is_peak.astype(np.uint8))
    if num_peaks <= 2:
        return [cnt]

    valid_centers = []
    for k in range(1, num_peaks):
        cx, cy = centroids[k]
        val = float(dist[int(round(cy)), int(round(cx))])
        valid_centers.append((cx, cy, val))

    kept_centers = []
    for c in sorted(valid_centers, key=lambda x: x[2], reverse=True):
        if not any(math.hypot(c[0] - kc[0], c[1] - kc[1]) < min_peak_dist for kc in kept_centers):
            kept_centers.append(c)

    if len(kept_centers) < 2:
        return [cnt]

    markers = np.zeros((bh, bw), dtype=np.int32)
    for idx, (cx, cy, _) in enumerate(kept_centers, 1):
        cv2.circle(markers, (int(round(cx)), int(round(cy))), 1, idx, -1)

    dist_norm = cv2.normalize(dist, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    energy = cv2.bitwise_not(dist_norm)
    energy_bgr = cv2.cvtColor(energy, cv2.COLOR_GRAY2BGR)

    markers = cv2.watershed(energy_bgr, markers)

    sub_contours = []
    for idx in range(1, len(kept_centers) + 1):
        sub_mask = ((markers == idx) & (local_mask > 0)).astype(np.uint8)
        if np.count_nonzero(sub_mask) < 3:
            continue
        sub_cnts, _ = cv2.findContours(sub_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for sc in sub_cnts:
            if cv2.contourArea(sc) >= 3.0:
                global_sc = sc + np.array([[[bx, by]]])
                sub_contours.append(global_sc)

    return sub_contours if len(sub_contours) >= 2 else [cnt]


# ==============================================================
# ================= 🌟 [径向梯度边缘自适应精修算法] =================
# ==============================================================
def _eval_radial_candidates(
    gx: np.ndarray,
    gy: np.ndarray,
    g_scale: float,
    local_cx: float,
    local_cy: float,
    nom_r: float,
    dx_arr: np.ndarray,
    dy_arr: np.ndarray,
    dr_arr: np.ndarray,
    cos_a: np.ndarray,
    sin_a: np.ndarray,
    center_penalty_w: float,
    r_penalty_w: float,
    r_expand_extra_w: float,
) -> tuple[float, float, float, float]:
    """
    向量化评估候选圆周的饱和径向梯度通量与法向一致性得分。
    - 使用软饱和函数 x / sqrt(1 + x^2) 抑制背景矩形元件/白底等单侧超强阶跃边缘的吸偏效应；
    - 保留强负梯度惩罚，防止圆周切穿背景亮区或内部空洞边缘；
    - 结合梯度法向对齐度 (cos_align^2)，过滤斜交的直线走线与贴片边框。
    """
    roi_h, roi_w = gx.shape
    DX, DY, DR = np.meshgrid(dx_arr, dy_arr, dr_arr, indexing='ij')
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
    gmag = np.sqrt(sample_gx * sample_gx + sample_gy * sample_gy) + 1e-4
    cos_align = rad_grad / gmag

    # 线性保留焊球自身边缘梯度尖峰，仅对超过自适应 cap 的单侧极端外部阶跃做截断；负梯度直接计入惩罚
    norm_rg = np.clip(rad_grad / g_scale, -1.0, 1.0)
    align_weight = np.where(rad_grad > 0.0, np.clip(cos_align, 0.0, 1.0), 1.0)
    point_score = norm_rg * align_weight

    # 均值 + 35 分位数融合：尖峰精确定位靠均值，抗单侧遮挡靠 35 分位数
    mean_score = np.mean(point_score, axis=1)
    p35_score = np.percentile(point_score, 35, axis=1)
    edge_score = 0.55 * mean_score + 0.45 * p35_score

    dist = np.hypot(cands_dx, cands_dy)
    dr_diff = cands_r - nom_r
    r_pen = r_penalty_w * np.abs(dr_diff) + r_expand_extra_w * np.maximum(0.0, dr_diff)
    final_scores = edge_score - center_penalty_w * dist - r_pen

    best_idx = int(np.argmax(final_scores))
    return (
        float(local_cx + cands_dx[best_idx]),
        float(local_cy + cands_dy[best_idx]),
        float(cands_r[best_idx]),
        float(edge_score[best_idx]),
    )


def _refine_solder_ball_radial_with_score(
    roi: np.ndarray,
    gx: np.ndarray,
    gy: np.ndarray,
    local_cx: float,
    local_cy: float,
    nom_r: float,
    search_dxy: float = 6.0,
    search_dr: float = 2.5,
    center_penalty_w: float = 0.006,
    r_penalty_w: float = 0.008,
    r_expand_extra_w: float = 0.018,
) -> tuple[float, float, float, float]:
    """
    抗背景干扰的粗到精 (Coarse-to-Fine) 亚像素焊球边缘拟合算法：
    1. 粗搜 (步长 1.0px, 24 角度) 快速锁定主峰；
    2. 精搜 (步长 0.5px, 32 角度) 亚像素精细收敛；
    3. 使用 ROI 梯度 90 分位数作为截断尺度，既保留高对比度焊球自身的尖峰定位精度，
       又截断外部单侧超强背景阶跃，同时对强负梯度施加惩罚。
    """
    roi_h, roi_w = roi.shape
    if roi_h < 5 or roi_w < 5 or nom_r < 3:
        return float(local_cx), float(local_cy), float(nom_r), 0.0

    # 自适应高位截断尺度：保留焊球边缘尖峰分辨率，同时抑制单侧极端外部阶跃
    roi_gmag = np.sqrt(gx * gx + gy * gy)
    g_scale = float(max(30.0, np.percentile(roi_gmag, 90)))

    dxy = min(float(search_dxy), 6.5)
    dr = min(float(search_dr), 3.0)

    # 阶段 1: 粗搜索 (步长 1.0px)
    angles_c = np.linspace(0, 2 * np.pi, 24, endpoint=False, dtype=np.float32)
    dx_c = np.arange(-dxy, dxy + 0.51, 1.0, dtype=np.float32)
    dy_c = np.arange(-dxy, dxy + 0.51, 1.0, dtype=np.float32)
    dr_c = np.arange(-dr, dr + 0.51, 1.0, dtype=np.float32)

    cx1, cy1, r1, _ = _eval_radial_candidates(
        gx, gy, g_scale, local_cx, local_cy, nom_r,
        dx_c, dy_c, dr_c, np.cos(angles_c), np.sin(angles_c),
        center_penalty_w, r_penalty_w, r_expand_extra_w,
    )

    # 阶段 2: 亚像素精搜索 (在粗搜最优点附近 ±1.0px, 步长 0.5px)
    angles_f = np.linspace(0, 2 * np.pi, 32, endpoint=False, dtype=np.float32)
    dx_f = np.arange((cx1 - local_cx) - 1.0, (cx1 - local_cx) + 1.01, 0.5, dtype=np.float32)
    dy_f = np.arange((cy1 - local_cy) - 1.0, (cy1 - local_cy) + 1.01, 0.5, dtype=np.float32)
    dr_f = np.arange((r1 - nom_r) - 1.0, (r1 - nom_r) + 1.01, 0.5, dtype=np.float32)
    dx_f = dx_f[(dx_f >= -dxy - 0.01) & (dx_f <= dxy + 0.01)]
    dy_f = dy_f[(dy_f >= -dxy - 0.01) & (dy_f <= dxy + 0.01)]
    dr_f = dr_f[(dr_f >= -dr - 0.01) & (dr_f <= dr + 0.01)]
    if dx_f.size == 0:
        dx_f = np.array([cx1 - local_cx], dtype=np.float32)
    if dy_f.size == 0:
        dy_f = np.array([cy1 - local_cy], dtype=np.float32)
    if dr_f.size == 0:
        dr_f = np.array([r1 - nom_r], dtype=np.float32)

    return _eval_radial_candidates(
        gx, gy, g_scale, local_cx, local_cy, nom_r,
        dx_f, dy_f, dr_f, np.cos(angles_f), np.sin(angles_f),
        center_penalty_w, r_penalty_w, r_expand_extra_w,
    )


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
    基于饱和径向梯度通量与法向一致性的亚像素高鲁棒焊球边缘拟合算法 (兼容旧接口)。
    """
    fx, fy, fr, _ = _refine_solder_ball_radial_with_score(
        roi, gx, gy, local_cx, local_cy, nom_r,
        search_dxy=search_dxy, search_dr=search_dr,
    )
    return fx, fy, fr


def _fit_affine_grid_centers(
    refined_entries: List[dict],
) -> tuple[dict[int, tuple[float, float]], dict[int, float]]:
    """
    按 grid_id 分组，使用 Huber 迭代重加权最小二乘 (IRLS) 拟合 2D 仿射网格映射:
        (grid_col, grid_row) -> (x_grid, y_grid)
    兼容芯片轻微旋转与缩放，并自动过滤拟合残差过大的非刚性分组。
    返回:
        grid_preds[idx] = (gx, gy)
        grid_med_r[grid_id] = 该阵列焊球半径中位数
    """
    groups: dict[int, list] = {}
    for idx, entry in enumerate(refined_entries):
        if entry is None:
            continue
        gid = entry.get("grid_id")
        gr = entry.get("grid_row")
        gc = entry.get("grid_col")
        if gid is None or gr is None or gc is None:
            continue
        groups.setdefault(int(gid), []).append(
            (idx, float(gc), float(gr), float(entry["fx"]), float(entry["fy"]), float(entry["fr"]))
        )

    grid_preds: dict[int, tuple[float, float]] = {}
    grid_med_r: dict[int, float] = {}

    for gid, pts in groups.items():
        if len(pts) < 6:
            continue
        A = np.array([[c, r, 1.0] for _, c, r, _, _, _ in pts], dtype=np.float64)
        bx = np.array([x for _, _, _, x, _, _ in pts], dtype=np.float64)
        by = np.array([y for _, _, _, _, y, _ in pts], dtype=np.float64)

        w = np.ones(len(pts), dtype=np.float64)
        coef_x = np.zeros(3, dtype=np.float64)
        coef_y = np.zeros(3, dtype=np.float64)
        med_err = 999.0
        for _ in range(5):
            W = np.sqrt(w)[:, None]
            coef_x, _, _, _ = np.linalg.lstsq(A * W, bx * W[:, 0], rcond=None)
            coef_y, _, _, _ = np.linalg.lstsq(A * W, by * W[:, 0], rcond=None)
            err = np.hypot(bx - A @ coef_x, by - A @ coef_y)
            med_err = float(np.median(err))
            delta = max(0.8, 1.5 * med_err)
            w = np.where(err <= delta, 1.0, delta / (err + 1e-6))

        # 仅当该阵列确实符合高刚性规则网格时才启用网格纠偏，避免误伤不规则阵列
        if med_err > 2.2:
            continue

        px = A @ coef_x
        py = A @ coef_y
        grid_med_r[gid] = float(np.median([r for _, _, _, _, _, r in pts]))
        for (idx, _, _, _, _, _), gx_val, gy_val in zip(pts, px, py):
            grid_preds[idx] = (float(gx_val), float(gy_val))

    return grid_preds, grid_med_r


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

def _refine_single_solder_geometry(
    data: dict,
    gray: np.ndarray,
    gx_full: np.ndarray,
    gy_full: np.ndarray,
    w_img: int,
    h_img: int,
    array_nominal_r: float,
) -> Optional[dict]:
    """Pass 1: 对单个焊球执行抗背景干扰的粗到精径向边缘拟合"""
    x_c, y_c, r = float(data.get("center_x", 0)), float(data.get("center_y", 0)), float(data.get("radius", 0))

    draw_r = float(data.get("draw_radius", 0.0) or 0.0)
    if draw_r > 0 and 0.65 * array_nominal_r <= draw_r <= 1.45 * array_nominal_r:
        ball_ref_r = draw_r
    elif 0.65 * array_nominal_r <= r <= 1.45 * array_nominal_r:
        ball_ref_r = array_nominal_r
    else:
        ball_ref_r = r

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
    fx_loc, fy_loc, fr, score = _refine_solder_ball_radial_with_score(
        roi, rgx, rgy, x_c - x1, y_c - y1, ball_ref_r,
        search_dxy=max(4.5, min(8.0, ball_ref_r * 0.35)),
        search_dr=max(2.0, min(4.5, ball_ref_r * 0.15)),
    )
    return {
        "fx": float(fx_loc + x1),
        "fy": float(fy_loc + y1),
        "fr": float(fr),
        "score": float(score),
        "ball_ref_r": float(ball_ref_r),
        "grid_id": data.get("grid_id"),
        "grid_row": data.get("grid_row"),
        "grid_col": data.get("grid_col"),
    }


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
    refined_geom: Optional[dict] = None,
) -> Optional[PredictionResult]:
    """处理单个焊球的亚像素边缘精修与气泡高精度提取"""
    conf = float(data.get("conf", 1.0))

    if refined_geom is None:
        refined_geom = _refine_single_solder_geometry(
            data, gray, gx_full, gy_full, w_img, h_img, array_nominal_r
        )
        if refined_geom is None:
            return None

    fx_abs = float(refined_geom["fx"])
    fy_abs = float(refined_geom["fy"])
    fr = float(refined_geom["fr"])

    # 以精修后的焊球中心裁剪 ROI，用于顶帽变换与空洞分割
    pad = int(max(fr * 1.5, fr + 15))
    x1 = max(0, int(round(fx_abs - pad)))
    y1 = max(0, int(round(fy_abs - pad)))
    x2 = min(w_img, int(round(fx_abs + pad)))
    y2 = min(h_img, int(round(fy_abs + pad)))
    roi = gray[y1:y2, x1:x2]
    if roi.size == 0:
        return None

    local_cx = int(round(fx_abs - x1))
    local_cy = int(round(fy_abs - y1))
    x_c = local_cx + x1
    y_c = local_cy + y1
    radius = max(1, int(round(fr * SOLDER_SHRINK_RATIO)))

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

    # 微孔保留原始边界，避免无节制闭运算粘连邻孔
    void_mask_raw = cv2.bitwise_and(void_thresh, solder_mask_safe)
    void_mask_subtle = cv2.morphologyEx(void_mask_raw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)))
    void_mask = cv2.bitwise_or(void_mask_raw, void_mask_subtle)

    # 坚实度与密度过滤 + 尺度自适应面积约束
    raw_contours, _ = cv2.findContours(void_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 🌟 针对性改进 1：仅对呈现凹陷/哑铃/狭长的连通域进行多峰分水岭解离 (避免大圆吞小圆)
    decomposed_contours = []
    for cnt in raw_contours:
        c_area = cv2.contourArea(cnt)
        hull_area = cv2.contourArea(cv2.convexHull(cnt))
        solidity = (c_area / float(hull_area)) if hull_area > 0 else 1.0
        rect = cv2.minAreaRect(cnt)
        rw, rh = rect[1]
        aspect = (max(rw, rh) / max(min(rw, rh), 1e-3)) if (rw > 0 and rh > 0) else 1.0
        
        # 仅当面积较大且明显呈现双核/哑铃/非凸凹陷 (solidity < 0.88 或 aspect >= 1.30) 时解离
        if c_area >= 18.0 and (solidity < 0.88 or aspect >= 1.30):
            subs = decompose_connected_component(cnt, roi_tophat, min_split_area=18.0, min_peak_dist=3.5)
            decomposed_contours.extend(subs)
        else:
            decomposed_contours.append(cnt)

    candidate_void_circles: List[Circle] = []
    max_allowed_area = MAX_VOID_AREA_RATIO * np.pi * radius * radius
    adaptive_min_area = max(float(min_void_area), float(min_void_area) * ((radius / 15.0) ** 1.1) * 0.8)

    for cnt in decomposed_contours:
        c_area = cv2.contourArea(cnt)
        if c_area < adaptive_min_area or c_area > max_allowed_area:
            continue

        single_mask = np.zeros_like(void_mask)
        cv2.drawContours(single_mask, [cnt], -1, 255, thickness=-1)

        tophat_vals = roi_tophat[single_mask > 0]
        if len(tophat_vals) == 0:
            continue
        peak_tophat = float(np.max(tophat_vals))
        peak_contrast = peak_tophat - bg_reference

        (v_x, v_y), v_radius = cv2.minEnclosingCircle(cnt)
        r_area = np.sqrt(c_area / np.pi)
        d_to_center = np.hypot(v_x - local_cx, v_y - local_cy)

        # 🌟 规则 A: 微小目标 (c_area < 8.0 或 r_area < 1.6) 严格要求峰值对比度 (杜绝底噪轻微起伏)
        if c_area < 8.0 or r_area < 1.6:
            if peak_contrast < (void_thresh_offset + 4.0):
                continue

        # 🌟 规则 B: 靠近焊球边缘区域 (d_to_center > radius * 0.70) 严格防范边缘厚度渐变毛刺
        if d_to_center > radius * 0.70:
            if c_area < 10.0 and peak_contrast < (void_thresh_offset + 4.8):
                continue
            # 边缘处过于扁平细长 (可能是圆弧贴边毛刺) 的过滤
            rect = cv2.minAreaRect(cnt)
            rw, rh = rect[1]
            if rw > 0 and rh > 0:
                aspect = max(rw, rh) / min(rw, rh)
                if aspect > 2.8:
                    continue

        actual_pixels = np.count_nonzero(cv2.bitwise_and(void_mask, single_mask))
        filled_area = np.count_nonzero(single_mask)
        if filled_area > 0 and (actual_pixels / filled_area) < MIN_VOID_DENSITY:
            continue

        hull_area = cv2.contourArea(cv2.convexHull(cnt))
        if hull_area > 0 and (c_area / float(hull_area)) < MIN_VOID_SOLIDITY:
            continue

        v_r_calc = min(v_radius * 0.98, r_area * 1.12, radius * MAX_VOID_RADIUS_RATIO, MAX_VOID_RADIUS_ABSOLUTE)

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
        "confidence": conf,
        "grid_row": data.get("grid_row"),
        "grid_col": data.get("grid_col"),
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

    # === 5. 两阶段并发精修 + 气泡分割流水线 (CPU 多核线程池加速) ===
    results: List[PredictionResult] = []
    max_workers = min(8, os.cpu_count() or 4)

    def _geom_worker(d):
        return _refine_single_solder_geometry(
            data=d,
            gray=gray,
            gx_full=gx_full,
            gy_full=gy_full,
            w_img=w_img,
            h_img=h_img,
            array_nominal_r=array_nominal_r,
        )

    # Pass 1: 并发执行逐焊球饱和径向梯度边缘精修
    if len(valid_solders) <= 4:
        geoms = [_geom_worker(d) for d in valid_solders]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            geoms = list(executor.map(_geom_worker, valid_solders))

    # Pass 2: 刚性 BGA 阵列 2D 仿射网格一致性校验 (仅纠偏受强背景干扰偏离或半径虚胖的焊球)
    grid_preds, grid_med_r = _fit_affine_grid_centers(geoms)
    for idx, geom in enumerate(geoms):
        if geom is None or idx not in grid_preds:
            continue
        gid = int(geom["grid_id"])
        r_med = grid_med_r.get(gid, array_nominal_r)
        gx_p, gy_p = grid_preds[idx]
        dev = math.hypot(geom["fx"] - gx_p, geom["fy"] - gy_p)
        r_oversize = geom["fr"] > r_med * 1.12
        low_conf_edge = geom["score"] < 0.42 and dev > max(1.8, r_med * 0.10)

        if dev > max(2.5, r_med * 0.16) or r_oversize or low_conf_edge:
            pad = int(max(r_med * 1.5, r_med + 15))
            x1 = max(0, int(round(gx_p - pad)))
            y1 = max(0, int(round(gy_p - pad)))
            x2 = min(w_img, int(round(gx_p + pad)))
            y2 = min(h_img, int(round(gy_p + pad)))
            roi = gray[y1:y2, x1:x2]
            if roi.size == 0:
                continue
            rgx = gx_full[y1:y2, x1:x2]
            rgy = gy_full[y1:y2, x1:x2]
            fx2, fy2, fr2, score2 = _refine_solder_ball_radial_with_score(
                roi, rgx, rgy, gx_p - x1, gy_p - y1, r_med,
                search_dxy=max(2.0, min(3.5, r_med * 0.16)),
                search_dr=max(1.5, min(3.0, r_med * 0.14)),
                center_penalty_w=0.025,
                r_penalty_w=0.020,
                r_expand_extra_w=0.045,
            )
            geom["fx"] = float(fx2 + x1)
            geom["fy"] = float(fy2 + y1)
            geom["fr"] = float(fr2)
            geom["score"] = float(score2)

    # Pass 3: 并发执行逐焊球气泡分割与空洞率计算
    def _void_worker(pair):
        d, g = pair
        if g is None:
            return None
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
            refined_geom=g,
        )

    pairs = list(zip(valid_solders, geoms))
    if len(pairs) <= 4:
        for pair in pairs:
            item_res = _void_worker(pair)
            if item_res is not None:
                results.append(item_res)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            thread_results = list(executor.map(_void_worker, pairs))
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
