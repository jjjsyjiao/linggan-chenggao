"""HTTP 请求统一 Trace 中间件：记录请求参数、返回结果及 OpenTracing 上下文。"""

import json
import time
from typing import Any

from fastapi import Request
from starlette.requests import Request as StarletteRequest

from app.observability.logging import get_logger
from app.observability.trace import (
    build_traceparent,
    get_span_id,
    get_trace_id,
    parse_traceparent,
    set_trace_context,
)

logger = get_logger(__name__)

# 请求/响应体日志最大长度（字符），超出截断
MAX_BODY_LOG_LEN = 2048
# 需脱敏的键名（不区分大小写）
SENSITIVE_KEYS = frozenset({"password", "api_key", "apikey", "secret", "token", "authorization"})


def _mask_sensitive(obj: Any) -> Any:
    """递归脱敏：将敏感字段值替换为 ***。"""
    if isinstance(obj, dict):
        return {k: "***" if (k and k.lower() in SENSITIVE_KEYS) else _mask_sensitive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mask_sensitive(i) for i in obj]
    return obj


def _truncate(s: str, max_len: int = MAX_BODY_LOG_LEN) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len] + "...[truncated]"


async def _get_request_body_for_log(request: Request) -> tuple[bytes, Request]:
    """
    读取请求体并返回 (body_bytes, new_request)，new_request 的 receive 会返回已缓存的 body，
    供后续路由正常读取。若未消费 body 则 new_request 即原 request。
    """
    # 仅对可能有 body 的方法尝试读取
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return b"", request
    # 文件上传保持流式处理；读取整个 multipart 会把几十 MB 图片复制到内存并写入日志。
    content_type = request.headers.get("content-type", "").lower()
    if "multipart/" in content_type:
        return b"", request
    length = request.headers.get("content-length")
    if not length or not length.isdigit() or int(length) > MAX_BODY_LOG_LEN:
        return b"", request
    try:
        body_bytes = await request.body()
    except Exception:
        return b"", request

    async def receive():
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    new_request = StarletteRequest(request.scope, receive)
    return body_bytes, new_request


def _body_preview(body_bytes: bytes) -> str | None:
    """生成可打印的请求/响应体预览，JSON 则脱敏并截断。"""
    if not body_bytes:
        return None
    try:
        text = body_bytes.decode("utf-8", errors="replace").strip()
        if not text:
            return None
        obj = json.loads(text)
        masked = _mask_sensitive(obj)
        return _truncate(json.dumps(masked, ensure_ascii=False, default=str))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _truncate(body_bytes.decode("utf-8", errors="replace"))


async def http_trace_middleware(request: Request, call_next):
    """
    统一 Trace 中间件：解析/生成 trace_id/span_id，标准打印请求参数与返回结果，
    并注入 W3C traceparent 响应头（符合 OpenTracing 生态）。
    """
    # 1. 解析或生成 Trace 上下文，与 request_id 对齐
    traceparent = request.headers.get("traceparent")
    tid, parent_sid = parse_traceparent(traceparent)
    trace_id, span_id = set_trace_context(trace_id=tid, parent_span_id=parent_sid or None)
    request.state.trace_id = trace_id
    request.state.span_id = span_id
    # 与现有 request_id 对齐：若无 X-Request-ID 则用 trace_id 作为 request_id（在 main 里 set_request_id 会用 header 或 uuid，这里只设置 state，主入口用 trace_id 设 request_id 见 main）
    # 此处仅设置 trace 上下文；request_id 仍在 main 的 request_id_middleware 里设置，我们保持 trace_id 与 request_id 可一致由 main 层统一用 trace_id 赋 request_id

    # 2. 读取请求体并构造可被后续路由使用的 request
    body_bytes, req_to_call = await _get_request_body_for_log(request)
    query_params = dict(req_to_call.query_params) if req_to_call.query_params else None
    request_preview = _body_preview(body_bytes)

    # 3. 请求开始日志（OpenTracing 风格：trace_id, span_id）
    logger.info(
        "http_request_start",
        method=req_to_call.method,
        path=req_to_call.url.path,
        query=query_params,
        body_preview=request_preview,
        trace_id=trace_id,
        span_id=span_id,
    )

    start = time.perf_counter()
    response = await call_next(req_to_call)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    # 4. 响应体预览（仅对非流式、可读 body 的 Response）
    response_preview = None
    if hasattr(response, "body") and response.body:
        response_preview = _body_preview(response.body)

    # 5. 响应结束日志
    logger.info(
        "http_request_finish",
        method=req_to_call.method,
        path=req_to_call.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
        response_preview=response_preview,
        trace_id=get_trace_id(),
        span_id=get_span_id(),
    )

    # 6. 注入 W3C traceparent 响应头
    response.headers["traceparent"] = build_traceparent(trace_id, span_id)
    return response
