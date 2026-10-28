"""可观测性模块的单元测试：logging、metrics、http_trace。"""

import logging
import os
import tempfile
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from app.observability.logging import (
    configure_logging,
    get_logger,
    get_request_id,
    set_request_id,
    add_request_id,
    add_trace_context,
    get_crew_log_file_path,
)
from app.observability.metrics import (
    ai_token_usage_total,
    ai_task_queue_depth,
    crew_execution_seconds,
    ai_agent_error_total,
)


# ---------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------


class TestRequestId:
    def test_set_and_get(self):
        rid = set_request_id("test-rid-123")
        assert rid == "test-rid-123"
        assert get_request_id() == "test-rid-123"

    def test_auto_generate(self):
        rid = set_request_id(None)
        assert len(rid) > 0
        assert get_request_id() == rid

    def test_default_empty(self):
        # Reset context
        from app.observability.logging import request_id_ctx
        token = request_id_ctx.set("")
        assert get_request_id() == ""
        request_id_ctx.reset(token)


class TestAddRequestId:
    def test_adds_request_id(self):
        set_request_id("test-abc")
        event_dict = {"event": "test"}
        result = add_request_id(None, None, event_dict)
        assert result["request_id"] == "test-abc"

    def test_no_request_id(self):
        from app.observability.logging import request_id_ctx
        token = request_id_ctx.set("")
        event_dict = {"event": "test"}
        result = add_request_id(None, None, event_dict)
        assert "request_id" not in result
        request_id_ctx.reset(token)


class TestAddTraceContext:
    def test_adds_trace_ids(self):
        from app.observability.trace import set_trace_context
        set_trace_context("t" * 32, "s" * 16)
        event_dict = {"event": "test"}
        result = add_trace_context(None, None, event_dict)
        assert result["trace_id"] == "t" * 32
        assert result["span_id"] == "s" * 16


class TestConfigureLogging:
    def test_creates_log_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "test_logs")
            configure_logging("INFO", log_dir)
            assert os.path.isdir(log_dir)

    def test_creates_logger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            configure_logging("DEBUG", tmpdir)
            logger = get_logger("test_module")
            assert logger is not None


class TestGetCrewLogFilePath:
    def test_returns_valid_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = get_crew_log_file_path(tmpdir)
            assert path.startswith(tmpdir)
            assert path.endswith(".txt")
            assert "crewai_" in path

    def test_default_dir(self):
        path = get_crew_log_file_path()
        assert "logs" in path

    def test_creates_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sub = os.path.join(tmpdir, "sub", "logs")
            path = get_crew_log_file_path(sub)
            assert os.path.isdir(sub)


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_ai_token_usage_defined(self):
        assert ai_token_usage_total is not None
        # Verify labels
        ai_token_usage_total.labels(model="test", agent_role="test")

    def test_ai_task_queue_depth_defined(self):
        assert ai_task_queue_depth is not None

    def test_crew_execution_seconds_defined(self):
        assert crew_execution_seconds is not None
        crew_execution_seconds.labels(flow_name="test").observe(1.0)

    def test_ai_agent_error_total_defined(self):
        assert ai_agent_error_total is not None
        ai_agent_error_total.labels(agent_role="test", error_type="TestError")


# ---------------------------------------------------------------------------
# http_trace helpers
# ---------------------------------------------------------------------------


class TestHttpTraceHelpers:
    def test_mask_sensitive(self):
        from app.observability.http_trace import _mask_sensitive
        data = {"password": "secret", "name": "test", "nested": {"api_key": "key123"}}
        result = _mask_sensitive(data)
        assert result["password"] == "***"
        assert result["name"] == "test"
        assert result["nested"]["api_key"] == "***"

    def test_mask_sensitive_list(self):
        from app.observability.http_trace import _mask_sensitive
        data = [{"token": "abc"}, {"name": "ok"}]
        result = _mask_sensitive(data)
        assert result[0]["token"] == "***"
        assert result[1]["name"] == "ok"

    def test_truncate(self):
        from app.observability.http_trace import _truncate
        short = "hello"
        assert _truncate(short, 100) == "hello"
        long_str = "x" * 3000
        result = _truncate(long_str, 100)
        assert len(result) < 200
        assert "truncated" in result

    def test_body_preview_json(self):
        from app.observability.http_trace import _body_preview
        body = b'{"password": "secret", "name": "test"}'
        result = _body_preview(body)
        assert "***" in result
        assert "test" in result

    def test_body_preview_empty(self):
        from app.observability.http_trace import _body_preview
        assert _body_preview(b"") is None
        assert _body_preview(b"   ") is None

    def test_body_preview_non_json(self):
        from app.observability.http_trace import _body_preview
        result = _body_preview(b"plain text body")
        assert result == "plain text body"
