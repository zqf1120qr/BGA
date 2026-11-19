# -*- coding: utf-8 -*-
"""
X射线智能工业质检工作站 - 静默自检模块 (Self Test)
====================================================================
用途：不打开任何窗口，快速验证「依赖库 → 推理设备 → 模型权重 → 四条质检
      流水线 → Excel/PDF 报表导出」整条链路是否完好。

价值：打包时裁剪了 CUDA 子库（cuFFT/cuSOLVER/cuSPARSE/NVRTC 等），
      一旦误删关键库，界面能正常打开但点「开始检测」才崩溃。本自检
      把这类隐性事故前移到交付前一键暴露。

用法：
    X-Ray_AI_Inspector.exe --selftest
    X-Ray_AI_Inspector.exe --selftest --image D:\\samples\\a.jpg
    X-Ray_AI_Inspector.exe --selftest --no-cpu          # 跳过 CPU 降级复测
    python desktop_app/main.py --selftest

输出：控制台（源码模式）+ 程序目录 selftest_report.txt
退出码：0 = 全部通过，1 = 存在失败项
"""
from __future__ import annotations

import datetime
import os
import platform
import sys
import time
import traceback

SELFTEST_OUTPUT_DIRNAME = "selftest_output"
REPORT_FILENAME = "selftest_report.txt"

# GPU 推理硬依赖及 torch_cuda.dll 静态 PE 导入表必需库（缺失会导致干净客户机 WinError 126）
REQUIRED_TORCH_DLLS = [
    "torch_cuda.dll", "torch_cpu.dll", "c10.dll", "c10_cuda.dll",
    "cudart64_12.dll", "cupti64_2025.1.1.dll",
    "cudnn64_9.dll", "cudnn_ops64_9.dll", "cudnn_cnn64_9.dll",
    "cudnn_graph64_9.dll", "cudnn_heuristic64_9.dll",
    "cudnn_engines_precompiled64_9.dll",
    "cudnn_engines_runtime_compiled64_9.dll",
    "cublas64_12.dll", "cublasLt64_12.dll",
    "cufft64_11.dll", "cusolver64_11.dll", "cusparse64_12.dll",
    "nvrtc64_120_0.dll", "nvJitLink_120_0.dll",
]

# 已通过 PE 导入表递归确认可安全裁剪的无静态依赖子库（存在仅提示，不算失败）
SLIMMED_TORCH_DLLS = [
    "cufftw64_11.dll", "cusolverMg64_11.dll",
    "curand64_10.dll", "cudnn_adv64_9.dll",
    "nvperf_host.dll",
]

_REQUIRED_MODULES = ["torch", "torchvision", "cv2", "numpy", "scipy", "pandas",
                     "openpyxl", "reportlab", "matplotlib", "PySide6"]


class _Report:
    """自检报告收集器：控制台 + 文本文件双通道"""

    def __init__(self):
        self.lines = []
        self.failures = 0
        self.warnings = 0
        self._t0 = time.time()

    def _emit(self, tag, msg):
        line = f"[{tag}] {msg}" if tag else msg
        self.lines.append(line)
        try:
            print(line, flush=True)
        except Exception:
            pass

    def section(self, title):
        self._emit("", "")
        self._emit("", f"===== {title} =====")

    def ok(self, msg):
        self._emit(" OK ", msg)

    def info(self, msg):
        self._emit("INFO", msg)

    def warn(self, msg):
        self.warnings += 1
        self._emit("WARN", msg)

    def fail(self, msg):
        self.failures += 1
        self._emit("FAIL", msg)

    def exception(self, msg, exc):
        self.failures += 1
        self._emit("FAIL", f"{msg} -> {type(exc).__name__}: {exc}")
        detail = traceback.format_exc()
        for line in detail.strip().splitlines()[-6:]:
            self._emit("", f"       {line}")


def _resolve_dirs():
    """返回 (程序目录, 资源根目录)，与 app_config 的解析口径保持一致"""
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(os.path.abspath(sys.executable))
        base_dir = getattr(sys, "_MEIPASS", app_dir)
    else:
        desktop_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(desktop_dir)
        app_dir = base_dir
    return os.path.abspath(app_dir), os.path.abspath(base_dir)


def _file_mb(path):
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except OSError:
        return 0.0


def _file_size_text(path):
    """小于 0.1 MB 时用 KB 显示，避免报表体积被四舍五入成 0.0 MB"""
    size_mb = _file_mb(path)
    if size_mb >= 0.1:
        return f"{size_mb:.1f} MB"
    return f"{size_mb * 1024:.0f} KB"


