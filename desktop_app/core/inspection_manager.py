# -*- coding: utf-8 -*-
"""
🌟 质检数据与会话管理器 (Inspection Manager)
--------------------------------------------
负责缓存当前检测结果、统一整合焊球/缺陷数据，并支持【动态阈值毫秒重算】与【双向联动检索】。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
import numpy as np


class SolderBallRecord:
    """单个焊球的完整物理与质检状态"""
    def __init__(
        self,
        index: int,
        cx: float,
        cy: float,
        radius: float,
        void_circles: List[Dict[str, Any]],
        void_rate: float,
        confidence: float = 0.80,
    ):
        self.index = index
        self.cx = cx
        self.cy = cy
        self.radius = radius
        self.void_circles = void_circles
        self.void_rate = void_rate
        self.confidence = confidence

        # 虚焊指标
        self.area = math.pi * (radius ** 2)
        self.area_ratio = 1.0
        self.reduction_percent = 0.0
        self.is_insufficient = False

        # 桥连指标
        self.is_bridge = False
        self.bridge_partners: List[int] = []

        # 质检状态
        self.is_void_ng = False
        self.is_ng = False
        self.status = "PASS"
        self.ng_reasons: List[str] = []

        # 交互状态 (工人是否手动消隐标注)
        self.is_user_hidden = False

    def re_evaluate(self, ng_void_thresh: float, undersize_thresh: float):
        """根据最新阈值进行毫秒级状态重判"""
        self.ng_reasons.clear()
        self.is_void_ng = self.void_rate > ng_void_thresh
        if self.is_void_ng:
            self.ng_reasons.append(f"气泡超标({self.void_rate * 100:.1f}%>{ng_void_thresh * 100:.1f}%)")

        self.is_insufficient = (self.reduction_percent / 100.0) > undersize_thresh
        if self.is_insufficient:
            self.ng_reasons.append(f"少锡虚焊(缩小{self.reduction_percent:.1f}%>{undersize_thresh * 100:.1f}%)")

        if self.is_bridge:
            self.ng_reasons.append("桥连短路")

        self.is_ng = self.is_void_ng or self.is_insufficient or self.is_bridge
        self.status = "NG" if self.is_ng else "PASS"


class InspectionSession:
    """单次质检会话管理"""
    def __init__(self):
        self.image_path: str = ""
        self.raw_image_mat: Optional[np.ndarray] = None
        self.inspected_image_path: Optional[str] = None
        self.solder_records: List[SolderBallRecord] = []
        self.bridge_defects: List[Dict[str, Any]] = []
        self.raw_pipeline_result: Optional[Dict[str, Any]] = None
        
        # 整体判定
        self.board_status: str = "READY"
        self.ng_reasons: List[str] = []
        self.elapsed_ms: float = 0.0

    def load_from_pipeline_result(
        self,
        image_path: str,
        raw_mat: np.ndarray,
        result: Dict[str, Any],
        ng_void_thresh: float = 0.25,
        undersize_thresh: float = 0.20,
    ):
        self.image_path = image_path
        self.raw_image_mat = raw_mat
        self.raw_pipeline_result = result
        self.inspected_image_path = result.get("visual_output_path")
        self.solder_records.clear()

        # 1. 解析所有焊球及气泡
        void_details = result.get("void_details", [])
        for idx, item in enumerate(void_details, start=1):
            sc = item.get("solder_circle", {})
            center = sc.get("center", (0.0, 0.0))
            radius = float(sc.get("radius", 10.0))
            void_circles = item.get("void_circle", [])
            void_rate = float(item.get("void_rate", 0.0))
            conf = float(item.get("confidence", 0.80))

            record = SolderBallRecord(
                index=idx,
                cx=float(center[0]),
                cy=float(center[1]),
                radius=radius,
                void_circles=void_circles,
                void_rate=void_rate,
                confidence=conf,
            )
            self.solder_records.append(record)

        # 2. 关联虚焊缺陷数据
        insufficient_details = result.get("insufficient_details", [])
        for defect in insufficient_details:
            s_idx = defect.get("solder_index", -1)
            if 1 <= s_idx <= len(self.solder_records):
                rec = self.solder_records[s_idx - 1]
                rec.reduction_percent = float(defect.get("reduction_percent", 0.0))
                rec.area_ratio = float(defect.get("area_ratio", 1.0))
                rec.area = float(defect.get("area", rec.area))

        # 3. 关联桥连缺陷数据
        self.bridge_defects = result.get("bridge_details", [])
        
        def _match_solder(ball_info: dict) -> Optional[SolderBallRecord]:
            if not ball_info:
                return None
            idx = ball_info.get("index", ball_info.get("orig_index", -1))
            center = ball_info.get("center")
            if center is None and "x" in ball_info and "y" in ball_info:
                center = (ball_info["x"], ball_info["y"])

            # 优先检查 1-based 索引
            if 1 <= idx <= len(self.solder_records):
                candidate = self.solder_records[idx - 1]
                if center is None or math.hypot(candidate.cx - center[0], candidate.cy - center[1]) < candidate.radius * 2.0:
                    return candidate

            # 其次检查 0-based 索引
            if 0 <= idx < len(self.solder_records):
                candidate = self.solder_records[idx]
                if center is None or math.hypot(candidate.cx - center[0], candidate.cy - center[1]) < candidate.radius * 2.0:
                    return candidate

            # 最后按坐标最近距离吸附匹配
            if center:
                cx, cy = center
                best = min(self.solder_records, key=lambda r: math.hypot(r.cx - cx, r.cy - cy), default=None)
                if best and math.hypot(best.cx - cx, best.cy - cy) <= max(25.0, best.radius * 2.5):
                    return best
            return None

        for b in self.bridge_defects:
            recA = _match_solder(b.get("ball_A", {}))
            recB = _match_solder(b.get("ball_B", {}))
            if recA:
                recA.is_bridge = True
                if recB:
                    recA.bridge_partners.append(recB.index)
            if recB:
                recB.is_bridge = True
                if recA:
                    recB.bridge_partners.append(recA.index)

        # 4. 执行初始判定
        self.re_evaluate(ng_void_thresh, undersize_thresh)

    def re_evaluate(self, ng_void_thresh: float, undersize_thresh: float):
        """纯内存毫秒重算"""
        board_ng = False
        reasons_set = set()

        for rec in self.solder_records:
            rec.re_evaluate(ng_void_thresh, undersize_thresh)
            if rec.is_ng:
                board_ng = True
                for r in rec.ng_reasons:
                    reasons_set.add(r)

        # 桥连缺陷绝对拦截整板判定
        if len(self.bridge_defects) > 0:
            board_ng = True
            reasons_set.add(f"桥连短路缺陷 ({len(self.bridge_defects)}处)")

        self.board_status = "NG" if board_ng else "PASS"
        self.ng_reasons = sorted(list(reasons_set))

    def get_summary_stats(self) -> Dict[str, Any]:
        """返回看板汇总统计"""
        total = len(self.solder_records)
        void_ng_count = sum(1 for r in self.solder_records if r.is_void_ng)
        bridge_count = len(self.bridge_defects)
        insuff_count = sum(1 for r in self.solder_records if r.is_insufficient)
        total_ng_balls = sum(1 for r in self.solder_records if r.is_ng)

        max_void = max((r.void_rate for r in self.solder_records), default=0.0)
        max_reduct = max((r.reduction_percent for r in self.solder_records), default=0.0)

        return {
            "total_solders": total,
            "board_status": self.board_status,
            "ng_reasons": self.ng_reasons,
            "total_ng_balls": total_ng_balls,
            "void_ng_count": void_ng_count,
            "bridge_count": bridge_count,
            "insufficient_count": insuff_count,
            "max_void_rate": max_void,
            "max_reduction_percent": max_reduct,
            "elapsed_ms": self.elapsed_ms,
        }

    def toggle_ball_visibility(self, ball_index: int) -> bool:
        """切换单个焊点的标注显隐状态，返回切换后的显隐状态 (True为隐藏)"""
        if 1 <= ball_index <= len(self.solder_records):
            rec = self.solder_records[ball_index - 1]
            rec.is_user_hidden = not rec.is_user_hidden
            return rec.is_user_hidden
        return False

    def reset_all_visibility(self):
        """恢复所有焊点的标注显示"""
        for rec in self.solder_records:
            rec.is_user_hidden = False
