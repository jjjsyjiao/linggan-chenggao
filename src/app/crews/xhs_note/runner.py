"""在可取消的独立进程运行快速生成或完整 Crew 流程。"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from app.observability.logging import get_logger, get_request_id
from app.schemas.xhs_note import XhsGeneratedNote, XhsNoteIdeaRequest

logger = get_logger(__name__)


def _worker_error(reason_code: str, *, error_type: str | None = None, exit_code: int | None = None) -> None:
    """Diagnostics must never include the worker result or exception message."""
    logger.warning(
        "xhs_generation_worker_error",
        reason_code=reason_code,
        error_type=error_type,
        exit_code=exit_code,
    )


async def _stop_process(process):
    if process.returncode is None:
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=2)
        except TimeoutError:
            process.kill()
            await process.wait()


async def _run_isolated_generation(request: XhsNoteIdeaRequest, mode: str):
    result_path = Path(request.images[0].local_path).parent / "result.json"
    environment = dict(os.environ)
    environment["CREWAI_TELEMETRY_DISABLED"] = "true"
    environment["OTEL_SDK_DISABLED"] = "true"
    environment["CREWAI_TESTING"] = "true"
    environment["APP_TOOLS_DIRECTORY_READ_ROOT"] = str(result_path.parent)
    # Context variables do not cross the process boundary. Override any stale
    # inherited value even when this caller has no active HTTP request.
    environment["APP_REQUEST_ID"] = get_request_id()
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "app.crews.xhs_note.worker", str(result_path), mode,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            env=environment,
        )
    except OSError as exc:
        _worker_error("worker_start_failed", error_type=type(exc).__name__)
        return None, "生成进程无法启动，请凭请求 ID 检查服务日志"
    try:
        await process.communicate(request.model_dump_json().encode("utf-8"))
        if process.returncode != 0:
            _worker_error("worker_exit_nonzero", exit_code=process.returncode)
            return None, "生成进程异常退出，请检查服务日志"
        if not result_path.is_file():
            _worker_error("worker_result_missing")
            return None, "生成进程未返回结果，请凭请求 ID 检查服务日志"
        try:
            result = json.loads(await asyncio.to_thread(result_path.read_text, encoding="utf-8"))
        except json.JSONDecodeError:
            _worker_error("worker_result_invalid_json")
            return None, "生成进程返回了无效结果，请凭请求 ID 检查服务日志"
        if not isinstance(result, dict) or not isinstance(result.get("error", ""), str):
            _worker_error("worker_result_invalid_envelope")
            return None, "生成进程结果格式无效，请凭请求 ID 检查服务日志"
        if result.get("error"):
            _worker_error("worker_reported_error")
            return None, result["error"]
        try:
            note = XhsGeneratedNote.model_validate(result.get("note"))
        except ValidationError:
            _worker_error("worker_note_invalid")
            return None, "生成进程未返回完整笔记，请凭请求 ID 检查服务日志"
        return note, ""
    except OSError as exc:
        _worker_error("worker_io_failed", error_type=type(exc).__name__)
        return None, "生成进程通信失败，请凭请求 ID 检查服务日志"
    finally:
        await asyncio.shield(_stop_process(process))


async def run_xhs_note_generation_flow(request: XhsNoteIdeaRequest):
    """客户端：一次视觉请求与本地事实组装。"""
    return await _run_isolated_generation(request, "fast")


async def run_xhs_note_flow(request: XhsNoteIdeaRequest):
    """完整报告保留原有多 Agent 流程。"""
    note, error = await _run_isolated_generation(request, "full")
    return note.report if note else None, error
