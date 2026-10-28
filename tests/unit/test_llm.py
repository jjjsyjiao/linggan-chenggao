"""AliyunLLM 的单元测试，使用 mock 模拟 HTTP 请求。"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from app.crews.llm.aliyun_llm import AliyunLLM


def _make_llm(**kwargs) -> AliyunLLM:
    """创建一个测试用 AliyunLLM 实例。"""
    defaults = dict(
        model="qwen-test",
        api_key="test-key-123",
        region="cn",
        timeout=30,
        retry_count=1,
    )
    defaults.update(kwargs)
    with patch("app.crews.llm.aliyun_llm.get_settings") as mock_settings:
        s = MagicMock()
        s.llm_api_key = defaults.get("api_key", "test-key")
        s.llm_model = "qwen-plus"
        s.llm_region = "cn"
        s.llm_timeout = 600
        s.llm_retry_count = 3
        s.llm_image_model = "qwen3-vl-plus"
        mock_settings.return_value = s
        return AliyunLLM(**defaults)


class TestAliyunLLMInit:
    def test_basic_init(self):
        llm = _make_llm()
        assert llm.model == "qwen-test"
        assert llm.api_key == "test-key-123"
        assert llm.region == "cn"

    def test_endpoint_cn(self):
        llm = _make_llm(region="cn")
        assert "dashscope.aliyuncs.com" in llm.endpoint

    def test_endpoint_intl(self):
        llm = _make_llm(region="intl")
        assert "intl" in llm.endpoint

    def test_endpoint_finance(self):
        llm = _make_llm(region="finance")
        assert "finance" in llm.endpoint

    def test_invalid_region(self):
        with pytest.raises(ValueError, match="不支持的地域"):
            _make_llm(region="invalid")

    def test_no_api_key(self):
        with patch("app.crews.llm.aliyun_llm.get_settings") as mock_settings:
            s = MagicMock()
            s.llm_api_key = ""
            s.llm_model = "qwen-plus"
            s.llm_region = "cn"
            s.llm_timeout = 600
            s.llm_retry_count = 3
            s.llm_image_model = "qwen3-vl-plus"
            mock_settings.return_value = s
            with pytest.raises(ValueError, match="API Key"):
                AliyunLLM(api_key="")

    def test_image_model(self):
        llm = _make_llm(image_model="my-vl-model")
        assert llm.image_model == "my-vl-model"


class TestAliyunLLMCall:
    def _mock_response(self, content: str = "回答内容", status_code: int = 200, tool_calls=None):
        resp = MagicMock()
        resp.status_code = status_code
        msg = {"content": content}
        if tool_calls is not None:
            msg["tool_calls"] = tool_calls
        resp.json.return_value = {
            "choices": [{"message": msg}],
            "usage": {"total_tokens": 100},
        }
        resp.raise_for_status = MagicMock()
        resp.text = "OK"
        return resp

    @patch("app.crews.llm.aliyun_llm.requests.post")
    def test_call_string(self, mock_post):
        mock_post.return_value = self._mock_response("你好")
        llm = _make_llm()
        result = llm.call("测试消息")
        assert result == "你好"
        mock_post.assert_called_once()

    @patch("app.crews.llm.aliyun_llm.requests.post")
    def test_call_messages_list(self, mock_post):
        mock_post.return_value = self._mock_response("回答")
        llm = _make_llm()
        result = llm.call([{"role": "user", "content": "你好"}])
        assert result == "回答"

    @patch("app.crews.llm.aliyun_llm.requests.post")
    def test_call_with_temperature(self, mock_post):
        mock_post.return_value = self._mock_response("回答")
        llm = _make_llm(temperature=0.7)
        llm.call("test")
        payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert payload["temperature"] == 0.7

    @patch("app.crews.llm.aliyun_llm.requests.post")
    def test_call_empty_content_retry(self, mock_post):
        empty_resp = self._mock_response("")
        ok_resp = self._mock_response("成功回答")
        mock_post.side_effect = [empty_resp, ok_resp]
        llm = _make_llm()
        result = llm.call("test")
        assert result == "成功回答"

    @patch("app.crews.llm.aliyun_llm.requests.post")
    def test_call_no_choices(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"choices": []}
        resp.raise_for_status = MagicMock()
        resp.text = "OK"
        mock_post.return_value = resp
        llm = _make_llm()
        with pytest.raises(ValueError, match="choices"):
            llm.call("test")

    @patch("app.crews.llm.aliyun_llm.requests.post")
    def test_call_server_error_retry(self, mock_post):
        error_resp = MagicMock()
        error_resp.status_code = 500
        error_resp.text = "Internal Server Error"
        error_resp.raise_for_status = MagicMock(side_effect=Exception("500"))

        ok_resp = self._mock_response("成功")
        mock_post.side_effect = [error_resp, ok_resp]
        llm = _make_llm(retry_count=1)
        result = llm.call("test")
        assert result == "成功"

    @patch("app.crews.llm.aliyun_llm.requests.post")
    def test_call_rate_limit_retry(self, mock_post):
        limit_resp = MagicMock()
        limit_resp.status_code = 429
        limit_resp.text = "Too Many Requests"
        limit_resp.raise_for_status = MagicMock(side_effect=Exception("429"))

        ok_resp = self._mock_response("ok")
        mock_post.side_effect = [limit_resp, ok_resp]
        llm = _make_llm(retry_count=1)
        result = llm.call("test")
        assert result == "ok"

    @patch("app.crews.llm.aliyun_llm.requests.post")
    def test_call_client_error_no_retry(self, mock_post):
        bad_resp = MagicMock()
        bad_resp.status_code = 400
        bad_resp.text = "Bad Request"
        bad_resp.raise_for_status.side_effect = Exception("400 Bad Request")
        mock_post.return_value = bad_resp
        llm = _make_llm()
        with pytest.raises(Exception):
            llm.call("test")

    @patch("app.crews.llm.aliyun_llm.requests.post")
    def test_call_timeout(self, mock_post):
        import requests
        mock_post.side_effect = requests.Timeout()
        llm = _make_llm(retry_count=0)
        with pytest.raises(TimeoutError):
            llm.call("test")

    @patch("app.crews.llm.aliyun_llm.requests.post")
    def test_call_with_callbacks(self, mock_post):
        mock_post.return_value = self._mock_response("ok")
        cb = MagicMock()
        cb.on_llm_start = MagicMock()
        cb.on_llm_end = MagicMock()
        llm = _make_llm()
        llm.call("test", callbacks=[cb])
        cb.on_llm_start.assert_called_once()
        cb.on_llm_end.assert_called_once()

    def test_max_iterations_zero(self):
        llm = _make_llm()
        with pytest.raises(RuntimeError, match="最大迭代"):
            llm.call("test", max_iterations=0)


class TestAliyunLLMMultimodal:
    def test_normalize_base64(self):
        llm = _make_llm()
        messages = [
            {"role": "user", "content": "请分析图片"},
            {"role": "assistant", "content": "add_image_to_content_local data:image/jpeg;base64,/9j/abc123"},
        ]
        result, flag = llm._normalize_multimodal_tool_result(messages)
        assert flag is True
        assert result[1]["role"] == "user"
        assert isinstance(result[1]["content"], list)

    def test_normalize_no_multimodal(self):
        llm = _make_llm()
        messages = [
            {"role": "user", "content": "普通消息"},
            {"role": "assistant", "content": "普通回复"},
        ]
        result, flag = llm._normalize_multimodal_tool_result(messages)
        assert flag is False
        assert len(result) == 2

    def test_normalize_http_image(self):
        llm = _make_llm()
        messages = [
            {"role": "assistant", "content": "add_image_to_content_local Observation: http://example.com/img.jpg"},
        ]
        result, flag = llm._normalize_multimodal_tool_result(messages)
        assert flag is True

    @patch("app.crews.llm.aliyun_llm.requests.post")
    def test_multimodal_model_switch(self, mock_post):
        """包含多模态消息时应切换到 image_model。"""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"choices": [{"message": {"content": "分析结果"}}]}
        resp.raise_for_status = MagicMock()
        resp.text = "OK"
        mock_post.return_value = resp

        llm = _make_llm(image_model="my-vl-model")
        llm.call([
            {"role": "user", "content": "请分析"},
            {"role": "assistant", "content": "add_image_to_content_local data:image/jpeg;base64,/9j/test"},
        ])
        payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert payload["model"] == "my-vl-model"


class TestAliyunLLMHelpers:
    def test_supports_function_calling(self):
        llm = _make_llm()
        assert llm.supports_function_calling() is False

    def test_supports_stop_words(self):
        llm = _make_llm()
        assert llm.supports_stop_words() is True

    def test_get_context_window_size_default(self):
        llm = _make_llm(model="qwen-test")
        assert llm.get_context_window_size() == 8192

    def test_get_context_window_size_long(self):
        llm = _make_llm(model="qwen-long-test")
        assert llm.get_context_window_size() == 200_000

    def test_get_context_window_size_max(self):
        llm = _make_llm(model="qwen-max")
        assert llm.get_context_window_size() == 8192

    def test_validate_messages_valid(self):
        llm = _make_llm()
        llm._validate_messages([
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "用户输入"},
            {"role": "assistant", "content": "助手回复"},
        ])

    def test_validate_messages_invalid_role(self):
        llm = _make_llm()
        with pytest.raises(ValueError, match="role"):
            llm._validate_messages([{"role": "invalid", "content": "test"}])

    def test_validate_messages_missing_content(self):
        llm = _make_llm()
        with pytest.raises(ValueError, match="content"):
            llm._validate_messages([{"role": "user"}])

    def test_validate_messages_multimodal_content(self):
        llm = _make_llm()
        llm._validate_messages([{
            "role": "user",
            "content": [
                {"type": "text", "text": "分析图片"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,abc"}},
            ],
        }])

    def test_prepare_stop_words_string(self):
        llm = _make_llm()
        assert llm._prepare_stop_words("stop") == "stop"

    def test_prepare_stop_words_list(self):
        llm = _make_llm()
        assert llm._prepare_stop_words(["stop1", "stop2"]) == ["stop1", "stop2"]

    def test_prepare_stop_words_none(self):
        llm = _make_llm()
        assert llm._prepare_stop_words("") is None
        assert llm._prepare_stop_words(None) is None


class TestAliyunLLMAcall:
    @pytest.mark.asyncio
    @patch("app.crews.llm.aliyun_llm.httpx.AsyncClient.post")
    async def test_acall(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"choices": [{"message": {"content": "异步回答"}}]}
        resp.raise_for_status = MagicMock()
        resp.text = "OK"
        mock_post.return_value = resp

        llm = _make_llm()
        result = await llm.acall("测试")
        assert result == "异步回答"


class TestGetLlm:
    @patch("app.crews.llm.get_settings")
    def test_get_llm_aliyun(self, mock_settings):
        s = MagicMock()
        s.llm_provider = "aliyun"
        s.llm_model = "qwen-plus"
        s.llm_api_key = "test-key"
        s.llm_region = "cn"
        s.llm_timeout = 600
        s.llm_retry_count = 3
        s.llm_image_model = "qwen3-vl-plus"
        mock_settings.return_value = s

        from app.crews.llm import get_llm
        llm = get_llm()
        assert isinstance(llm, AliyunLLM)

    @patch("app.crews.llm.get_settings")
    def test_get_llm_invalid_provider(self, mock_settings):
        s = MagicMock()
        s.llm_provider = "openai"
        mock_settings.return_value = s

        from app.crews.llm import get_llm
        with pytest.raises(ValueError, match="不支持"):
            get_llm(provider="openai")


class TestBoundImageRequests:
    def test_first_request_includes_image_even_if_model_answers_without_tools(self,tmp_path):
        import base64
        from tests.unit.test_service import image_bytes
        path=tmp_path/"photo.jpg"
        path.write_bytes(image_bytes("red"))
        response=MagicMock(status_code=200)
        response.json.return_value={"choices":[{"message":{"content":"直接给出分析，没有工具调用"}}]}
        llm=_make_llm(image_paths=[str(path)],image_model="qwen3-vl-plus")
        with patch("app.crews.llm.aliyun_llm.requests.post",return_value=response) as post:
            assert llm.call("请分析") == "直接给出分析，没有工具调用"
        payload=post.call_args.kwargs["json"]
        assert payload["model"]=="qwen3-vl-plus"
        images=[part["image_url"]["url"] for msg in payload["messages"] if isinstance(msg.get("content"),list) for part in msg["content"] if part["type"]=="image_url"]
        assert len(images)==1
        assert base64.b64decode(images[0].split(",",1)[1])==path.read_bytes()

    def test_concurrent_agents_bind_only_their_own_image(self,tmp_path):
        import base64
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from app.crews.xhs_note.tasks import build_visual_analysis_task,build_image_edit_task
        from app.schemas.xhs_note import XhsImageInput
        from tests.conftest import make_visual_analysis
        from tests.unit.test_service import image_bytes
        paths=[]
        for idx,color in enumerate(["red","blue"]):
            path=tmp_path/f"{idx}.jpg"
            path.write_bytes(image_bytes(color))
            paths.append(path)
        expected={}
        seen={}
        lock=threading.Lock()
        tasks=[]
        with patch("app.crews.xhs_note.agents.get_llm",lambda **kwargs:AliyunLLM(api_key="offline-only",**kwargs)):
            for idx,path in enumerate(paths):
                image=XhsImageInput(image_id=f"img_{idx}",file_name=path.name,local_path=str(path))
                for phase,task in [("visual",build_visual_analysis_task(image,"test")),("edit",build_image_edit_task("test",image,make_visual_analysis(idx)))]:
                    name=f"{phase}_{idx}"
                    tasks.append((name,task))
                    expected[name]=path.read_bytes()
        def offline_post(url,**kwargs):
            payload=kwargs["json"]
            assert payload["model"]=="qwen3-vl-plus"
            name=payload["messages"][0]["content"]
            images=[part["image_url"]["url"] for msg in payload["messages"] if isinstance(msg.get("content"),list) for part in msg["content"] if part["type"]=="image_url"]
            assert len(images)==1,"每个任务只应附加自己的图片，不能附加整批图片"
            with lock:
                seen[name]=base64.b64decode(images[0].split(",",1)[1])
            response=MagicMock(status_code=200)
            response.json.return_value={"choices":[{"message":{"content":"模型直接回答"}}]}
            return response
        with patch("app.crews.llm.aliyun_llm.requests.post",offline_post),ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda pair:pair[1].agent.llm.call(pair[0]),tasks))
        assert results==["模型直接回答"]*4
        assert seen==expected

    @pytest.mark.asyncio
    async def test_async_first_request_also_contains_bound_image(self,tmp_path):
        import base64
        from tests.unit.test_service import image_bytes
        path=tmp_path/"photo.jpg"
        path.write_bytes(image_bytes())
        response=MagicMock(status_code=200)
        response.json.return_value={"choices":[{"message":{"content":"异步直接回答"}}]}
        llm=_make_llm(image_paths=[str(path)],image_model="qwen3-vl-plus")
        with patch("app.crews.llm.aliyun_llm.httpx.AsyncClient.post",return_value=response) as post:
            assert await llm.acall("请分析") == "异步直接回答"
        payload=post.call_args.kwargs["json"]
        assert payload["model"]=="qwen3-vl-plus"
        url=payload["messages"][-1]["content"][-1]["image_url"]["url"]
        assert base64.b64decode(url.split(",",1)[1])==path.read_bytes()
