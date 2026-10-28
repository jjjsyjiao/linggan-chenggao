"""OpenTracing 兼容的 Trace 上下文：trace_id、span_id、W3C traceparent 解析与注入。"""

import secrets
from contextvars import ContextVar

# W3C Trace Context: trace_id 32 位十六进制，span_id 16 位十六进制
TRACE_ID_BYTES = 16  # 32 hex chars
SPAN_ID_BYTES = 8    # 16 hex chars

trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="")
span_id_ctx: ContextVar[str] = ContextVar("span_id", default="")
parent_span_id_ctx: ContextVar[str] = ContextVar("parent_span_id", default="")


def _random_hex(num_bytes: int) -> str:
    return secrets.token_hex(num_bytes)


def generate_trace_id() -> str:
    """生成符合 W3C 的 32 位十六进制 trace_id。"""
    return _random_hex(TRACE_ID_BYTES)


def generate_span_id() -> str:
    """生成符合 W3C 的 16 位十六进制 span_id。"""
    return _random_hex(SPAN_ID_BYTES)


def set_trace_context(
    trace_id: str | None = None,
    span_id: str | None = None,
    parent_span_id: str | None = None,
) -> tuple[str, str]:
    """
    设置当前上下文的 trace_id、span_id。
    若未传入则自动生成，返回 (trace_id, span_id)。
    """
    tid = trace_id or generate_trace_id()
    sid = span_id or generate_span_id()
    trace_id_ctx.set(tid)
    span_id_ctx.set(sid)
    if parent_span_id is not None:
        parent_span_id_ctx.set(parent_span_id)
    return tid, sid


def get_trace_id() -> str:
    return trace_id_ctx.get() or ""


def get_span_id() -> str:
    return span_id_ctx.get() or ""


def get_parent_span_id() -> str:
    return parent_span_id_ctx.get() or ""


def get_trace_context() -> dict[str, str]:
    """返回 OpenTracing 风格的上下文字典，便于写入日志。"""
    return {
        "trace_id": get_trace_id(),
        "span_id": get_span_id(),
        "parent_span_id": get_parent_span_id(),
    }


def parse_traceparent(header_value: str | None) -> tuple[str | None, str | None]:
    """
    解析 W3C traceparent 头：version-trace_id-span_id-flags。
    返回 (trace_id, parent_span_id)，解析失败返回 (None, None)。
    """
    if not header_value or not header_value.strip():
        return None, None
    parts = header_value.strip().split("-")
    if len(parts) != 4:
        return None, None
    _version, tid, parent_sid, _flags = parts
    if len(tid) != 32 or len(parent_sid) != 16:
        return None, None
    try:
        int(tid, 16)
        int(parent_sid, 16)
    except ValueError:
        return None, None
    return tid, parent_sid


def build_traceparent(trace_id: str, span_id: str, sampled: bool = True) -> str:
    """构造 W3C traceparent 头：00-{trace_id}-{span_id}-{flags}。"""
    flags = "01" if sampled else "00"
    return f"00-{trace_id}-{span_id}-{flags}"
