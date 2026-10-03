# -*- coding: utf-8 -*-
"""
🌟 OpenCV 与 Qt 图像数据高性能零冗余转换工具 (Image Converter)
"""
from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtGui import QImage, QPixmap


def cv_mat_to_qimage(cv_img: np.ndarray) -> QImage:
    """将 OpenCV 图像 (BGR 或灰度) 转换为 QImage (零内存拷贝共享底层数据)"""
    if cv_img is None or cv_img.size == 0:
        return QImage()

    if len(cv_img.shape) == 2:
        # 单通道灰度图
        h, w = cv_img.shape
        bytes_per_line = w
        # QImage 复制一份，防止底层 numpy 数组被 GC 销毁后出现野指针
        q_img = QImage(cv_img.data, w, h, bytes_per_line, QImage.Format.Format_Grayscale8)
        return q_img.copy()

    elif len(cv_img.shape) == 3:
        h, w, ch = cv_img.shape
        if ch == 3:
            bytes_per_line = 3 * w
            q_img = QImage(cv_img.data, w, h, bytes_per_line, QImage.Format.Format_BGR888)
            return q_img.copy()
        elif ch == 4:
            bytes_per_line = 4 * w
            q_img = QImage(cv_img.data, w, h, bytes_per_line, QImage.Format.Format_BGRA8888)
            return q_img.copy()

    return QImage()


def cv_mat_to_qpixmap(cv_img: np.ndarray) -> QPixmap:
    """将 OpenCV 图像转换为可直接在视口渲染的 QPixmap"""
    q_img = cv_mat_to_qimage(cv_img)
    if q_img.isNull():
        return QPixmap()
    return QPixmap.fromImage(q_img)


def load_image_unicode(file_path: str) -> np.ndarray | None:
    """支持 Windows 包含中文字符路径的图片加载"""
    try:
        data = np.fromfile(file_path, dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"[ERROR] 无法读取图片 {file_path}: {e}")
        return None


def crop_image_rect(img: np.ndarray, rect: tuple[int, int, int, int]) -> np.ndarray:
    """
    按 (x1, y1, x2, y2) 坐标安全裁剪图像
    """
    h, w = img.shape[:2]
    x1, y1, x2, y2 = rect
    x1 = max(0, min(x1, w - 1))
    y1 = max(0, min(y1, h - 1))
    x2 = max(x1 + 1, min(x2, w))
    y2 = max(y1 + 1, min(y2, h))
    return img[y1:y2, x1:x2].copy()
