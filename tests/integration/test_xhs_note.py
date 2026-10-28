"""小红书爆款笔记集成测试：多图 + 表单上传.

注意：此测试验证 API 接口的请求/响应契约。
- 使用 mock 替代真实 LLM 调用，避免依赖外部 API。
- 测试覆盖成功路径、错误路径与边界情况。
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
@patch("app.api.v1.xhs_note.generate_xhs_note_report")
async def test_xhs_note_report_success(mock_generate) -> None:
    """成功路径：返回 code=0 + report 字符串。"""
    mock_generate.return_value = (
        "原始创作意图: 地中海饮食\n生成笔记标题: 测试标题\n生成笔记正文: 测试正文",
        "",
    )

    tests_dir = Path(__file__).resolve().parent
    image_files = sorted(tests_dir.glob("*.jpg"))

    if not image_files:
        # 没有测试图片时创建一个临时文件
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", dir=str(tests_dir), delete=False)
        tmp.write(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        tmp.close()
        image_files = [Path(tmp.name)]

    files = [
        ("images", (p.name, open(str(p), "rb"), "image/jpeg")) for p in image_files[:2]
    ]

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://localhost:8000",
        ) as client:
            resp = await client.post(
                "/api/v1/xhs/notes/report",
                data={"idea_text": "我想分享最近开始用地中海饮食减脂"},
                files=files,
                headers={"X-API-Key": "test-key"},
            )
    finally:
        for _, (_, fobj, _) in files:
            fobj.close()

    assert resp.status_code == 200, resp.text
    body = resp.json()

    # 顶层统一响应契约
    assert body.get("code") == 0
    assert body.get("message") == "ok"
    assert "request_id" in body
    assert body.get("data") is not None

    data = body["data"]
    # 当前 API 返回的是 XhsNoteReportResponse(report=str)
    assert "report" in data
    assert isinstance(data["report"], str)
    assert len(data["report"]) > 0


@pytest.mark.asyncio
@patch("app.api.v1.xhs_note.generate_xhs_note_report")
async def test_xhs_note_report_failure(mock_generate) -> None:
    """失败路径：LLM 返回错误时 code=1。"""
    mock_generate.return_value = (None, "LLM 调用超时")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://localhost:8000",
    ) as client:
        resp = await client.post(
            "/api/v1/xhs/notes/report",
            data={"idea_text": "测试"},
            files=[("images", ("test.jpg", b"\xff\xd8\xff\xe0", "image/jpeg"))],
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 1
    assert "失败" in body["message"]


@pytest.mark.asyncio
async def test_xhs_note_report_missing_images() -> None:
    """缺少图片字段应返回 422。"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://localhost:8000",
    ) as client:
        resp = await client.post(
            "/api/v1/xhs/notes/report",
            data={"idea_text": "测试"},
        )
    assert resp.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