def _build_sample_image(target_path):
    """现场无样例图时，现场合成一张带焊球阵列与空洞的测试图"""
    import cv2
    import numpy as np

    size = 1024
    canvas = np.full((size, size), 35, dtype=np.uint8)
    for row in range(4):
        for col in range(4):
            cx = 170 + col * 225
            cy = 170 + row * 225
            cv2.circle(canvas, (cx, cy), 72, 205, -1)
            cv2.circle(canvas, (cx, cy), 22, 80, -1)
    color = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
    ok, buf = cv2.imencode(".jpg", color)
    if not ok:
        raise RuntimeError("合成测试图编码失败")
    buf.tofile(target_path)
    return target_path


def _locate_sample_image(explicit_image, base_dir, out_dir):
    """样例图优先级：命令行指定 > 源码目录 data/imgs > 合成图"""
    if explicit_image:
        explicit_image = os.path.abspath(explicit_image)
        if os.path.exists(explicit_image):
            return explicit_image, "命令行指定"
        return None, f"命令行指定的图片不存在: {explicit_image}"

    img_dir = os.path.join(base_dir, "data", "imgs")
    if os.path.isdir(img_dir):
        for name in sorted(os.listdir(img_dir)):
            if name.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                return os.path.join(img_dir, name), "项目样例图"

    sample = os.path.join(out_dir, "selftest_sample.jpg")
    return _build_sample_image(sample), "自动合成"


def _check_modules(report):
    for name in _REQUIRED_MODULES:
        try:
            module = __import__(name)
            version = getattr(module, "__version__", "") or getattr(module, "VERSION", "")
            report.ok(f"{name:<12} {version}")
        except Exception as exc:
            report.exception(f"依赖 {name} 导入失败", exc)


def _check_torch_runtime(report):
    """校验 torch 运行时与 CUDA 关键库完整性"""
    try:
        import torch
    except Exception as exc:
        report.exception("torch 导入失败", exc)
        return None

    lib_dir = os.path.join(os.path.dirname(torch.__file__), "lib")
    report.info(f"torch 版本: {torch.__version__}")
    report.info(f"torch 运行库目录: {lib_dir}")

    if not os.path.isdir(lib_dir):
        report.warn("未找到 torch/lib 目录，跳过关键库校验")
        return torch

    missing = [name for name in REQUIRED_TORCH_DLLS
               if not os.path.exists(os.path.join(lib_dir, name))]
    if missing:
        report.fail("GPU 推理关键库缺失: " + ", ".join(missing))
    else:
        report.ok(f"GPU 推理关键库齐全 ({len(REQUIRED_TORCH_DLLS)} 个)")

    leftover = [name for name in SLIMMED_TORCH_DLLS
                if os.path.exists(os.path.join(lib_dir, name))]
    if leftover:
        report.info(f"体积精简未完全生效，仍存在: {', '.join(leftover)}")
    else:
        report.ok("体积精简生效（无关 CUDA 子库已剔除）")

    cuda_ok = False
    try:
        cuda_ok = bool(torch.cuda.is_available())
    except Exception as exc:
        report.exception("torch.cuda.is_available() 调用异常", exc)

    if cuda_ok:
        try:
            report.ok(f"CUDA 可用: {torch.cuda.get_device_name(0)}")
        except Exception:
            report.ok("CUDA 可用")
    else:
        report.warn("CUDA 不可用，本次将只验证 CPU 推理链路")
    return torch


def _resolve_device(report):
    """与主程序一致：auto 优先 GPU，无独显平滑降级 CPU"""
    try:
        from desktop_app.core.hardware_sniff import HardwareSniffer
        sniffer = HardwareSniffer()
        device, status_text, _color = sniffer.resolve_device("auto")
        report.ok(f"推理设备解析: {device}  ({status_text})")
        return device
    except Exception as exc:
        report.exception("硬件嗅探失败，回退 CPU", exc)
        return "cpu"


def _resolve_weights(report, app_dir, base_dir):
    candidates = [
        os.path.join(app_dir, "backend", "best.pt"),
        os.path.join(app_dir, "best.pt"),
        os.path.join(base_dir, "backend", "best.pt"),
        os.path.join(base_dir, "best.pt"),
    ]
    for path in candidates:
        if os.path.exists(path):
            report.ok(f"模型权重: {path} ({_file_mb(path):.1f} MB)")
            return path
    report.fail("未找到模型权重 best.pt，请检查安装包完整性")
    return None


