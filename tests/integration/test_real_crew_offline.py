"""使用真实 Crew/Agent/Task 与 HTTPX 适配器离线执行全部三阶段，验证版本兼容。"""
import json
from unittest.mock import patch

import httpx

from app.crews.llm.aliyun_llm import AliyunLLM
from app.crews.xhs_note.flows import run_xhs_note_generation_flow
from app.schemas.xhs_note import XhsImageInput, XhsNoteIdeaRequest
from tests.conftest import make_visual_analysis, make_edit_plan, make_strategy_brief, make_copywriting, make_seo_note
from tests.unit.test_service import image_bytes


async def test_real_crew_three_phases_and_bound_images(tmp_path):
    image_path=tmp_path/"image.jpg"
    image_path.write_bytes(image_bytes())
    responses=iter([
        "Final Answer: "+make_visual_analysis(0).model_dump_json(),
        "Final Answer: 视觉汇总完成",
        "Final Answer: "+make_edit_plan(0).model_dump_json(),
        "Final Answer: 图片编辑汇总完成",
        "Final Answer: "+make_strategy_brief().model_dump_json(),
        "Final Answer: "+make_copywriting().model_dump_json(),
        "Final Answer: "+make_seo_note().model_dump_json(),
    ])
    seen_payloads=[]
    def offline_post(url,**kwargs):
        seen_payloads.append(kwargs["json"])
        return httpx.Response(200,json={"choices":[{"message":{"content":next(responses)}}]},request=httpx.Request("POST",url))
    with patch("app.crews.xhs_note.agents.get_llm", lambda **kwargs:AliyunLLM(api_key="offline-only",**kwargs)),patch("app.crews.llm.aliyun_llm.requests.post",offline_post):
        result,error=await run_xhs_note_generation_flow(XhsNoteIdeaRequest(idea_text="分享沙拉",images=[XhsImageInput(image_id="img_0",file_name="image.jpg",local_path=str(image_path))]))
    assert not error,error
    assert result.title==make_seo_note().optimized_title
    assert result.image_order==["img_0"]
    assert len(seen_payloads)==7
    multimodal=[payload for payload in seen_payloads if payload["model"]=="qwen3-vl-plus"]
    assert len(multimodal)==2,"视觉分析和图片编辑必须直接使用视觉模型，汇总任务保持文本"
    assert seen_payloads[0]["model"]=="qwen3-vl-plus"
    assert seen_payloads[1]["model"]=="qwen-plus"
    assert seen_payloads[2]["model"]=="qwen3-vl-plus"
    import base64
    for payload in multimodal:
        urls=[part["image_url"]["url"] for message in payload["messages"] if isinstance(message.get("content"),list) for part in message["content"] if part.get("type")=="image_url"]
        assert len(urls)==1
        assert base64.b64decode(urls[0].split(",",1)[1])==image_path.read_bytes()
    assert any(
        isinstance(message.get("content"),list) and any(item.get("type")=="image_url" for item in message["content"])
        for payload in multimodal for message in payload["messages"]
    )
