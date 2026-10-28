"""健康检查与 API 集成测试。

默认用 ASGITransport 进程内调用 app，不经过网络，请求不会打到已启动的 Web 服务，
所以「运行 Web 服务的那个终端」不会打 trace 日志；日志会打在跑 pytest 的终端。

若要让 Web 服务控制台打 trace 日志（和 curl 时一样）：
  终端 1:  PYTHONPATH=src python -m app
  终端 2:  LIVE_URL=http://127.0.0.1:8000 pytest tests/integration/test_api_health.py -v

在项目根目录运行（进程内，Web 服务终端无日志）:
  pytest tests/integration/test_api_health.py -v
  或  PYTHONPATH=src python tests/integration/test_api_health.py
"""

import os
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

# 未设置 LIVE_URL 时用 ASGITransport 进程内调用；设置后对真实服务发 HTTP
LIVE_URL = os.environ.get("LIVE_URL", "").strip()


def _make_client():
    if LIVE_URL:
        return AsyncClient(base_url=LIVE_URL)
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://localhost:8000",
    )


@pytest.mark.asyncio
async def test_health_live() -> None:
    async with _make_client() as client:
        r = await client.get("/health/live")
    print(r.json())
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_ready() -> None:
    async with _make_client() as client:
        r = await client.get("/health/ready")
    print(r.json())
    assert r.status_code == 200
    data = r.json()
    assert data.get("code") == 0
    assert "request_id" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
