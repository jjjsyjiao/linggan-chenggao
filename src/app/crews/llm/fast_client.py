"""Single-request async DashScope transport, independent of CrewAI.

The native HTTP body uses top-level ``enable_thinking`` (not SDK ``extra_body``).
Qwen-Plus and Qwen3-VL-Plus support JSON mode with thinking disabled:
https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output
https://www.alibabacloud.com/help/en/model-studio/deep-thinking
https://help.aliyun.com/en/model-studio/vision
Temperature 0 is valid for Qwen3-VL non-thinking mode (allowed range [0, 2)):
https://help.aliyun.com/en/model-studio/qwen-api-via-openai-chat-completions
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import time
from typing import Any, TypedDict

import httpx

from app.core.config import Settings, get_settings
from app.observability.logging import get_logger

logger = get_logger(__name__)

ENDPOINTS = {
    "cn": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    "intl": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
    "finance": "https://dashscope-finance.aliyuncs.com/compatible-mode/v1/chat/completions",
}


class CompletionResult(TypedDict):
    content: str
    usage: dict[str, Any]
    duration_seconds: float


class FastLLMError(RuntimeError):
    """Safe to expose: no provider body, request, headers, or image content."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _endpoint(settings: Settings) -> str:
    override = settings.llm_base_url
    if isinstance(override, str) and override.strip():
        endpoint = override.strip().rstrip("/")
        # Historical config accepts a complete endpoint. Also accept SDK-style
        # /compatible-mode/v1, without duplicating /chat/completions.
        if endpoint.endswith("/v1"):
            endpoint += "/chat/completions"
        return endpoint
    try:
        return ENDPOINTS[settings.llm_region]
    except KeyError:
        raise ValueError("不支持的模型服务地域") from None


def _supports_thinking_switch(model: str) -> bool:
    if model in {"qwen-plus", "qwen-plus-latest"}:
        return True
    if model == "qwen3-vl-plus" or model.startswith("qwen3-vl-plus-"):
        return True
    # Qwen-Plus snapshots before this date have no thinking switch.
    match = re.fullmatch(r"qwen-plus-(\d{4}-\d{2}-\d{2})", model)
    return bool(match and match[1] >= "2025-04-28")


def _image_fingerprints(messages: list[dict[str, Any]]) -> list[str]:
    """Hash decoded image bytes (or a remote reference), never log image data."""
    hashes: list[str] = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "image_url":
                continue
            image_url = part.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else None
            if not isinstance(url, str) or not url:
                raise FastLLMError("图片消息必须包含 image_url.url")
            if url.startswith("data:"):
                match = re.fullmatch(r"data:image/[\w.+-]+;base64,([A-Za-z0-9+/=]+)", url)
                if not match:
                    raise FastLLMError("图片必须使用规范的 base64 data URL")
                try:
                    image_bytes = base64.b64decode(match[1], validate=True)
                except (ValueError, binascii.Error):
                    raise FastLLMError("图片 base64 编码无效") from None
                if not image_bytes:
                    raise FastLLMError("图片内容不能为空")
                hashes.append(hashlib.sha256(image_bytes).hexdigest())
            else:
                # URLs may contain signed tokens. Only their hash can enter logs.
                hashes.append(hashlib.sha256(url.encode("utf-8")).hexdigest())
    return hashes


def _token_counts(usage: dict[str, Any]) -> dict[str, int]:
    return {
        key: value
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        if isinstance((value := usage.get(key)), int) and not isinstance(value, bool)
    }


class FastLLMClient:
    """Perform at most one HTTP POST per completion; never retry a model call.

    An injected AsyncClient remains owned by its caller. Without one, a client is
    opened and closed per request, including when cancelled. Cancellation and
    timeouts therefore stop awaiting the upstream request immediately.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = settings if settings is not None else get_settings()
        if not isinstance(settings.llm_api_key, str) or not settings.llm_api_key.strip():
            raise ValueError("阿里云 API Key 未配置，请设置 APP_LLM_API_KEY")
        self._api_key = settings.llm_api_key.strip()
        self._timeout = settings.llm_timeout
        self._endpoint = _endpoint(settings)
        self._client = client

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        max_tokens: int,
        response_json: bool = True,
    ) -> CompletionResult:
        if not isinstance(messages, list) or not messages or any(
            not isinstance(message, dict) for message in messages
        ):
            raise ValueError("messages 必须是非空消息列表")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model 不能为空")
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0:
            raise ValueError("max_tokens 必须是正整数")

        image_hashes = _image_fingerprints(messages)
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if response_json:
            payload["response_format"] = {"type": "json_object"}
        if _supports_thinking_switch(model):
            payload["enable_thinking"] = False
        if model == "qwen3-vl-plus" or model.startswith("qwen3-vl-plus-"):
            # Extract visual facts with minimum sampling randomness. This does
            # not prove factual accuracy, and top_p stays at the provider default.
            payload["temperature"] = 0
        headers = {"Authorization": f"Bearer {self._api_key}"}
        started = time.perf_counter()
        logger.info(
            "fast_llm_request",
            model=model,
            image_count=len(image_hashes),
            image_sha256s=image_hashes,
        )
        try:
            if self._client is not None:
                response = await self._client.post(
                    self._endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout,
                    follow_redirects=False,
                )
            else:
                # Explicit zero transport retries; redirects also must not turn
                # one invocation into a second HTTP request.
                transport = httpx.AsyncHTTPTransport(retries=0)
                async with httpx.AsyncClient(transport=transport) as client:
                    response = await client.post(
                        self._endpoint,
                        json=payload,
                        headers=headers,
                        timeout=self._timeout,
                        follow_redirects=False,
                    )
        except httpx.TimeoutException:
            raise FastLLMError("模型请求超时，未自动重试") from None
        except httpx.HTTPError:
            raise FastLLMError("模型服务连接失败，未自动重试") from None

        if not 200 <= response.status_code < 300:
            raise FastLLMError(
                f"模型服务返回 HTTP {response.status_code}，未自动重试",
                status_code=response.status_code,
            )
        try:
            data = response.json()
        except ValueError:
            raise FastLLMError("模型服务返回了无效的 JSON 响应") from None
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise FastLLMError("模型服务响应缺少 choices")
        choice = choices[0]
        if choice.get("finish_reason") == "length":
            raise FastLLMError("模型输出达到长度上限，请缩短内容后重试")
        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise FastLLMError("模型服务未返回正文，未自动重试")
        usage = data.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        duration_seconds = round(time.perf_counter() - started, 4)
        logger.info(
            "fast_llm_completed",
            model=model,
            duration_seconds=duration_seconds,
            **_token_counts(usage),
        )
        return {
            "content": content,
            "usage": usage,
            "duration_seconds": duration_seconds,
        }
