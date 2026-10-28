"""在 multipart 解析前限制请求体，包含没有 Content-Length 的分块上传。"""
from uuid import uuid4
import asyncio

from fastapi import HTTPException
from starlette.responses import JSONResponse


class UploadBodyLimitMiddleware:
    def __init__(self, app, max_bytes: int, max_concurrent: int = 2):
        self.app = app
        self.max_bytes = max_bytes
        self.slots = asyncio.Semaphore(max_concurrent)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or not scope.get("path", "").startswith("/api/v1/xhs/"):
            await self.app(scope, receive, send)
            return
        # 在multipart解析与磁盘spool之前限制上传/生成总并发，避免大量拒绝请求先占满磁盘。
        if self.slots.locked():
            request_id = scope.get("state", {}).get("request_id") or str(uuid4())
            response = JSONResponse(
                {"code": 429, "message": "生成任务较多，请稍后重试", "request_id": request_id},
                status_code=429,
                headers={"X-Request-ID": request_id, "Retry-After": "10"},
            )
            await response(scope, receive, send)
            return
        await self.slots.acquire()
        try:
            await self._bounded_request(scope, receive, send)
        finally:
            self.slots.release()

    async def _bounded_request(self, scope, receive, send):
        headers = dict(scope.get("headers", []))
        length = headers.get(b"content-length", b"")
        if length.isdigit() and int(length) > self.max_bytes:
            request_id = scope.get("state", {}).get("request_id") or str(uuid4())
            response = JSONResponse(
                {"code": 413, "message": "上传请求过大，请减少或压缩图片", "request_id": request_id},
                status_code=413,
                headers={"X-Request-ID": request_id},
            )
            await response(scope, receive, send)
            return
        received = 0
        too_large = False
        error_sent = False

        async def bounded_receive():
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    too_large = True
                    raise HTTPException(413, "上传请求过大，请减少或压缩图片")
            return message

        async def bounded_send(message):
            nonlocal error_sent
            # Starlette 某些版本将 multipart receive 异常统一转换为 400；保留真实 413。
            if too_large:
                if not error_sent:
                    error_sent = True
                    request_id = scope.get("state", {}).get("request_id") or str(uuid4())
                    response = JSONResponse(
                        {"code": 413, "message": "上传请求过大，请减少或压缩图片", "request_id": request_id},
                        status_code=413,
                        headers={"X-Request-ID": request_id},
                    )
                    await response(scope, receive, send)
                return
            await send(message)

        await self.app(scope, bounded_receive, bounded_send)
