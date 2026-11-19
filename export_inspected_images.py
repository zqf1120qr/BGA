# -*- coding: utf-8 -*-
"""
🔬 X-ray AI Inspector - 客户端风格质检结果图像批量导出脚本 (Client-Style Image Exporter)
---------------------------------------------------------------------------------------
功能说明：
1. 一键运行：无需任何参数即可直接将 data/imgs 中的全部待测图像按照客户端高保真矢量视口风格
   （绿圈焊球 + 明黄空洞 + 警戒红短路框 + 胶囊标牌 + 工业 HUD 看板 + 标准图例）渲染并输出到文件夹；
2. 自由配置：支持单图或指定目录、支持 all_outline (全轮廓) 与 defect_only (仅高亮缺陷) 双视口模式；
3. 联动设置：自动加载 settings.json 中的工艺阈值配方，同时支持命令行灵活覆盖；
4. 结构化报表：支持同步输出 batch_inspection_summary.json 质检摘要。

使用示例：
  python export_inspected_images.py                                     # 默认检测 data/imgs 并导出到 output/inspected_images
  python export_inspected_images.py -i data/imgs/bridge_1.jpg           # 单图检测并导出
  python export_inspected_images.py -i data/imgs -o my_output           # 指定输入与输出文件夹
  python export_inspected_images.py --view-mode defect_only             # 仅高亮缺陷模式
  python export_inspected_images.py --ng-void 0.20 --undersize 0.15     # 自定义判定阈值
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import List, Optional

# 确保控制台支持 UTF-8 输出
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 确保项目根目录与 backend 目录位于 sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import cv2
import numpy as np

from desktop_app.app_config import app_config_mgr
from desktop_app.core.hardware_sniff import hardware_sniffer
from desktop_app.core.inspection_manager import InspectionSession
from desktop_app.utils.client_result_renderer import render_client_style_inspection_image
from backend.xray_pipeline import inspect_bga


SUPPORTED_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")


def parse_args():
    cfg = app_config_mgr.config
    parser = argparse.ArgumentParser(
        description="X-ray AI Inspector - 客户端风格质检结果图像批量导出工具",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        default=os.path.join(PROJECT_ROOT, "data", "imgs"),
        help="输入图像文件路径或待检测图像文件夹目录",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=os.path.join(PROJECT_ROOT, "output", "inspected_images"),
        help="质检标注图像保存的目标输出文件夹目录",
    )
    parser.add_argument(
        "-v", "--view-mode",
        type=str,
        choices=["all_outline", "defect_only"],
        default=getattr(cfg, "view_mode", "all_outline") or "all_outline",
        help="渲染视口模式: 'all_outline' (全焊球翠绿轮廓+缺陷高亮) 或 'defect_only' (仅高亮缺陷对象)",
    )
    parser.add_argument(
        "-m", "--mode",
        type=str,
        choices=["comprehensive", "void", "bridge", "insufficient"],
        default=getattr(cfg, "inspection_mode", "comprehensive") or "comprehensive",
        help="质检算法模式: comprehensive(综合), void(仅气泡), bridge(仅桥连), insufficient(仅虚焊)",
    )
    parser.add_argument(
        "--weights",
        type=str,
        default=getattr(cfg, "weights_path", os.path.join(BACKEND_DIR, "best.pt")),
        help="YOLO 目标检测模型权重文件路径 (.pt)",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=getattr(cfg, "conf_threshold", 0.20),
        help="焊球识别置信度门槛",
    )
    parser.add_argument(
        "--ng-void",
        type=float,
        default=getattr(cfg, "ng_void_threshold", 0.25),
        help="空洞气泡率超标门槛 (例如 0.25 表示 25%)",
    )
    parser.add_argument(
        "--undersize",
        type=float,
        default=getattr(cfg, "undersize_threshold", 0.20),
        help="少锡虚焊面积缩减门槛 (例如 0.20 表示缩减 20%)",
    )
    parser.add_argument(
        "--reference-mode",
        type=str,
        choices=["mean", "median"],
        default=getattr(cfg, "area_reference_mode", "mean") or "mean",
        help="焊球虚焊面积统计基准模式 ('mean' 均值 或 'median' 中位数)",
    )
    parser.add_argument(
        "-d", "--device",
        type=str,
        default=getattr(cfg, "hardware_device", "auto"),
        help="运算设备选择: 'auto' (自动探测), '0' (第一块 CUDA GPU), 'cpu'",
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="不绘制顶部客户端 HUD 状态看板",
    )
    parser.add_argument(
        "--no-legend",
        action="store_true",
        help="不绘制底部工业图例栏",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=95,
        help="输出 JPEG 图片压缩质量 (1-100)",
    )
    parser.add_argument(
        "--no-json",
        action="store_true",
        help="不生成 batch_inspection_summary.json 质检汇总数据文件",
    )
    return parser.parse_args()


def collect_image_files(input_path: str) -> List[str]:
    """收集指定路径下的所有合法图像文件"""
    if not os.path.exists(input_path):
        return []
    if os.path.isfile(input_path):
        if input_path.lower().endswith(SUPPORTED_EXTS):
            return [os.path.abspath(input_path)]
        return []
    
    file_list = []
    for root, _, files in os.walk(input_path):
        for f in sorted(files):
            if f.lower().endswith(SUPPORTED_EXTS):
                file_list.append(os.path.abspath(os.path.join(root, f)))
        break  # 仅遍历输入目录根层
    return file_list


def main():
    args = parse_args()

    # 1. 搜集待处理图片
    input_images = collect_image_files(args.input)
    if not input_images:
        print(f"\n[错误] 在输入路径下未找到任何有效图像文件: {args.input}")
        print(f"       支持的格式: {', '.join(SUPPORTED_EXTS)}")
        sys.exit(1)

    # 2. 确保输出目录存在
    os.makedirs(args.output, exist_ok=True)

    # 3. 硬件算力自适应解析
    target_device, status_text, _ = hardware_sniffer.resolve_device(args.device)

    # 4. 打印工业启动面板
    print("=" * 76)
    print("🔬 X-ray AI Inspector - 客户端风格质检结果图像批量导出工作流")
    print("=" * 76)
    print(f"📂 待测输入: {args.input} (共 {len(input_images)} 张图像)")
    print(f"📁 输出目录: {os.path.abspath(args.output)}")
    print(f"📦 权重模型: {args.weights}")
    print(f"⚙️  质检模式: {args.mode.upper()}  |  视口渲染: {args.view_mode}")
    print(f"🎯 判定基准: 空洞超标 > {args.ng_void * 100:.1f}%  |  虚焊少锡 > {args.undersize * 100:.1f}%")
    print(f"⚡ 运算加速: {status_text} (设备代码: {target_device})")
    print(f"🎨 布局元素: {'包含顶部HUD' if not args.no_banner else '无HUD'} | {'包含底部图例' if not args.no_legend else '无图例'}")
    print("=" * 76)

    # 5. 循环执行质检推理并渲染输出
    summary_records = []
    total_start_time = time.time()
    pass_count = 0
    ng_count = 0

    for idx, img_path in enumerate(input_images, start=1):
        fname = os.path.basename(img_path)
        base_stem = os.path.splitext(fname)[0]
        print(f"\n[{idx}/{len(input_images)}] 正在质检并渲染: {fname} ...")

        t_img_start = time.time()
        try:
            # 5.1 执行核心质检算法 (复用已加载模型)
            raw_bgr = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            res = inspect_bga(
                input_image_path=img_path,
                weights_path=args.weights,
                mode=args.mode,
                conf_threshold=args.conf,
                ng_void_threshold=args.ng_void,
                undersize_threshold=args.undersize,
                area_reference_mode=args.reference_mode,
                device=target_device,
                save_debug_image=False,
            )

            # 5.2 载入 InspectionSession 执行标准引脚位号推导与状态统计
            session = InspectionSession()
            session.load_from_pipeline_result(
                image_path=img_path,
                raw_mat=raw_bgr,
                result=res,
                ng_void_thresh=args.ng_void,
                undersize_thresh=args.undersize,
            )
            elapsed_ms = (time.time() - t_img_start) * 1000.0
            session.elapsed_ms = elapsed_ms

            status = session.board_status  # "PASS" 或 "NG"
            if status == "PASS":
                pass_count += 1
                status_symbol = "✅ PASS"
            else:
                ng_count += 1
                status_symbol = "❌ NG"

            # 5.3 调用客户端风格矢量渲染器生成图像
            out_img_name = f"{base_stem}_inspected_{status}.jpg"
            out_img_path = os.path.join(args.output, out_img_name)

            render_client_style_inspection_image(
                image_path=img_path,
                session=session,
                output_path=out_img_path,
                view_mode=args.view_mode,
                include_banner=not args.no_banner,
                include_legend=not args.no_legend,
                image_quality=args.quality,
                chip_label=fname,
            )

            # 5.4 控制台状态回显
            solder_cnt = len(session.solder_records)
            void_ng_cnt = sum(1 for r in session.solder_records if r.final_is_ng and r.is_void_ng)
            insuff_cnt = sum(1 for r in session.solder_records if r.final_is_ng and r.is_insufficient)
            bridge_cnt = len([b for b in session.bridge_defects if not b.get("is_reviewed_pass", False)])

            print(f"    └─ 结论: {status_symbol}  |  耗时: {elapsed_ms:.1f}ms  |  焊球总数: {solder_cnt}")
            print(f"       缺陷明细: 空洞NG: {void_ng_cnt} | 桥连短路: {bridge_cnt} | 虚焊少锡: {insuff_cnt}")
            if session.ng_reasons:
                print("       ⚠️ 不良判据:")
                for r in session.ng_reasons[:3]:
                    print(f"          • {r}")
                if len(session.ng_reasons) > 3:
                    print(f"          • ... 另有 {len(session.ng_reasons) - 3} 项异常")
            print(f"    💾 图像已输出: {out_img_path}")

            summary_records.append({
                "file_name": fname,
                "input_path": img_path,
                "output_image": out_img_path,
                "status": status,
                "solder_count": solder_cnt,
                "void_ng_count": void_ng_cnt,
                "bridge_defect_count": bridge_cnt,
                "insufficient_count": insuff_cnt,
                "elapsed_ms": round(elapsed_ms, 1),
                "ng_reasons": session.ng_reasons,
            })

        except Exception as e:
            print(f"    [FAIL] 处理失败: {e}")
            import traceback
            traceback.print_exc()

    # 6. 生成汇总 JSON (可选)
    total_elapsed = time.time() - total_start_time
    total_images = len(input_images)
    pass_rate = (pass_count / total_images * 100.0) if total_images > 0 else 0.0

    if not args.no_json:
        json_report_path = os.path.join(args.output, "batch_inspection_summary.json")
        try:
            with open(json_report_path, "w", encoding="utf-8") as jf:
                json.dump({
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "total_images": total_images,
                    "pass_count": pass_count,
                    "ng_count": ng_count,
                    "pass_rate_percent": round(pass_rate, 2),
                    "total_elapsed_seconds": round(total_elapsed, 2),
                    "inspection_config": {
                        "mode": args.mode,
                        "view_mode": args.view_mode,
                        "ng_void_threshold": args.ng_void,
                        "undersize_threshold": args.undersize,
                        "weights_path": args.weights,
                    },
                    "results": summary_records,
                }, jf, ensure_ascii=False, indent=2)
            print(f"\n📊 质检清单数据已导出: {json_report_path}")
        except Exception as e:
            print(f"[WARN] 保存 JSON 数据失败: {e}")

    # 7. 打印最终完成统计卡片
    print("\n" + "=" * 76)
    print("🎉 客户端风格质检结果图像批量导出完成！")
    print("=" * 76)
    print(f"  • 处理图片总量 : {total_images} 张")
    print(f"  • 合格良品 (PASS) : {pass_count} 张 ({pass_rate:.1f}%)")
    print(f"  • 缺陷工件 (NG)   : {ng_count} 张 ({100.0 - pass_rate:.1f}%)")
    print(f"  • 整体运行总耗时 : {total_elapsed:.2f} 秒 (平均 {(total_elapsed / total_images * 1000.0):.1f} ms/张)")
    print(f"  • 结果输出文件夹 : {os.path.abspath(args.output)}")
    print("=" * 76)


if __name__ == "__main__":
    main()
