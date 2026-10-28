"""受控生成子进程入口；请求/结果只在本机临时工作目录内传递。"""
import asyncio
import json
import os
import sys
from pathlib import Path

from app.core.config import get_settings
from app.observability.logging import configure_logging, get_logger, set_request_id
from app.schemas.xhs_note import XhsNoteIdeaRequest


def main():
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_dir)
    set_request_id(os.environ.get("APP_REQUEST_ID") or None)
    output = Path(sys.argv[1])
    try:
        mode = sys.argv[2] if len(sys.argv) > 2 else "full"
        if mode == "fast":
            from app.crews.xhs_note.fast_flow import run_fast_note_flow as generate
        elif mode == "full":
            from app.crews.xhs_note.flows import run_xhs_note_generation_flow as generate
        else:
            raise ValueError("未知生成模式")
        request = XhsNoteIdeaRequest.model_validate_json(sys.stdin.buffer.read())
        note, error = asyncio.run(generate(request))
        result = {"note": note.model_dump() if note else None, "error": error}
    except Exception as exc:
        # Exception messages/tracebacks can embed model text or validation
        # input_value. Record only a stable type and code at this boundary.
        get_logger(__name__).error("generation_worker_failed", reason_code="worker_execution_failed", error_type=type(exc).__name__)
        result = {"note": None, "error": "生成进程执行失败，请凭请求 ID 检查服务日志"}
    try:
        output.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        get_logger(__name__).error("generation_worker_failed", reason_code="worker_result_write_failed", error_type=type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
