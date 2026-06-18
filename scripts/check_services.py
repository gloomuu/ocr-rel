#!/usr/bin/env python3
"""现场环境 OCR / 大模型连通性检测脚本。

默认读取项目根目录 `.env` 中的配置，检测：
1. 本地 Paddle OCR HTTP 服务（OCR_SERVER_URL，POST /ocr/single）
2. 大模型 API（LLM_BASE_URL + LLM_MODEL）
   - 文本 JSON 调用
   - 多模态读图调用（仅当模型名判定支持 vision 时）

用法（在项目根目录执行）：

    PYTHONPATH=src python scripts/check_services.py
    PYTHONPATH=src python scripts/check_services.py --image /path/to/test.jpg
    PYTHONPATH=src python scripts/check_services.py --skip-llm
    PYTHONPATH=src python scripts/check_services.py --skip-ocr
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

# 允许在项目根目录直接运行：PYTHONPATH=src python scripts/check_services.py
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ocr_rel.config import settings  # noqa: E402
from ocr_rel.llm.client import LlmClient  # noqa: E402
from ocr_rel.llm.vision import model_supports_vision  # noqa: E402
from ocr_rel.ocr.local_engine import LocalHttpOcrClient  # noqa: E402


@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str
    elapsed_ms: int = 0
    detail: str = ""


@dataclass
class Report:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(item.ok for item in self.results)

    def add(self, result: CheckResult) -> None:
        self.results.append(result)

    def print_summary(self) -> None:
        print("\n" + "=" * 60)
        print("检测结果汇总")
        print("=" * 60)
        for item in self.results:
            status = "PASS" if item.ok else "FAIL"
            print(f"[{status}] {item.name} ({item.elapsed_ms} ms)")
            print(f"       {item.message}")
            if item.detail:
                preview = item.detail if len(item.detail) <= 300 else item.detail[:300] + "..."
                print(f"       详情: {preview}")
        print("-" * 60)
        if self.passed:
            print("全部检测通过。")
        else:
            failed = [item.name for item in self.results if not item.ok]
            print(f"以下检测失败: {', '.join(failed)}")


def _load_image(image_path: str | None) -> Image.Image:
    if image_path:
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"图片不存在: {path}")
        return Image.open(path).convert("RGB")
    return _make_sample_image()


def _make_sample_image() -> Image.Image:
    image = Image.new("RGB", (480, 160), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 460, 140), outline=(0, 0, 0), width=2)
    draw.text((40, 60), "OCR连通性测试 91440300682024797J", fill=(0, 0, 0))
    return image


async def check_ocr_health(report: Report) -> None:
    name = "OCR 健康检查 GET /health"
    url = f"{settings.ocr_server_url.rstrip('/')}/health"
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
        elapsed = int((time.perf_counter() - started) * 1000)
        status = payload.get("status", payload)
        model_loaded = payload.get("model_loaded")
        detail = f"status={status}"
        if model_loaded is not None:
            detail += f", model_loaded={model_loaded}"
        report.add(
            CheckResult(
                name=name,
                ok=True,
                message=f"OCR 服务可达: {url}",
                elapsed_ms=elapsed,
                detail=detail,
            )
        )
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        report.add(
            CheckResult(
                name=name,
                ok=False,
                message=f"无法访问 OCR 健康检查: {url}",
                elapsed_ms=elapsed,
                detail=str(exc),
            )
        )


async def check_ocr_single(report: Report, image: Image.Image) -> None:
    name = "OCR 识别 POST /ocr/single"
    client = LocalHttpOcrClient()
    started = time.perf_counter()
    try:
        text = await client.recognize_image(image)
        blocks = await client.recognize_blocks(client.encode_image(image))
        elapsed = int((time.perf_counter() - started) * 1000)
        if not text.strip():
            report.add(
                CheckResult(
                    name=name,
                    ok=False,
                    message="OCR 返回空文本，请检查服务或调低 OCR_CONFIDENCE_THRESHOLD",
                    elapsed_ms=elapsed,
                    detail=f"blocks={len(blocks)}",
                )
            )
            return
        report.add(
            CheckResult(
                name=name,
                ok=True,
                message=f"OCR 识别成功，共 {len(blocks)} 个文本块",
                elapsed_ms=elapsed,
                detail=text.replace("\n", " | "),
            )
        )
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        report.add(
            CheckResult(
                name=name,
                ok=False,
                message=f"OCR 识别失败: {settings.ocr_server_url}",
                elapsed_ms=elapsed,
                detail=f"{exc}\n{traceback.format_exc(limit=2)}",
            )
        )


async def check_llm_config(report: Report) -> bool:
    name = "LLM 配置检查"
    started = time.perf_counter()
    elapsed = int((time.perf_counter() - started) * 1000)
    if not settings.llm_api_key.strip():
        report.add(
            CheckResult(
                name=name,
                ok=False,
                message="LLM_API_KEY 未配置",
                elapsed_ms=elapsed,
            )
        )
        return False
    vision = model_supports_vision(settings.llm_model)
    report.add(
        CheckResult(
            name=name,
            ok=True,
            message=(
                f"LLM 已配置: model={settings.llm_model}, "
                f"base={settings.llm_base_url}, vision={vision}"
            ),
            elapsed_ms=elapsed,
        )
    )
    return True


async def check_llm_text(report: Report) -> None:
    name = "LLM 文本调用 /chat/completions"
    client = LlmClient()
    started = time.perf_counter()
    try:
        result = await client.chat_json(
            system_prompt='你是连通性测试助手。只输出 JSON：{"ok": true, "service": "llm"}',
            user_prompt="请返回测试 JSON。",
        )
        elapsed = int((time.perf_counter() - started) * 1000)
        ok = result.get("ok") is True
        report.add(
            CheckResult(
                name=name,
                ok=ok,
                message="LLM 文本调用成功" if ok else "LLM 返回格式异常",
                elapsed_ms=elapsed,
                detail=str(result),
            )
        )
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        report.add(
            CheckResult(
                name=name,
                ok=False,
                message=f"LLM 文本调用失败: {settings.llm_base_url}",
                elapsed_ms=elapsed,
                detail=str(exc),
            )
        )


async def check_llm_vision(report: Report, image: Image.Image) -> None:
    name = "LLM 多模态读图 /chat/completions"
    if not model_supports_vision(settings.llm_model):
        report.add(
            CheckResult(
                name=name,
                ok=True,
                message=f"当前模型 {settings.llm_model!r} 非多模态，跳过读图测试",
                elapsed_ms=0,
            )
        )
        return

    client = LlmClient()
    started = time.perf_counter()
    try:
        result = await client.chat_json(
            system_prompt=(
                "你是连通性测试助手。"
                '只输出 JSON：{"ok": true, "hasText": true} 或 {"ok": true, "hasText": false}。'
            ),
            user_prompt="请查看图片中是否包含文字，并返回 JSON。",
            images=[image],
        )
        elapsed = int((time.perf_counter() - started) * 1000)
        ok = result.get("ok") is True
        report.add(
            CheckResult(
                name=name,
                ok=ok,
                message="LLM 多模态读图成功" if ok else "LLM 多模态返回格式异常",
                elapsed_ms=elapsed,
                detail=str(result),
            )
        )
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        report.add(
            CheckResult(
                name=name,
                ok=False,
                message=f"LLM 多模态读图失败: {settings.llm_model}",
                elapsed_ms=elapsed,
                detail=str(exc),
            )
        )


def _print_config() -> None:
    print("=" * 60)
    print("现场依赖服务连通性检测")
    print("=" * 60)
    print(f"OCR_ENGINE          = {settings.ocr_engine}")
    print(f"OCR_SERVER_URL      = {settings.ocr_server_url}")
    print(f"OCR_CONFIDENCE      = {settings.ocr_confidence_threshold}")
    print(f"OCR_TIMEOUT         = {settings.ocr_timeout}s")
    print(f"LLM_BASE_URL        = {settings.llm_base_url}")
    print(f"LLM_MODEL           = {settings.llm_model}")
    print(f"LLM_TIMEOUT         = {settings.llm_timeout}s")
    print(f"LLM_API_KEY         = {'已配置' if settings.llm_api_key else '未配置'}")
    print(f"EXTRACTION_STRATEGY = {settings.extraction_strategy}")
    print("-" * 60)


async def run_checks(*, image_path: str | None, skip_ocr: bool, skip_llm: bool) -> Report:
    report = Report()
    image = _load_image(image_path)

    if not skip_ocr:
        if settings.ocr_engine != "local":
            report.add(
                CheckResult(
                    name="OCR 引擎提示",
                    ok=True,
                    message=(
                        f"当前 OCR_ENGINE={settings.ocr_engine}，"
                        "本脚本主要检测本地 HTTP Paddle 服务（OCR_SERVER_URL）。"
                    ),
                )
            )
        await check_ocr_health(report)
        await check_ocr_single(report, image)
    else:
        report.add(CheckResult(name="OCR 检测", ok=True, message="已跳过 (--skip-ocr)"))

    if not skip_llm:
        if await check_llm_config(report):
            await check_llm_text(report)
            await check_llm_vision(report, image)
    else:
        report.add(CheckResult(name="LLM 检测", ok=True, message="已跳过 (--skip-llm)"))

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="现场 OCR / 大模型连通性检测")
    parser.add_argument(
        "--image",
        help="用于 OCR / 多模态测试的图片路径；不传则使用内置测试图",
    )
    parser.add_argument("--skip-ocr", action="store_true", help="跳过 OCR 服务检测")
    parser.add_argument("--skip-llm", action="store_true", help="跳过 LLM 服务检测")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _print_config()
    report = asyncio.run(
        run_checks(
            image_path=args.image,
            skip_ocr=args.skip_ocr,
            skip_llm=args.skip_llm,
        )
    )
    report.print_summary()
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
