"""客户端协议通过真实 FastAPI/Service/图片处理链路测试，模型一律离线替身。"""
import asyncio
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from PIL import Image

from app.core.config import Settings
from app.main import create_application
from app.schemas.xhs_note import XhsGeneratedNote


@pytest.fixture
def setup_app(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, llm_api_key="", data_output_dir=str(tmp_path))
    monkeypatch.setattr("app.services.xhs_note_service.get_settings", lambda: settings)
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr("app.core.security.get_settings", lambda: settings)
    app = create_application()
    return app, settings


def picture():
    output=BytesIO()
    Image.new("RGB",(80,60),"red").save(output,format="JPEG")
    return output.getvalue()


async def test_demo_real_upload_and_schema(setup_app):
    app,settings=setup_app
    settings.xhs_demo_mode=True
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
        response=await client.post("/api/v1/xhs/notes/generate",data={"idea_text":"记录周末"},files=[("images",("same.jpg",picture(),"image/jpeg")),("images",("same.jpg",picture(),"image/jpeg"))])
    assert response.status_code==200,response.text
    body=response.json()
    assert body["code"]==0
    assert body["data"]["is_demo"] is True
    assert body["data"]["image_order"]==["img_0","img_1"]
    assert body["data"]["title"] and body["data"]["content"]
    assert body["request_id"]==response.headers["X-Request-ID"]
    assert "local_path" not in response.text
    assert not list(Path(settings.data_output_dir).glob("xhs_note/run_*"))


@pytest.mark.parametrize("payload,mime,status",[(b"video","video/mp4",415),(b"bad","image/jpeg",415),(None,"image/jpeg",503)])
async def test_validation_and_missing_configuration(setup_app,payload,mime,status):
    app,settings=setup_app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
        response=await client.post("/api/v1/xhs/notes/generate",data={"idea_text":"test"},files=[("images",("test.jpg",picture() if payload is None else payload,mime))])
    assert response.status_code==status,response.text
    assert response.json()["code"]==status


async def test_http_error_and_retry_header(setup_app):
    app,settings=setup_app
    from app.services.xhs_note_service import NoteGenerationError
    with patch("app.api.v1.xhs_note.generate_xhs_note", AsyncMock(side_effect=NoteGenerationError("繁忙",429))):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
            response=await client.post("/api/v1/xhs/notes/generate",data={"idea_text":"test"},files=[("images",("test.jpg",picture(),"image/jpeg"))])
    assert response.status_code==429
    assert response.headers["Retry-After"]=="10"


async def test_body_limit_before_multipart_decode(setup_app):
    _,settings=setup_app
    settings.xhs_max_total_bytes=100
    app=create_application()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
        response=await client.post("/api/v1/xhs/notes/generate",content=b"x"*(1024*1024+101),headers={"content-type":"multipart/form-data; boundary=test"})
    assert response.status_code==413,response.text


async def test_chunked_body_limit(setup_app):
    _,settings=setup_app
    settings.xhs_max_total_bytes=100
    app=create_application()
    async def chunks():
        yield b'--test\r\nContent-Disposition: form-data; name="idea_text"\r\n\r\nhello\r\n--test\r\nContent-Disposition: form-data; name="images"; filename="a.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'
        for _ in range(18):
            yield b"x"*(64*1024)
        yield b"\r\n--test--\r\n"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
        response=await client.post("/api/v1/xhs/notes/generate",content=chunks(),headers={"content-type":"multipart/form-data; boundary=test"})
    assert response.status_code==413,response.text


async def test_busy_rejected_before_parsing_upload(setup_app):
    app,settings=setup_app
    entered=asyncio.Event()
    release=asyncio.Event()
    count=0
    async def generate(*args):
        nonlocal count
        count+=1
        if count==2:
            entered.set()
        await release.wait()
        return XhsGeneratedNote(title="title",content="content",image_order=["img_0"])
    with patch("app.api.v1.xhs_note.generate_xhs_note",generate):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
            async def post():
                return await client.post("/api/v1/xhs/notes/generate",data={"idea_text":"test"},files=[("images",("test.jpg",picture(),"image/jpeg"))])
            tasks=[asyncio.create_task(post()) for _ in range(2)]
            await asyncio.wait_for(entered.wait(),2)
            rejected=await client.post("/api/v1/xhs/notes/generate",content=b"invalid multipart",headers={"content-type":"multipart/form-data; boundary=test"})
            assert rejected.status_code==429
            assert rejected.headers["Retry-After"]=="10"
            assert (await client.get("/health/live")).status_code==200
            release.set()
            assert all(response.status_code==200 for response in await asyncio.gather(*tasks))
