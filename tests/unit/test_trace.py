"""OpenTracing 兼容 Trace 上下文的单元测试。"""

from app.observability.trace import (
    generate_trace_id,
    generate_span_id,
    set_trace_context,
    get_trace_id,
    get_span_id,
    get_parent_span_id,
    get_trace_context,
    parse_traceparent,
    build_traceparent,
)


class TestGenerateIds:
    def test_trace_id_length(self):
        tid = generate_trace_id()
        assert len(tid) == 32
        int(tid, 16)  # should be valid hex

    def test_span_id_length(self):
        sid = generate_span_id()
        assert len(sid) == 16
        int(sid, 16)

    def test_uniqueness(self):
        ids = {generate_trace_id() for _ in range(100)}
        assert len(ids) == 100


class TestSetGetTraceContext:
    def test_set_and_get(self):
        tid, sid = set_trace_context("abc" * 10 + "ab", "1234567890abcdef")
        assert get_trace_id() == "abc" * 10 + "ab"
        assert get_span_id() == "1234567890abcdef"

    def test_auto_generate(self):
        tid, sid = set_trace_context()
        assert len(tid) == 32
        assert len(sid) == 16

    def test_parent_span_id(self):
        set_trace_context(parent_span_id="parentspan1234ab")
        assert get_parent_span_id() == "parentspan1234ab"

    def test_get_trace_context_dict(self):
        set_trace_context("a" * 32, "b" * 16, "c" * 16)
        ctx = get_trace_context()
        assert ctx["trace_id"] == "a" * 32
        assert ctx["span_id"] == "b" * 16
        assert ctx["parent_span_id"] == "c" * 16


class TestParseTraceparent:
    def test_valid(self):
        header = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
        tid, psid = parse_traceparent(header)
        assert tid == "a" * 32
        assert psid == "b" * 16

    def test_none(self):
        tid, psid = parse_traceparent(None)
        assert tid is None
        assert psid is None

    def test_empty(self):
        tid, psid = parse_traceparent("")
        assert tid is None
        assert psid is None

    def test_invalid_format(self):
        tid, psid = parse_traceparent("invalid")
        assert tid is None

    def test_wrong_length(self):
        tid, psid = parse_traceparent("00-abc-def-01")
        assert tid is None

    def test_non_hex(self):
        tid, psid = parse_traceparent("00-" + "g" * 32 + "-" + "h" * 16 + "-01")
        assert tid is None


class TestBuildTraceparent:
    def test_sampled(self):
        result = build_traceparent("a" * 32, "b" * 16, sampled=True)
        assert result == "00-" + "a" * 32 + "-" + "b" * 16 + "-01"

    def test_not_sampled(self):
        result = build_traceparent("a" * 32, "b" * 16, sampled=False)
        assert result.endswith("-00")
