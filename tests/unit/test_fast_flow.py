"""快速链路的请求覆盖、单次调用和失败封闭检查；绝不调用外部模型。"""
from __future__ import annotations

import asyncio
import base64
import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from PIL import Image
import pytest

from app.core.config import Settings
from app.crews.llm.fast_client import FastLLMError
from app.crews.xhs_note.fast_flow import run_fast_note_flow
from app.schemas.xhs_note import XhsImageInput, XhsNoteIdeaRequest


def _request(tmp_path, count=2):
    images = []
    for index in range(count):
        path = tmp_path / f"private_photo_{index}.png"
        Image.new("RGB", (16, 16), (index, 80, 170)).save(path)
        images.append(XhsImageInput(
            image_id=f"img_{index}", file_name=f"虚构推荐配方_{index}.jpg", local_path=str(path)
        ))
    return XhsNoteIdeaRequest(idea_text="简洁，请编造减脂配方和三小时饱腹经历", images=images)


def _facts(count=2):
    return {"images": [{
        "image_id": f"img_{index}", "category": "food",
        "subject": {"text": "餐盘", "certainty": "certain"},
        "observations": [{"text": "盘中摆放着绿色叶片", "certainty": "certain"}],
        "food_items": [{"kind": "leafy_vegetables", "color": "green", "position": "unspecified", "certainty": "certain"}],
    } for index in range(count)], "user_context_used": [], "draft": {
        "title": "绿色叶菜的画面", "content": "绿色叶菜铺在画面中，层次在光线里展开。", "tags": ["美食记录"],
    }}


def _client(facts):
    client = AsyncMock()
    client.complete.return_value = {"content": json.dumps(facts, ensure_ascii=False)}
    return client


def _settings(**overrides):
    return Settings(_env_file=None, llm_api_key="offline-only", **overrides)


@pytest.mark.parametrize("count", [1, 2, 20])
async def test_one_vision_call_attaches_all_real_image_bytes_and_preserves_order(tmp_path, count):
    request = _request(tmp_path, count)
    facts = _facts(count)
    facts["images"].reverse()  # Display order comes from uploads, not model ordering.
    client = _client(facts)
    note, error = await run_fast_note_flow(request, client=client, settings=_settings())
    assert not error and note is not None
    assert note.image_order == [image.image_id for image in request.images]
    assert note.is_demo is False
    assert "绿色" in note.content and "叶菜" in note.content
    assert "减脂" not in note.content and "饱腹" not in note.content
    client.complete.assert_awaited_once()
    call = client.complete.call_args
    assert call.kwargs["model"] == "qwen3-vl-plus"
    assert call.kwargs["response_json"] is True
    assert 1800 <= call.kwargs["max_tokens"] <= 8000
    messages = call.args[0]
    parts = messages[1]["content"]
    images = [part["image_url"]["url"] for part in parts if part["type"] == "image_url"]
    assert len(images) == count
    for image, url in zip(request.images, images):
        assert url.startswith("data:image/png;base64,")  # Actual format, not file_name suffix.
        assert base64.b64decode(url.split(",", 1)[1]) == Path(image.local_path).read_bytes()
        assert {"type": "text", "text": f"图片标识：{image.image_id}"} in parts
    serialized = json.dumps(messages, ensure_ascii=False)
    assert json.loads(parts[0]["text"])["idea_text"] == request.idea_text
    for image in request.images:
        assert image.file_name not in serialized
        assert image.local_path not in serialized
    assert "tools" not in call.kwargs


