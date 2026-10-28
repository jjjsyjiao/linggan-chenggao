"""验证真正的子进程取消与结果传输；不加载模型、不访问网络。"""
import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.crews.xhs_note.runner import run_xhs_note_flow, run_xhs_note_generation_flow
from app.schemas.xhs_note import XhsImageInput, XhsNoteIdeaRequest


def request(tmp_path):
    return XhsNoteIdeaRequest(idea_text="test",images=[XhsImageInput(image_id="img_0",file_name="test.jpg",local_path=str(tmp_path/"img_0.jpg"))])


@pytest.mark.parametrize("runner,mode", [
    (run_xhs_note_generation_flow, "fast"),
    (run_xhs_note_flow, "full"),
])
async def test_real_process_terminated_on_cancel(tmp_path, runner, mode):
    original=asyncio.create_subprocess_exec
    started=asyncio.Event()
    children=[]
    async def spawn(*args,**kwargs):
        assert args == (sys.executable, "-m", "app.crews.xhs_note.worker", str(tmp_path/"result.json"), mode)
        process=await original(sys.executable,"-c","import sys,time;sys.stdin.buffer.read();time.sleep(60)",**kwargs)
        children.append(process)
        started.set()
        return process
    with patch("app.crews.xhs_note.runner.asyncio.create_subprocess_exec",spawn):
        task=asyncio.create_task(runner(request(tmp_path)))
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert children[0].returncode is not None


@pytest.mark.parametrize("runner,mode", [
    (run_xhs_note_generation_flow, "fast"),
    (run_xhs_note_flow, "full"),
])
async def test_real_process_result_transfer(tmp_path, runner, mode):
    original=asyncio.create_subprocess_exec
    output=tmp_path/"result.json"
    script="import sys,json;from pathlib import Path;req=json.load(sys.stdin);Path(sys.argv[1]).write_text(json.dumps({'note':{'title':'title','content':'content','image_order':['img_0'],'report':'完整报告'},'error':''}))"
    async def spawn(*args,**kwargs):
        assert args == (sys.executable, "-m", "app.crews.xhs_note.worker", str(output), mode)
        assert kwargs["env"]["CREWAI_TELEMETRY_DISABLED"]=="true"
        assert kwargs["env"]["APP_TOOLS_DIRECTORY_READ_ROOT"]==str(tmp_path)
        assert kwargs["env"]["APP_REQUEST_ID"]=="runner-request-id"
        return await original(sys.executable,"-c",script,str(output),**kwargs)
    with patch("app.crews.xhs_note.runner.asyncio.create_subprocess_exec",spawn), patch("app.crews.xhs_note.runner.get_request_id",return_value="runner-request-id"):
        result,error=await runner(request(tmp_path))
    assert error==""
    if mode == "fast":
        assert result.title=="title"
        assert result.image_order==["img_0"]
    else:
        assert result=="完整报告"


@pytest.mark.parametrize("case,code", [
    ("exit", "worker_exit_nonzero"),
    ("missing", "worker_result_missing"),
    ("json", "worker_result_invalid_json"),
    ("envelope", "worker_result_invalid_envelope"),
    ("note", "worker_note_invalid"),
    ("reported", "worker_reported_error"),
])
async def test_bad_worker_results_have_safe_diagnostics_without_payloads(tmp_path, case, code):
    original=asyncio.create_subprocess_exec
    sentinel="PRIVATE_MODEL_CONTENT_OR_KEY"
    contents={
        "json":'{"note":"'+sentinel+'"',
        "envelope":json.dumps([sentinel]),
        "note":json.dumps({"note":{"title":"","content":sentinel,"image_order":[]},"error":""}),
        "reported":json.dumps({"note":None,"error":sentinel}),
    }
    script="import sys;from pathlib import Path;sys.stdin.buffer.read();"
    if case=="exit":
        script+="sys.exit(7)"
    elif case!="missing":
        script+="Path(sys.argv[1]).write_text(sys.argv[2])"
    async def spawn(*args,**kwargs):
        return await original(sys.executable,"-c",script,str(tmp_path/"result.json"),contents.get(case,""),**kwargs)
    logger=MagicMock()
    with patch("app.crews.xhs_note.runner.asyncio.create_subprocess_exec",spawn), patch("app.crews.xhs_note.runner.logger",logger):
        note,error=await run_xhs_note_generation_flow(request(tmp_path))
    assert note is None and error
    assert logger.warning.call_args.kwargs["reason_code"]==code
    assert sentinel not in repr(logger.mock_calls)
    if case=="exit":
        assert logger.warning.call_args.kwargs["exit_code"]==7


async def test_worker_start_failure_has_safe_diagnostic(tmp_path):
    logger=MagicMock()
    with patch("app.crews.xhs_note.runner.asyncio.create_subprocess_exec",AsyncMock(side_effect=OSError("PRIVATE_ERROR_MESSAGE"))), patch("app.crews.xhs_note.runner.logger",logger):
        note,error=await run_xhs_note_generation_flow(request(tmp_path))
    assert note is None and error
    assert logger.warning.call_args.kwargs["reason_code"]=="worker_start_failed"
    assert "PRIVATE_ERROR_MESSAGE" not in repr(logger.mock_calls)