def _run_pipelines(report, image_path, weights_path, device):
    """跑通四条质检流水线，返回综合模式结果供报表复测使用"""
    try:
        from xray_pipeline import (inspect_bga_bridge, inspect_bga_comprehensive,
                                   inspect_bga_insufficient, inspect_bga_void)
    except Exception as exc:
        report.exception("质检流水线模块导入失败", exc)
        return None

    cases = [
        ("气泡检测 void", inspect_bga_void),
        ("桥连检测 bridge", inspect_bga_bridge),
        ("虚焊检测 insufficient", inspect_bga_insufficient),
        ("综合检测 comprehensive", inspect_bga_comprehensive),
    ]
    comprehensive_result = None
    for label, func in cases:
        started = time.time()
        try:
            result = func(input_image_path=image_path, weights_path=weights_path, device=device)
            elapsed = (time.time() - started) * 1000.0
            status = result.get("board_status", "?")
            summary = result.get("summary") or {}
            balls = summary.get("solder_count", len(result.get("void_details") or []))
            bridges = summary.get("bridge_defect_count", len(result.get("bridge_details") or []))
            unsatisfied = summary.get("insufficient_solder_count", 0)
            report.ok(f"{label:<24} {elapsed:8.0f} ms  判定={status}  焊球={balls}"
                      f"  桥连={bridges}  虚焊={unsatisfied}")
            if func is inspect_bga_comprehensive:
                comprehensive_result = result
        except Exception as exc:
            report.exception(f"{label} 执行失败", exc)
    return comprehensive_result


def _run_reports(report, image_path, raw_mat, pipeline_result, out_dir):
    """用与界面完全相同的链路重建会话并导出 Excel / PDF 报表"""
    if not pipeline_result:
        report.warn("综合检测未产出结果，跳过报表导出复测")
        return

    try:
        from desktop_app.core.inspection_manager import InspectionSession
        from desktop_app.utils.excel_reporter import export_inspection_excel
        from desktop_app.utils.pdf_reporter import export_inspection_pdf
    except Exception as exc:
        report.exception("报表模块导入失败", exc)
        return

    try:
        session = InspectionSession()
        session.load_from_pipeline_result(
            image_path=image_path,
            raw_mat=raw_mat,
            result=pipeline_result,
            ng_void_thresh=0.25,
            undersize_thresh=0.20,
        )
        stats = session.get_summary_stats()
        stats["void_threshold"] = 0.25
        stats["reduction_threshold"] = 0.20
        report.ok(f"会话重建: 焊球 {stats.get('total_solders')} 个，判定 {stats.get('board_status')}")
    except Exception as exc:
        report.exception("质检会话重建失败", exc)
        return

    xlsx_path = os.path.join(out_dir, "selftest_report.xlsx")
    try:
        export_inspection_excel(
            save_path=xlsx_path,
            image_name=os.path.basename(image_path),
            summary_stats=stats,
            records=session.solder_records,
        )
        if _file_mb(xlsx_path) > 0:
            report.ok(f"Excel 导出成功: {xlsx_path} ({_file_size_text(xlsx_path)})")
        else:
            report.fail("Excel 导出结果为空文件")
    except Exception as exc:
        report.exception("Excel 导出失败", exc)

    pdf_path = os.path.join(out_dir, "selftest_report.pdf")
    try:
        export_inspection_pdf(
            save_path=pdf_path,
            image_name=os.path.basename(image_path),
            summary_stats=stats,
            records=session.solder_records,
            preview_img_path=session.inspected_image_path,
            image_path=image_path,
            bridge_defects=session.bridge_defects,
        )
        if _file_mb(pdf_path) > 0:
            report.ok(f"PDF 导出成功: {pdf_path} ({_file_size_text(pdf_path)})")
        else:
            report.fail("PDF 导出结果为空文件")
    except Exception as exc:
        report.exception("PDF 导出失败", exc)


def _run_cpu_fallback(report, image_path, weights_path):
    """GPU 机器上额外验证 CPU 降级链路，确保无独显客户机也能跑"""
    try:
        from xray_pipeline import inspect_bga_bridge
    except Exception as exc:
        report.exception("CPU 复测时流水线导入失败", exc)
        return
    started = time.time()
    try:
        result = inspect_bga_bridge(input_image_path=image_path,
                                    weights_path=weights_path,
                                    device="cpu")
        elapsed = (time.time() - started) * 1000.0
        report.ok(f"{'CPU 降级推理 bridge':<24} {elapsed:8.0f} ms  判定={result.get('board_status', '?')}")
    except Exception as exc:
        report.exception("CPU 降级推理失败", exc)


