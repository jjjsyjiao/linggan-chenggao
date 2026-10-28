"""FastAPI 应用创建、API 路由与依赖注入的单元测试。"""

from __future__ import annotations

from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_application, app
from app.api.dependencies import get_request_id


# ---------------------------------------------------------------------------
# create_application
# ---------------------------------------------------------------------------


class TestCreateApplication:
    def test_creates_fastapi_app(self):
        application = create_application()
        assert application is not None
        assert application.title == "Enterprise AI App"

    def test_docs_available_in_dev(self):
        with patch("app.main.get_settings") as mock:
            s = MagicMock()
            s.env = "development"
            s.log_level = "INFO"
            s.log_dir = "./logs"
            s.port = 8072
            mock.return_value = s
            application = create_application()
            assert application.docs_url == "/docs"

    def test_docs_hidden_in_production(self):
        with patch("app.main.get_settings") as mock:
            s = MagicMock()
            s.env = "production"
            s.log_level = "INFO"
            s.log_dir = "./logs"
            s.port = 8072
            mock.return_value = s
            application = create_application()
            assert application.docs_url is None


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


class TestGetRequestId:
    @pytest.mark.asyncio
    async def test_from_header(self):
        request = MagicMock()
        request.headers = {"X-Request-ID": "test-rid-999"}
        rid = await get_request_id(request)
        assert rid == "test-rid-999"

    @pytest.mark.asyncio
    async def test_auto_generate(self):
        request = MagicMock()
        request.headers = {}
        rid = await get_request_id(request)
        assert len(rid) > 0


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------


class TestHealthEndpoints:
    @pytest.mark.asyncio
    async def test_liveness(self):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.get("/health/live")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_readiness(self):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.get("/health/ready")
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert "request_id" in data

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.get("/metrics")
        assert r.status_code == 200
        assert "http_request" in r.text or "process" in r.text


# ---------------------------------------------------------------------------
# XHS Note API endpoint
# ---------------------------------------------------------------------------


class TestXhsNoteApi:
    @pytest.mark.asyncio
    @patch("app.api.v1.xhs_note.generate_xhs_note_report")
    async def test_success(self, mock_generate):
        mock_generate.return_value = ("最终报告内容", "")
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.post(
                "/api/v1/xhs/notes/report",
                data={"idea_text": "测试意图"},
                files=[("images", ("test.jpg", b"\xff\xd8\xff\xe0", "image/jpeg"))],
            )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["report"] == "最终报告内容"

    @pytest.mark.asyncio
    @patch("app.api.v1.xhs_note.generate_xhs_note_report")
    async def test_generation_failure(self, mock_generate):
        mock_generate.return_value = (None, "LLM 调用失败")
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.post(
                "/api/v1/xhs/notes/report",
                data={"idea_text": "测试"},
                files=[("images", ("test.jpg", b"\xff\xd8\xff\xe0", "image/jpeg"))],
            )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 1
        assert "失败" in body["message"]

    @pytest.mark.asyncio
    @patch("app.api.v1.xhs_note.generate_xhs_note_report")
    async def test_exception_handling(self, mock_generate):
        mock_generate.side_effect = RuntimeError("意外错误")
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.post(
                "/api/v1/xhs/notes/report",
                data={"idea_text": "测试"},
                files=[("images", ("test.jpg", b"\xff\xd8\xff\xe0", "image/jpeg"))],
            )
        assert r.status_code == 500

    @pytest.mark.asyncio
    async def test_missing_idea_text(self):
        """缺少 idea_text 应返回 422。"""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.post(
                "/api/v1/xhs/notes/report",
                files=[("images", ("test.jpg", b"\xff\xd8\xff\xe0", "image/jpeg"))],
            )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------


class TestExceptionHandlers:
    @pytest.mark.asyncio
    async def test_404(self):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.get("/nonexistent/path")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_request_id_header_in_response(self):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.get("/health/live", headers={"X-Request-ID": "my-rid"})
        assert "X-Request-ID" in r.headers

    @pytest.mark.asyncio
    async def test_traceparent_in_response(self):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.get("/health/live")
        assert "traceparent" in r.headers


@pytest.mark.asyncio
async def test_mobile_disconnect_cancels_generation():
    import asyncio
    from fastapi import HTTPException
    from app.api.v1.xhs_note import _generate_for_request
    stopped=asyncio.Event()
    async def generate(*args):
        try:
            await asyncio.Future()
        finally:
            stopped.set()
    request=MagicMock()
    request.is_disconnected=AsyncMock(return_value=True)
    with patch("app.api.v1.xhs_note.generate_xhs_note",generate):
        with pytest.raises(HTTPException) as error:
            await _generate_for_request(request,"test",[])
    assert error.value.status_code==499
    assert stopped.is_set()
