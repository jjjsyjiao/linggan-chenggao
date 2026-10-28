"""Offline HTTP-contract tests: no model calls, including failure fallbacks."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from unittest.mock import MagicMock

import httpx
import pytest

from app.core.config import Settings
from app.crews.llm.fast_client import FastLLMClient, FastLLMError


def _settings(**kwargs) -> Settings:
    return Settings(
        _env_file=None,
        llm_api_key="fake-secret-key",
        **kwargs,
    )


def _response(content='{"title":"图片中的花"}', **kwargs) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            **kwargs,
        },
    )


async def test_multimodal_bytes_and_all_messages_are_passed_through():
    image_bytes = b"real-image-bytes-without-tool-selection"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    messages = [
        {"role": "system", "content": "Only describe visible facts. Return JSON."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "请先看这两张图片"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
            ],
        },
    ]
    before = json.loads(json.dumps(messages))
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "POST"
        assert request.headers["Authorization"] == "Bearer fake-secret-key"
        assert json.loads(request.content) == {
            "model": "qwen3-vl-plus",
            "messages": messages,
            "max_tokens": 900,
            "response_format": {"type": "json_object"},
            "enable_thinking": False,
            "temperature": 0,
        }
        return _response()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await FastLLMClient(_settings(), client=http).complete(
            messages, model="qwen3-vl-plus", max_tokens=900
        )
        assert not http.is_closed
    assert len(requests) == 1
    assert messages == before
    assert result["content"] == '{"title":"图片中的花"}'
    assert result["usage"]["total_tokens"] == 120
    assert result["duration_seconds"] >= 0


@pytest.mark.parametrize(
    ("model", "has_switch"),
    [
        ("qwen-plus", True),
        ("qwen-plus-latest", True),
        ("qwen-plus-2025-04-28", True),
        ("qwen-plus-2025-07-28", True),
        ("qwen3-vl-plus", True),
        ("qwen3-vl-plus-2025-09-23", True),
        ("qwen3-vl-plus-latest", True),
        ("qwen-plus-2024-12-20", False),
        ("qwen-vl-plus", False),
        ("my-custom-model", False),
    ],
)
async def test_only_documented_thinking_switch_is_sent(model, has_switch):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return _response("正文")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await FastLLMClient(_settings(), client=http).complete(
            [{"role": "user", "content": "正文"}],
            model=model,
            max_tokens=500,
            response_json=False,
        )
    payload = requests[0]
    assert ("enable_thinking" in payload) is has_switch
    if has_switch:
        assert payload["enable_thinking"] is False
    assert "response_format" not in payload
    assert "extra_body" not in payload
    if model == "qwen3-vl-plus" or model.startswith("qwen3-vl-plus-"):
        assert payload["temperature"] == 0
    else:
        assert "temperature" not in payload
    assert "top_p" not in payload
    assert "tools" not in payload
    assert "stream_options" not in payload


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        (
            _settings(llm_region="cn"),
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        ),
        (
            _settings(llm_region="intl"),
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
        ),
        (
            _settings(llm_region="finance"),
            "https://dashscope-finance.aliyuncs.com/compatible-mode/v1/chat/completions",
        ),
        (
            _settings(llm_base_url="https://proxy.test/compatible-mode/v1"),
            "https://proxy.test/compatible-mode/v1/chat/completions",
        ),
        (
            _settings(llm_base_url="https://proxy.test/v1/"),
            "https://proxy.test/v1/chat/completions",
        ),
        (
            _settings(llm_base_url="https://proxy.test/v1/chat/completions"),
            "https://proxy.test/v1/chat/completions",
        ),
        (
            _settings(llm_base_url="https://proxy.test/custom/endpoint"),
            "https://proxy.test/custom/endpoint",
        ),
    ],
)
async def test_region_and_base_url_semantics(settings, expected):
    requests = []

    def handler(request):
        requests.append(request)
        assert str(request.url) == expected
        return _response()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await FastLLMClient(settings, client=http).complete(
            [{"role": "user", "content": "JSON"}], model="qwen-plus", max_tokens=100
        )
    assert len(requests) == 1


@pytest.mark.parametrize("status", [301, 307, 400, 401, 429, 500, 503])
async def test_http_errors_and_redirects_never_retry_or_leak_body(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status,
            text="sensitive-provider-body fake-secret-key data:image/jpeg;base64,AAAA",
            headers={"Location": "https://other.test/redirect"},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as http:
        with pytest.raises(FastLLMError) as caught:
            await FastLLMClient(_settings(llm_retry_count=10), client=http).complete(
                [{"role": "user", "content": "JSON"}], model="qwen-plus", max_tokens=100
            )
    assert len(requests) == 1
    assert caught.value.status_code == status
    assert "fake-secret-key" not in str(caught.value)
    assert "sensitive-provider-body" not in str(caught.value)
    assert "data:image" not in str(caught.value)


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError, httpx.ReadError])
async def test_transport_failure_never_retries_or_leaks_exception(error):
    requests = []

    def handler(request):
        requests.append(request)
        raise error("fake-secret-key sensitive-body", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(FastLLMError) as caught:
            await FastLLMClient(_settings(), client=http).complete(
                [{"role": "user", "content": "JSON"}], model="qwen-plus", max_tokens=100
            )
    assert len(requests) == 1
    assert "fake-secret-key" not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json fake-secret-key"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [None]}),
        _response(""),
        _response("   "),
        _response(None),
        _response(choices=[{"finish_reason": "length", "message": {"content": '{"truncated'}}]),
    ],
)
async def test_invalid_or_truncated_provider_response_is_not_repaired_with_paid_call(response):
    requests = []

    def handler(request):
        requests.append(request)
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(FastLLMError):
            await FastLLMClient(_settings(), client=http).complete(
                [{"role": "user", "content": "JSON"}], model="qwen-plus", max_tokens=100
            )
    assert len(requests) == 1


async def test_cancellation_propagates_to_transport_without_second_call():
    entered = asyncio.Event()
    cancelled = asyncio.Event()
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        task = asyncio.create_task(
            FastLLMClient(_settings(), client=http).complete(
                [{"role": "user", "content": "JSON"}], model="qwen-plus", max_tokens=100
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()
        assert not http.is_closed
    assert calls == 1


async def test_logs_include_only_model_duration_token_counts_and_image_hashes(monkeypatch):
    logger = MagicMock()
    monkeypatch.setattr("app.crews.llm.fast_client.logger", logger)
    image_bytes = b"sensitive-image-content"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    remote_url = "https://private.test/image.jpg?token=secret"
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "sensitive-user-prompt JSON"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
            {"type": "image_url", "image_url": {"url": remote_url}},
        ],
    }]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: _response(
            'sensitive-model-output',
            usage={"total_tokens": 123, "extra": "sensitive-usage", "prompt_tokens": "bad"},
        ))
    ) as http:
        await FastLLMClient(_settings(), client=http).complete(
            messages, model="qwen3-vl-plus", max_tokens=100
        )
    assert logger.info.call_count == 2
    request_log = logger.info.call_args_list[0].kwargs
    assert request_log == {
        "model": "qwen3-vl-plus",
        "image_count": 2,
        "image_sha256s": [
            hashlib.sha256(image_bytes).hexdigest(),
            hashlib.sha256(remote_url.encode()).hexdigest(),
        ],
    }
    completion_log = logger.info.call_args_list[1].kwargs
    assert set(completion_log) == {"model", "duration_seconds", "total_tokens"}
    assert completion_log["total_tokens"] == 123
    all_logs = str(logger.mock_calls)
    for secret in (
        encoded,
        remote_url,
        "fake-secret-key",
        "sensitive-user-prompt",
        "sensitive-model-output",
        "sensitive-usage",
    ):
        assert secret not in all_logs


@pytest.mark.parametrize(
    "url",
    [
        "data:image/png;base64,not-a-base64!",
        "data:text/plain;base64,YQ==",
        "data:image/png;base64,",
        "data:image/png;base64,Y===",
    ],
)
async def test_invalid_image_encoding_fails_before_any_http_request(url):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return _response()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(FastLLMError):
            await FastLLMClient(_settings(), client=http).complete(
                [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}}]}],
                model="qwen3-vl-plus",
                max_tokens=100,
            )
    assert calls == 0


@pytest.mark.parametrize("max_tokens", [0, -1, True, 1.5])
async def test_invalid_token_budget_fails_before_request(max_tokens):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: _response())) as http:
        with pytest.raises(ValueError, match="max_tokens"):
            await FastLLMClient(_settings(), client=http).complete(
                [{"role": "user", "content": "JSON"}],
                model="qwen-plus",
                max_tokens=max_tokens,
            )


async def test_missing_usage_is_allowed():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: _response(usage=None))
    ) as http:
        result = await FastLLMClient(_settings(), client=http).complete(
            [{"role": "user", "content": "JSON"}], model="qwen-plus", max_tokens=100
        )
    assert result["usage"] == {}


def test_missing_key_fails_without_network():
    settings = _settings()
    settings.llm_api_key = ""
    with pytest.raises(ValueError, match="APP_LLM_API_KEY"):
        FastLLMClient(settings)
