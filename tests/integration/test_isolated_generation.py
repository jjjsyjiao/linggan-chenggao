"""HTTP→real worker→local upstream; editable warnings and safe correlated logs."""
import asyncio
import base64
import json
import re
import shlex
import statistics
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from app.core.config import Settings
from app.core.image_utils import compress_image_to_standard
from app.main import create_application
from tests.unit.test_service import image_bytes


async def test_same_images_follow_latest_intent_and_return_editable_review_warnings(tmp_path, monkeypatch):
    images = [{
        "image_id": f"img_{index}", "category": "nature",
        "subject": {"text": "菊花", "certainty": "certain"},
        "observations": [
            {"text": "主体位于画面中央", "certainty": "certain"},
            {"text": "花瓣向四周展开，近景突出花朵轮廓", "certainty": "certain"},
        ], "food_items": [],
    } for index in range(2)]
    poem = {"title": "菊花与光", "content": "菊花安静地舒展，\n花瓣围住一圈光，\n把柔和留在这一帧。", "tags": ["菊花", "花间短诗"]}
    observation = {"title": "阳台菊花的构图观察", "content": "这两张菊花照片是我在自家阳台拍的。\n\n- 主体位于画面中央。\n- 花瓣向四周展开。\n- 近景突出花朵轮廓。", "tags": ["菊花", "构图观察"]}

    def generation(draft, *, context=None, supplied_images=None):
        return {"images": images if supplied_images is None else supplied_images, "user_context_used": context or [], "draft": draft}

    cases = [
        {"name": "poem", "idea": "请结合这两张菊花照片写一首温柔的短诗，50字以内，不写构图清单。", "kind": "normal", "generation": generation(poem)},
        {"name": "context", "idea": "背景：这两张菊花照片是我在自家阳台拍的。请用客观语气列出三个构图观察，不写诗，120字以内。", "kind": "normal", "generation": generation(observation, context=["这两张菊花照片是我在自家阳台拍的。"])},
        {"name": "source_quote", "idea": "请为这组菊花写短诗，不添加拍摄地或购买经历。", "kind": "warning", "generation": generation(poem, context=["这些菊花是我在杭州买的。"])},
        {"name": "unsupported_quantity", "idea": "请客观描述这组菊花，不添加价格或功效。", "kind": "warning", "generation": generation({**poem, "content": "这盆菊花18元，花瓣向四周展开。"})},
        {"name": "layout", "idea": "请写准确4行短诗，每行一句。", "kind": "warning", "generation": generation({**poem, "content": "花瓣向着光线静静舒展"})},
        {"name": "long_title", "idea": "请给这组菊花写自然的笔记标题。", "kind": "warning", "generation": generation({**poem, "title": "菊花" * 12})},
        {"name": "long_body", "idea": "请写一篇完整的菊花观察记录。", "kind": "warning", "generation": generation({**poem, "content": "花瓣向外舒展。" * 150})},
        {"name": "missing_image", "idea": "结合全部照片写菊花短诗，逐图检查。", "kind": "hard", "generation": generation(poem, supplied_images=images[:1])},
        {"name": "duplicate_image", "idea": "结合全部照片写菊花短诗，不重复图片标识。", "kind": "hard", "generation": generation(poem, supplied_images=[images[0], images[0]])},
        {"name": "bad_json", "idea": "结合全部照片写菊花短诗，返回完整结构。", "kind": "hard", "raw": '{"images":['},
    ]
    by_idea = {case["idea"]: case for case in cases}
    originals = [image_bytes("red"), image_bytes("blue")]
    seen, seen_ideas, upstream_errors = [], [], []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(payload)
            try:
                user = next(message for message in payload["messages"] if message["role"] == "user")
                idea = json.loads(user["content"][0]["text"])["idea_text"]
                seen_ideas.append(idea)
                case = by_idea[idea]
                value = case.get("raw") or json.dumps(case["generation"], ensure_ascii=False)
            except (KeyError, StopIteration, TypeError, ValueError) as error:
                upstream_errors.append(type(error).__name__)
                self.send_response(400)
                self.end_headers()
                return
            time.sleep(0.03)
            content = json.dumps({"choices": [{"message": {"content": value}}]}, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    for key, value in {
        "APP_LLM_API_KEY": "offline-only-not-a-real-key",
        "APP_LLM_BASE_URL": f"http://127.0.0.1:{server.server_port}/chat/completions",
        "APP_DATA_OUTPUT_DIR": str(tmp_path / "output"), "APP_LOG_DIR": str(tmp_path / "logs"),
        "APP_XHS_DEMO_MODE": "false", "APP_LLM_IMAGE_MODEL": "qwen3-vl-plus", "APP_ENV": "development",
    }.items():
        monkeypatch.setenv(key, value)
    settings = Settings(_env_file=None, api_keys="")
    expected_images = []
    for index, original in enumerate(originals):
        path = tmp_path / f"expected_{index}.jpg"
        path.write_bytes(original)
        expected_images.append(compress_image_to_standard(path, settings.xhs_image_max_size, settings.xhs_image_quality).read_bytes())
    for module in ["app.main", "app.core.security", "app.services.xhs_note_service"]:
        monkeypatch.setattr(module + ".get_settings", lambda: settings)
    app = create_application()
    try:
        latencies, returned = [], []
        started = time.perf_counter()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for index, case in enumerate(cases):
                rid = "isolated-" + case["name"]
                task = asyncio.create_task(client.post(
                    "/api/v1/xhs/notes/generate", headers={"X-Request-ID": rid}, data={"idea_text": case["idea"]},
                    files=[("images", ("photo.jpg", original, "image/jpeg")) for original in originals],
                ))
                while not task.done() or len(latencies) < 10:
                    before = time.perf_counter()
                    assert (await client.get("/health/live")).status_code == 200
                    latencies.append((time.perf_counter() - before) * 1000)
                    await asyncio.sleep(0.04)
                    assert time.perf_counter() - started < 25, "离线生成进程异常挂起"
                response = await task
                body = response.json()
                assert response.headers["X-Request-ID"] == body["request_id"] == rid
                if case["kind"] == "hard":
                    assert response.status_code == 502, case["name"]
                    assert body.get("data") is None
                else:
                    assert response.status_code == 200, case["name"]
                    note = body["data"]
                    returned.append(note)
                    for field, value in case["generation"]["draft"].items():
                        assert note[field] == value, "草稿应完整保留，不能因警示套模板或截断"
                    assert note["image_order"] == ["img_0", "img_1"]
                    assert note["is_demo"] is False
                    assert bool(note["review_warnings"]) == (case["kind"] == "warning"), case["name"]
                assert "local_path" not in response.text
                assert len(seen) == index + 1, "警示和拒绝都不得触发第二次模型调用"
                assert not list((tmp_path / "output" / "xhs_note").glob("run_*"))

        assert seen_ideas == [case["idea"] for case in cases]
        assert not upstream_errors
        assert returned[0]["title"] != returned[1]["title"]
        assert returned[0]["content"] != returned[1]["content"]
        assert len(returned[0]["content"]) <= 50 and len(returned[1]["content"]) <= 120
        for payload in seen:
            assert payload["model"] == "qwen3-vl-plus"
            assert payload["response_format"] == {"type": "json_object"}
            assert not payload.get("tools") and not payload.get("tool_choice")
            urls = [part["image_url"]["url"] for message in payload["messages"] if isinstance(message.get("content"), list) for part in message["content"] if part.get("type") == "image_url"]
            assert len(urls) == 2
            assert [base64.b64decode(url.split(",", 1)[1]) for url in urls] == expected_images

        # Inspect only local test logs. Never emit their raw contents on failure.
        log_text = "\n".join(path.read_text() for path in (tmp_path / "logs").glob("*.log"))
        events = []
        for line in log_text.splitlines():
            fields = {part.partition("=")[0]: part.partition("=")[2] for part in shlex.split(line) if "=" in part}
            events.append({key: fields.get(key) for key in ("event", "request_id", "reason_code")})
        for case in cases:
            matching = [event for event in events if event["request_id"] == "isolated-" + case["name"]]
            assert sum(event["event"] == "fast_llm_request" for event in matching) == 1, case["name"]
            assert sum(event["event"] == "fast_llm_completed" for event in matching) == 1, case["name"]
            if case["kind"] == "warning":
                assert any(event["event"] == "xhs_fast_generation_review" and event["reason_code"] == "manual_review_required" for event in matching), case["name"]
            elif case["kind"] == "hard":
                assert any(event["event"] == "xhs_fast_generation_rejected" and re.fullmatch(r"[A-Za-z0-9_]+", event["reason_code"] or "") for event in matching), case["name"]
        assert "offline-only-not-a-real-key" not in log_text
        assert "data:image/" not in log_text
        assert all(case["idea"] not in log_text for case in cases)
        assert all(case.get("generation", {}).get("draft", {}).get("content", "SENTINEL_NOT_USED") not in log_text for case in cases)
        assert max(latencies) < 1000
        print(json.dumps({"offline_requests": len(cases), "offline_generation_seconds": round(time.perf_counter() - started, 3), "health_samples": len(latencies), "health_p50_ms": round(statistics.median(latencies), 3), "health_max_ms": round(max(latencies), 3)}))
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