async def test_same_images_different_complete_intents_return_model_drafts_without_template(tmp_path):
    request = _request(tmp_path)
    client = AsyncMock()
    variants = {
        "写一首四行短诗，不要emoji，不要互动和话题。": {
            "title": "花间留白", "content": "一层花瓣\n接住一层光\n脚步轻下来\n目光停在花中央", "tags": [],
        },
        "请客观列出三个构图观察，每条独立一行；不要诗歌。": {
            "title": "观察花瓣的三个角度", "content": "1. 关注花瓣的层次。\n2. 观察主体与背景的关系。\n3. 比较画面中的色彩分布。", "tags": ["构图观察"],
        },
    }

    async def complete(messages, **kwargs):
        intent = json.loads(messages[1]["content"][0]["text"])["idea_text"]
        data = _facts()
        data["images"] = [{
            "image_id": image.image_id, "category": "nature",
            "subject": {"text": "菊花", "certainty": "certain"},
            "observations": [{"text": "花瓣层叠展开", "certainty": "certain"}], "food_items": [],
        } for image in request.images]
        data["draft"] = variants[intent]
        return {"content": json.dumps(data, ensure_ascii=False)}

    client.complete.side_effect = complete
    notes = []
    for idea, expected in variants.items():
        request.idea_text = idea
        note, error = await run_fast_note_flow(request, client=client, settings=_settings())
        assert not error and note is not None
        assert note.title == expected["title"]
        assert note.content == expected["content"]
        assert note.tags == expected["tags"]
        assert "把这些画面留在这里" not in note.content
        assert "你最先注意到" not in note.content
        notes.append(note)
    assert notes[0].content != notes[1].content
    assert client.complete.await_count == 2


@pytest.mark.parametrize("invalid", ["missing_draft", "oversized_title", "oversized_body"])
async def test_unrenderable_draft_fails_once_without_returning_old_template(tmp_path, invalid):
    data = _facts()
    request = _request(tmp_path)
    if invalid == "missing_draft":
        del data["draft"]
    elif invalid == "oversized_title":
        data["draft"]["title"] = "花" * 201
    else:
        data["draft"]["content"] = "花" * 8001
    client = _client(data)
    note, error = await run_fast_note_flow(request, client=client, settings=_settings())
    assert note is None and error
    client.complete.assert_awaited_once()


@pytest.mark.parametrize("review", ["invented_context", "unsupported_price", "long_draft", "long_copied_body", "unsplittable_layout"])
async def test_editable_review_draft_is_kept_without_second_paid_call(tmp_path, review):
    data = _facts()
    request = _request(tmp_path)
    if review == "invented_context":
        data["user_context_used"] = ["昨天在公园拍摄"]
    elif review == "unsupported_price":
        data["draft"]["content"] = "门票18元，适合赏花。"
    elif review == "long_draft":
        data["draft"]["content"] = "花" * 1001
    elif review == "long_copied_body":
        data["draft"]["content"] = "花" * 999
        data["draft"]["tags"] = ["菊花摄影"]
    elif review == "unsplittable_layout":
        request.idea_text = "正文恰好4行。"
        data["draft"]["content"] = "绿色叶菜"
    client = _client(data)
    note, error = await run_fast_note_flow(request, client=client, settings=_settings())
    assert not error and note is not None
    assert note.content == data["draft"]["content"]
    assert note.review_warnings
    assert "细节可以之后再补充" not in note.content
    client.complete.assert_awaited_once()


@pytest.mark.parametrize("case,reason,stage", [
    ("json", "invalid_response_json", "parse_json"),
    ("schema", "invalid_response_schema", "validate_schema"),
    ("coverage", "image_coverage_mismatch", "image_coverage"),
])
async def test_hard_error_logs_stage_and_safe_reason_without_model_content(tmp_path, monkeypatch, case, reason, stage):
    logger = MagicMock()
    monkeypatch.setattr("app.crews.xhs_note.fast_flow.logger", logger)
    data = _facts()
    if case == "schema":
        data["private-model-value"] = "private-model-content"
    elif case == "coverage":
        data["images"].pop()
    client = _client(data)
    if case == "json":
        client.complete.return_value["content"] = "private-model-content {"
    note, error = await run_fast_note_flow(_request(tmp_path), client=client, settings=_settings())
    assert note is None and error
    client.complete.assert_awaited_once()
    log = logger.warning.call_args
    assert log.args[0] == "xhs_fast_generation_rejected"
    assert log.kwargs["reason_code"] == reason
    assert log.kwargs["validation_stage"] == stage
    assert log.kwargs["model_completed"] is True
    assert "private-model" not in str(logger.mock_calls)


