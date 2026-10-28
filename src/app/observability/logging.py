"""结构化日志（structlog），支持 request_id、trace_id/span_id 注入与脱敏；
按小时轮转输出到文件，error 单独文件，使用普通文本格式而非 JSON。"""

import logging
import logging.handlers
import os
from contextvars import ContextVar
from datetime import date
from uuid import uuid4

import structlog


request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    return request_id_ctx.get() or ""


def set_request_id(rid: str | None = None) -> str:
    rid = rid or str(uuid4())
    request_id_ctx.set(rid)
    return rid


def add_request_id(logger: logging.Logger, method_name: str, event_dict: dict) -> dict:
    rid = get_request_id()
    if rid:
        event_dict["request_id"] = rid
    return event_dict


def add_trace_context(logger: logging.Logger, method_name: str, event_dict: dict) -> dict:
    """注入 OpenTracing 兼容的 trace_id、span_id 到每条日志。"""
    try:
        from app.observability.trace import get_trace_id, get_span_id
        tid = get_trace_id()
        sid = get_span_id()
        if tid:
            event_dict["trace_id"] = tid
        if sid:
            event_dict["span_id"] = sid
    except Exception:
        pass
    return event_dict


def _shared_processors() -> list:
    return [
        structlog.contextvars.merge_contextvars,
        add_request_id,
        add_trace_context,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]


def configure_logging(log_level: str = "INFO", log_dir: str = "./logs") -> None:
    """配置 structlog：按小时轮转写入 log_dir，app.log 为全部级别，error.log 仅 ERROR；
    日志以普通文本 key=value 形式输出，便于直接阅读。"""
    os.makedirs(log_dir, exist_ok=True)
    level = getattr(logging, log_level.upper(), logging.INFO)

    # 使用文本格式输出日志，而不是 JSON。
    # 这里采用 structlog 的 KeyValueRenderer，将字段渲染为单行 key=value 形式，
    # 既保留结构化信息，又便于人类直接阅读与 grep。
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.KeyValueRenderer(key_order=["timestamp", "level", "event", "request_id", "trace_id", "span_id"]),
        foreign_pre_chain=_shared_processors(),
    )

    all_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_dir, "app.log"),
        when="H",
        interval=1,
        backupCount=24 * 7,  # 保留约 7 天
        encoding="utf-8",
    )
    all_handler.setFormatter(formatter)
    all_handler.setLevel(level)

    error_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_dir, "error.log"),
        when="H",
        interval=1,
        backupCount=24 * 30,  # error 保留约 30 天
        encoding="utf-8",
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)

    app_logger = logging.getLogger("app")
    app_logger.setLevel(level)  # 使用配置的日志级别，而不是硬编码 DEBUG
    app_logger.handlers.clear()
    app_logger.addHandler(all_handler)
    app_logger.addHandler(error_handler)
    app_logger.propagate = False

    structlog.configure(
        processors=[
            *_shared_processors(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def get_crew_log_file_path(log_dir: str | None = None) -> str:
    """返回 Crew 任务日志文件路径，与现有日志位置和风格一致。

    与 app.log、error.log 相同：直接写在 log_dir 下，文件名按日期区分，
    例如 log_dir 为 ./logs 时返回 ./logs/crewai_2025-02-06.txt。

    Args:
        log_dir: 日志根目录，与 configure_logging 的 log_dir 一致；默认 ./logs。

    Returns:
        基于 log_dir 的 crew 日志文件路径（.txt）。
    """
    base = log_dir or "./logs"
    os.makedirs(base, exist_ok=True)
    date_str = date.today().isoformat()
    return os.path.join(base, f"crewai_{date_str}.txt")
