"""阿里云通义千问 LLM 实现，基于 CrewAI BaseLLM，适配本项目配置与日志规范。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from pathlib import Path
from typing import Any, ClassVar, Tuple
import re
import threading
import time
from weakref import WeakKeyDictionary

import httpx
import requests
from crewai import BaseLLM
from pydantic import Field

from app.core.config import get_settings
from app.observability.logging import get_logger

logger = get_logger(__name__)
_async_limiters: WeakKeyDictionary = WeakKeyDictionary()
_sync_limiters: dict[int, threading.BoundedSemaphore] = {}


def _llm_limiter() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if loop not in _async_limiters:
        _async_limiters[loop] = asyncio.Semaphore(get_settings().llm_max_concurrency)
    return _async_limiters[loop]


class AliyunLLM(BaseLLM):
    """阿里云通义千问 LLM，兼容 CrewAI BaseLLM 接口，支持多模态消息。"""

    ENDPOINTS: ClassVar[dict[str, str]] = {
        "cn": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "intl": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
        "finance": "https://dashscope-finance.aliyuncs.com/compatible-mode/v1/chat/completions",
    }
    endpoint: str = ""
    region: str = "cn"
    timeout: int = 120
    retry_count: int = 3
    image_model: str = "qwen3-vl-plus"
    image_paths: list[str] = Field(default_factory=list, exclude=True, repr=False)
    BOUND_IMAGE_PROMPT: ClassVar[str] = "以下是本任务对应的真实图片，请直接依据图片内容完成分析，不得编造看不到的细节。"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        region: str | None = None,
        temperature: float | None = None,
        timeout: int | None = None,
        retry_count: int | None = None,
        image_model: str | None = None,
        image_paths: list[str] | None = None,
    ) -> None:
        """
        初始化阿里云 LLM。未传参数时从 APP_* 配置读取。

        Args:
            model: 模型名称，如 qwen-plus、qwen-turbo
            api_key: API Key，不传则用 APP_LLM_API_KEY
            region: 地域 cn / intl / finance，不传则用 APP_LLM_REGION
            temperature: 采样温度
            timeout: 请求超时秒数
            retry_count: 请求失败时的重试次数，不传则用 APP_LLM_RETRY_COUNT
        """
        settings = get_settings()
        model = model or settings.llm_model
        super().__init__(model=model, temperature=temperature)

        self.api_key = api_key or settings.llm_api_key
        if not self.api_key:
            raise ValueError(
                "阿里云 API Key 未配置。请设置环境变量 APP_LLM_API_KEY 或在构造时传入 api_key"
            )

        region = region or settings.llm_region
        if region not in self.ENDPOINTS:
            raise ValueError(
                f"不支持的地域: {region}，支持: {list(self.ENDPOINTS.keys())}"
            )
        endpoint_override = settings.llm_base_url
        self.endpoint = endpoint_override if isinstance(endpoint_override, str) and endpoint_override else self.ENDPOINTS[region]
        self.region = region
        self.timeout = timeout if timeout is not None else settings.llm_timeout
        self.retry_count = retry_count if retry_count is not None else settings.llm_retry_count
        # 专门的多模态模型；优先使用显式入参，其次尝试从配置读取，最后使用默认值。
        self.image_model = (
            image_model
            or getattr(settings, "llm_image_model", None)
            or "qwen3-vl-plus"
        )
        self.image_paths = list(image_paths or [])

    def _attach_bound_images(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """逐 Agent 绑定真实图像，第一轮请求就携带图片，不能由模型自行决定是否看图。"""
        if not self.image_paths:
            return messages
        content = [{"type": "text", "text": self.BOUND_IMAGE_PROMPT}]
        hashes = []
        byte_sizes = []
        for value in self.image_paths:
            path = Path(value)
            if not path.is_file():
                raise ValueError("任务图片不存在，禁止在缺少图片的情况下生成分析")
            mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            binary = path.read_bytes()
            hashes.append(hashlib.sha256(binary).hexdigest())
            byte_sizes.append(len(binary))
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(binary).decode('ascii')}"}})
        logger.info("llm_images_attached", image_count=len(self.image_paths), model=self.image_model, image_sha256s=hashes, image_sizes_bytes=byte_sizes)
        previous = [message for message in messages if not (isinstance(message.get("content"), list) and message["content"] and message["content"][0].get("text") == self.BOUND_IMAGE_PROMPT)]
        return [*previous, {"role": "user", "content": content}]

    def _normalize_multimodal_tool_result(
        self, messages: list[dict[str, Any]]
    ) -> Tuple[list[dict[str, Any]], bool]:
        """
        将 CrewAI 对 AddImageTool/AddImageToolLocal 的字符串结果还原为多模态 user 消息。

        参考原项目实现：
        - 当内容中包含 AddImageToolLocal 输出的 data URL 时，转为通义千问兼容的
          `[{type: text}, {type: image_url, image_url: {url: ...}}]` 结构；
        - 当内容中包含远程 http 图片 Observation 时，转为 {type: text} + {type: image} 结构。

        Returns:
            (normalized_messages, used_multimodal_model)
        """
        out: list[dict[str, Any]] = []
        flag = False
        for msg in messages:
            content = msg.get("content")
            # 仅处理来自工具调用后的 assistant 文本消息
            if msg.get("role") != "assistant" or content is None or not isinstance(content, str):
                out.append(msg)
                continue

            s = content
            # 情形 1：AddImageToolLocal 返回 base64 data URL
            if "add_image_to_content_local" in s and ("data:image/" in s and ";base64," in s):
                logger.info("normalized_multimodal_tool_result base64_from_tool")
                idx = s.find("data:image/")
                data_url = re.match(r"data:image/[^;\s]+;base64,[A-Za-z0-9+/=]+", s[idx:]).group(0)
                logger.info(
                    "normalized_multimodal_tool_result base64_len=%s",
                    len(data_url),
                )
                text = s[:idx] + "图片内容已加载"
                user_msg = {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
                out.append(user_msg)
                flag = True
                continue

            # 情形 2：AddImageToolLocal 观测到远程 http 图片链接
            if "add_image_to_content_local" in s and "Observation: http" in s:
                idx = s.find("http", s.find("Observation: http"))
                data_url = s[idx:].split()[0]
                text = s[:idx] + "图片内容已加载"
                user_msg = {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
                logger.info("normalized_multimodal_tool_result http_image_from_tool")
                out.append(user_msg)
                flag = True
                continue

            out.append(msg)

        logger.info("normalized_multimodal_tool_result flag=%s", flag)
        return out, flag

    def call(self, *args, **kwargs):
        limit = get_settings().llm_max_concurrency
        limiter = _sync_limiters.setdefault(limit, threading.BoundedSemaphore(limit))
        with limiter:
            return self._call_sync(*args, **kwargs)

    def _call_sync(
        self,
        messages: str | list[dict[str, Any]],
        tools: list[dict] | None = None,
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        max_iterations: int = 10,
        _retry_on_empty: bool = True,
        **kwargs: Any,
    ) -> str | Any:
        """调用阿里云 Chat Completions API，支持 Function Calling 与多模态消息。"""
        llm_started = time.perf_counter()
        logger.debug("llm_call", model=self.model)
        if max_iterations <= 0:
            raise RuntimeError("Function calling 达到最大迭代次数，可能存在无限循环")

        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        messages = self._attach_bound_images(messages)

        # 将 AddImageToolLocal 的字符串结果还原为多模态消息，并根据是否包含图片决定模型
        messages, used_multimodal = self._normalize_multimodal_tool_result(messages)
        used_multimodal = used_multimodal or any(isinstance(msg.get("content"), list) and any(item.get("type") in {"image", "image_url"} for item in msg["content"]) for msg in messages)
        self._validate_messages(messages)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        # 若本轮对话中存在多模态消息，则自动切换为多模态模型
        if used_multimodal:
            payload["model"] = self.image_model

        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.stop and self.supports_stop_words():
            stop_value = self._prepare_stop_words(self.stop)
            if stop_value:
                payload["stop"] = stop_value
        if tools and self.supports_function_calling():
            payload["tools"] = tools

        if callbacks:
            for cb in callbacks:
                if hasattr(cb, "on_llm_start"):
                    try:
                        cb.on_llm_start(messages)
                    except Exception:
                        pass

        logger.debug(
            "llm_request",
            endpoint=self.endpoint,
            model=payload.get("model"),
            region=self.region,
            num_messages=len(messages),
        )

        # 重试逻辑
        last_exception = None
        for attempt in range(self.retry_count + 1):  # 总共尝试 retry_count + 1 次
            if attempt:
                time.sleep(min(2 ** (attempt - 1), 8))
            try:
                response = requests.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.timeout,
                )
                
                # 检查 HTTP 状态码，决定是否需要重试
                status_code = response.status_code
                if status_code >= 500:
                    # 5xx 服务器错误，可以重试
                    if attempt < self.retry_count:
                        logger.warning(
                            "llm_server_error_retry",
                            status_code=status_code,
                            attempt=attempt + 1,
                            max_attempts=self.retry_count + 1,
                        )
                        last_exception = RuntimeError(f"LLM 服务器错误 {status_code}: {response.text[:200]}")
                        continue
                    else:
                        response.raise_for_status()
                elif status_code == 429:
                    # 429 限流错误，可以重试
                    if attempt < self.retry_count:
                        logger.warning(
                            "llm_rate_limit_retry",
                            attempt=attempt + 1,
                            max_attempts=self.retry_count + 1,
                        )
                        last_exception = RuntimeError(f"LLM 请求限流: {response.text[:200]}")
                        continue
                    else:
                        response.raise_for_status()
                elif status_code >= 400:
                    # 其他 4xx 客户端错误，不重试
                    response.raise_for_status()
                
                # 请求成功
                result = response.json()
                if attempt > 0:
                    logger.info(
                        "llm_request_success_after_retry",
                        attempt=attempt + 1,
                        total_attempts=self.retry_count + 1,
                    )
                logger.debug("llm_response_received", model=self.model)
                break
                
            except requests.Timeout:
                last_exception = TimeoutError(f"LLM 请求超时（{self.timeout} 秒）")
                if attempt < self.retry_count:
                    logger.warning(
                        "llm_timeout_retry",
                        timeout=self.timeout,
                        attempt=attempt + 1,
                        max_attempts=self.retry_count + 1,
                    )
                    continue
                else:
                    logger.error("llm_timeout_final", timeout=self.timeout, total_attempts=self.retry_count + 1)
                    raise last_exception
            except requests.HTTPError as exc:
                if exc.response is not None and 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
                    raise RuntimeError("模型请求失败，请检查 API Key 和模型权限") from exc
                raise RuntimeError("模型上游服务暂时不可用") from exc
            except requests.RequestException as e:
                last_exception = RuntimeError(f"LLM 请求失败: {e}")
                if attempt < self.retry_count:
                    logger.warning(
                        "llm_request_error_retry",
                        error=str(e),
                        attempt=attempt + 1,
                        max_attempts=self.retry_count + 1,
                    )
                    continue
                else:
                    logger.exception("llm_request_failed", error=str(e), total_attempts=self.retry_count + 1)
                    raise last_exception
        else:
            # 所有重试都失败了
            if last_exception:
                raise last_exception
            raise RuntimeError("LLM 请求失败：未知错误")

        if callbacks:
            for cb in callbacks:
                if hasattr(cb, "on_llm_end"):
                    try:
                        cb.on_llm_end(result)
                    except Exception:
                        pass

        if "choices" not in result or not result["choices"]:
            raise ValueError("响应中未找到 choices 字段")

        message = result["choices"][0].get("message", {})
        # 模型按 function call 返回时：content 常为空字符串，真实内容在 tool_calls 里，走 _handle_function_calls 处理
        if "tool_calls" in message:
            if available_functions:
                return self._handle_function_calls(
                    message["tool_calls"],
                    messages,
                    tools,
                    available_functions,
                    max_iterations - 1,
                )
            raise ValueError(
                "响应包含 tool_calls 但未提供 available_functions，无法执行工具调用"
            )

        content = message.get("content")
        if content is None:
            raise ValueError("响应中未找到 content 字段")

        # 仅当无 tool_calls 且 content 为空时才重试/报错（有 tool_calls 时已在上方处理）
        if isinstance(content, str) and not content.strip():
            if _retry_on_empty:
                # 限制空内容重试次数，避免无限循环
                max_empty_retries = 2
                retry_count = kwargs.get("_empty_retry_count", 0)
                if retry_count >= max_empty_retries:
                    raise ValueError(
                        f"LLM 连续 {max_empty_retries + 1} 次返回空内容，可能是模型限流或异常，请稍后重试或检查 API 配额"
                    )
                logger.warning(
                    "llm_empty_content_retry",
                    model=self.model,
                    retry_count=retry_count + 1,
                    max_retries=max_empty_retries,
                )
                return self._call_sync(
                    messages,
                    tools=tools,
                    callbacks=callbacks,
                    available_functions=available_functions,
                    max_iterations=max_iterations,
                    _retry_on_empty=False,
                    _empty_retry_count=retry_count + 1,
                    **kwargs,
                )
            raise ValueError(
                "LLM 返回空内容，可能是模型限流或偶发异常，请稍后重试或检查 API 配额"
            )
        
        logger.info(
            "llm_response",
            endpoint=self.endpoint,
            model=payload["model"],
            duration_seconds=round(time.perf_counter() - llm_started, 3),
            usage=result.get("usage", {}),
        )
        return content

    def _handle_function_calls(
        self,
        tool_calls: list[dict],
        messages: list[dict[str, Any]],
        tools: list[dict] | None,
        available_functions: dict[str, Any],
        max_iterations: int,
    ) -> str | Any:
        """处理 Function Calling 递归调用。"""
        if max_iterations <= 0:
            raise RuntimeError("Function calling 达到最大迭代次数，可能存在无限循环")

        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls,
        })

        for tool_call in tool_calls:
            fn_info = tool_call.get("function", {})
            fn_name = fn_info.get("name")
            tool_call_id = tool_call.get("id")
            if not tool_call_id:
                raise ValueError(f"tool_call 缺少 id: {tool_call}")

            if fn_name in available_functions:
                try:
                    raw = fn_info.get("arguments", "{}")
                    args = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
                except json.JSONDecodeError as e:
                    raise ValueError(f"无法解析函数参数: {e}") from e
                try:
                    function_result = available_functions[fn_name](**args)
                except Exception as e:
                    function_result = f"函数执行错误: {str(e)}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": str(function_result),
                })
            else:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": f"函数 {fn_name} 不可用",
                })

        return self.call(messages, tools, None, available_functions, max_iterations - 1)

    async def acall(
        self,
        messages: str | list[dict[str, Any]],
        tools: list[dict] | None = None,
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        max_iterations: int = 10,
        _retry_on_empty: bool = True,
        **kwargs: Any,
    ) -> str | Any:
        """原生异步 HTTP：超时/取消会关闭请求，避免后台线程继续计费或占用并发槽。"""
        if max_iterations <= 0:
            raise RuntimeError("Function calling 达到最大迭代次数")
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        messages = self._attach_bound_images(messages)
        messages, multimodal = self._normalize_multimodal_tool_result(messages)
        multimodal = multimodal or any(
            isinstance(msg.get("content"), list) and any(
                item.get("type") in {"image", "image_url"} for item in msg["content"]
            ) for msg in messages
        )
        self._validate_messages(messages)
        payload = {"model": self.image_model if multimodal else self.model, "messages": messages}
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.stop:
            payload["stop"] = self._prepare_stop_words(self.stop)
        if tools and self.supports_function_calling():
            payload["tools"] = tools
        for callback in callbacks or []:
            if hasattr(callback, "on_llm_start"):
                callback.on_llm_start(messages)
        async with _llm_limiter():
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                for attempt in range(self.retry_count + 1):
                    try:
                        response = await client.post(
                            self.endpoint,
                            headers={"Authorization": f"Bearer {self.api_key}"},
                            json=payload,
                        )
                        response.raise_for_status()
                        result = response.json()
                        choices = result.get("choices") or []
                        if not choices:
                            raise ValueError("响应中未找到 choices 字段")
                        message = choices[0].get("message", {})
                        if message.get("tool_calls"):
                            raise ValueError("当前使用 ReAct 工具模式，上游却返回 tool_calls，请检查模型配置")
                        content = message.get("content")
                        if not isinstance(content, str) or not content.strip():
                            raise ValueError("模型未返回有效正文")
                        for callback in callbacks or []:
                            if hasattr(callback, "on_llm_end"):
                                callback.on_llm_end(result)
                        return content
                    except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                        retryable = not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code == 429 or exc.response.status_code >= 500
                        if not retryable or attempt >= self.retry_count:
                            if isinstance(exc, httpx.TimeoutException):
                                raise TimeoutError("模型请求超时") from exc
                            raise RuntimeError("模型请求失败，请检查 API Key、模型权限及网络") from exc
                        await asyncio.sleep(min(2 ** attempt, 8))
        raise RuntimeError("模型请求失败")

    def supports_function_calling(self) -> bool:
        # 返回 False，让 CrewAI 走 ReAct 文本解析路径（Action: / Action Input:），
        # 由 CrewAgentExecutor._invoke_loop_react() 解析输出并执行工具。
        # 阿里云模型常把“要调用工具”写在 content 里而非返回 tool_calls，故不用 API 的 function calling。
        return False

    def supports_stop_words(self) -> bool:
        return True

    def _validate_messages(self, messages: list[dict[str, Any]]) -> None:
        """校验消息格式（含多模态 content）。"""
        valid_roles = {"system", "user", "assistant", "tool"}
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise ValueError(f"消息 {i} 必须是字典: {msg}")
            if "role" not in msg or msg["role"] not in valid_roles:
                raise ValueError(f"消息 {i} 缺少或无效的 role: {msg}")
            if msg["role"] == "tool":
                if "tool_call_id" not in msg or "content" not in msg:
                    raise ValueError(f"tool 消息 {i} 缺少 tool_call_id/content: {msg}")
            elif "content" not in msg and msg.get("tool_calls") is None:
                raise ValueError(f"消息 {i} 缺少 content 且无 tool_calls: {msg}")
            else:
                content = msg.get("content")
                if content is not None and not isinstance(content, (str, list)):
                    raise ValueError(f"消息 {i} 的 content 须为 str 或 list: {type(content)}")
                if isinstance(content, list):
                    for j, item in enumerate(content):
                        if not isinstance(item, dict) or "type" not in item:
                            raise ValueError(f"消息 {i} content[{j}] 须为含 type 的 dict: {item}")

    def _prepare_stop_words(
        self, stop: str | list[str | int]
    ) -> str | list[str | int] | None:
        """准备 stop 参数。"""
        if not stop:
            return None
        if isinstance(stop, str):
            return stop
        if isinstance(stop, list) and stop:
            return stop
        return None

    def get_context_window_size(self) -> int:
        """根据模型名返回上下文窗口大小（Token 数）。"""
        m = self.model.lower()
        if "long" in m:
            return 200_000
        if "max" in m or "plus" in m or "turbo" in m or "flash" in m:
            return 8192
        return 8192