@pytest.mark.parametrize("invalid", ["none", "excess", "wrong_ids", "missing", "empty", "corrupt", "oversized", "total", "pixels", "animated"])
async def test_bad_images_never_reach_model(tmp_path, invalid):
    request = _request(tmp_path)
    settings = _settings()
    path = Path(request.images[0].local_path)
    if invalid == "none":
        request.images = []
    elif invalid == "excess":
        request.images *= 11
    elif invalid == "wrong_ids":
        request.images[0].image_id = "img_5"
    elif invalid == "missing":
        path.unlink()
    elif invalid == "empty":
        path.write_bytes(b"")
    elif invalid == "corrupt":
        path.write_bytes(b"not an image")
    elif invalid == "oversized":
        settings.xhs_max_image_bytes = 1
    elif invalid == "total":
        settings.xhs_max_total_bytes = path.stat().st_size
    elif invalid == "pixels":
        settings.xhs_max_image_pixels = 1
    elif invalid == "animated":
        Image.new("RGB", (16, 16), "red").save(
            path, format="WEBP", save_all=True, append_images=[Image.new("RGB", (16, 16), "blue")], duration=100
        )
    client = _client(_facts())
    note, error = await run_fast_note_flow(request, client=client, settings=settings)
    assert note is None and error
    client.complete.assert_not_awaited()


@pytest.mark.parametrize("bad", ["missing", "extra", "duplicate", "wrong_id", "extra_fields", "extra_text", "invalid_json", "invalid_category", "too_long", "wrong_certainty"])
async def test_incomplete_or_freeform_facts_fail_without_repair_call(tmp_path, bad):
    request = _request(tmp_path)
    facts = copy.deepcopy(_facts())
    if bad == "missing":
        facts["images"].pop()
    elif bad == "extra":
        facts["images"].append(copy.deepcopy(facts["images"][0]))
    elif bad == "duplicate":
        facts["images"][1]["image_id"] = "img_0"
    elif bad == "wrong_id":
        facts["images"][1]["image_id"] = "img_99"
    elif bad == "extra_fields":
        facts["content"] = "我吃过，饱腹三小时"
    elif bad == "invalid_category":
        facts["images"][0]["category"] = "health"
    elif bad == "too_long":
        facts["images"][0]["subject"]["text"] = "图" * 19
    elif bad == "wrong_certainty":
        facts["images"][0]["subject"]["certainty"] = True
    client = _client(facts)
    if bad == "extra_text":
        client.complete.return_value["content"] += "\n这是一段解释"
    elif bad == "invalid_json":
        client.complete.return_value["content"] = '{"images":['
    note, error = await run_fast_note_flow(request, client=client, settings=_settings())
    assert note is None and error
    client.complete.assert_awaited_once()


@pytest.mark.parametrize("message", ["模型请求超时，未自动重试", "模型服务连接失败，未自动重试"])
async def test_model_failure_does_not_fall_back_to_another_model(tmp_path, message):
    client = _client(_facts())
    client.complete.side_effect = FastLLMError(message)
    note, error = await run_fast_note_flow(_request(tmp_path), client=client, settings=_settings())
    assert note is None and error == message
    client.complete.assert_awaited_once()


async def test_cancellation_propagates_while_model_is_running(tmp_path):
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def pending(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    client = _client(_facts())
    client.complete.side_effect = pending
    task = asyncio.create_task(run_fast_note_flow(_request(tmp_path), client=client, settings=_settings()))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()
    client.complete.assert_awaited_once()