def _write_report_file(report, app_dir, header_lines):
    path = os.path.join(app_dir, REPORT_FILENAME)
    body = []
    body.extend(header_lines)
    body.extend(report.lines)
    body.append("")
    body.append("=" * 60)
    body.append(f"结论: {'全部通过' if report.failures == 0 else f'存在 {report.failures} 项失败'}"
                f"（警告 {report.warnings} 项），总耗时 {time.time() - report._t0:.1f}s")
    content = "\n".join(body) + "\n"
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path
    except Exception:
        return None


def _attach_parent_console():
    """
    当打包为无黑框 GUI 程序 (console=False) 且用户从 cmd/PowerShell 触发 --selftest 时，
    主动挂载父进程控制台并重定向 stdout/stderr，使命令行能实时看到自检输出。
    """
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ATTACH_PARENT_PROCESS = -1
        if kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            con_out = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
            sys.stdout = con_out
            sys.stderr = con_out
            print("", flush=True)
    except Exception:
        pass


def run_selftest(argv=None):
    """静默自检入口，返回进程退出码（0 通过 / 1 失败）"""
    _attach_parent_console()
    argv = list(sys.argv[1:] if argv is None else argv)
    explicit_image = None
    if "--image" in argv:
        idx = argv.index("--image")
        if idx + 1 < len(argv):
            explicit_image = argv[idx + 1]
    skip_cpu = "--no-cpu" in argv

    app_dir, base_dir = _resolve_dirs()
    out_dir = os.path.join(app_dir, SELFTEST_OUTPUT_DIRNAME)
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        out_dir = app_dir

    report = _Report()
    started_at = datetime.datetime.now()

    report.section("0. 运行环境")
    report.info(f"程序目录: {app_dir}")
    report.info(f"运行模式: {'PyInstaller 二进制包' if getattr(sys, 'frozen', False) else '源码模式'}")
    report.info(f"操作系统: {platform.platform()}")
    report.info(f"Python  : {platform.python_version()}")
    report.info(f"CPU 核心: {os.cpu_count()}")
    report.info(f"输出目录: {out_dir}")

    report.section("1. 依赖库导入")
    _check_modules(report)

    report.section("2. 推理运行时与 CUDA 关键库")
    _check_torch_runtime(report)

    report.section("3. 设备与模型")
    device = _resolve_device(report)
    weights_path = _resolve_weights(report, app_dir, base_dir)

    report.section("4. 样例图准备")
    image_path, image_source = _locate_sample_image(explicit_image, base_dir, out_dir)
    if image_path:
        report.ok(f"测试图: {image_path} ({image_source})")
    else:
        report.fail(image_source)

    report.section("5. 四条质检流水线")
    comprehensive_result = None
    raw_mat = None
    if image_path and weights_path:
        try:
            import cv2
            import numpy as np
            raw_mat = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if raw_mat is None:
                report.fail("测试图解码失败")
        except Exception as exc:
            report.exception("测试图解码异常", exc)
        comprehensive_result = _run_pipelines(report, image_path, weights_path, device)
    else:
        report.warn("缺少测试图或模型权重，跳过流水线验证")

    report.section("6. 报表导出链路")
    if comprehensive_result is not None and raw_mat is not None:
        _run_reports(report, image_path, raw_mat, comprehensive_result, out_dir)
    else:
        report.warn("无可用检测结果，跳过报表导出")

    if device != "cpu" and not skip_cpu and image_path and weights_path:
        report.section("7. CPU 降级复测")
        _run_cpu_fallback(report, image_path, weights_path)

    report.section("8. 自检结论")
    if report.failures == 0:
        report.ok(f"全部检查通过（警告 {report.warnings} 项），耗时 {time.time() - report._t0:.1f}s")
    else:
        report.fail(f"存在 {report.failures} 项失败，警告 {report.warnings} 项，请查看上方明细")

    header = [
        "X射线智能工业质检工作站 - 静默自检报告",
        f"生成时间: {started_at.strftime('%Y-%m-%d %H:%M:%S')}",
        "-" * 60,
    ]
    report_path = _write_report_file(report, app_dir, header)
    if report_path:
        try:
            print(f"\n自检报告已写入: {report_path}", flush=True)
        except Exception:
            pass

    return 0 if report.failures == 0 else 1
