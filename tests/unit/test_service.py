"""真实图片解码、上传资源限制与生成生命周期回归测试；模型调用全部 mock。"""
import asyncio
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image
from starlette.datastructures import UploadFile, Headers

from app.core.config import Settings
from app.services.xhs_note_service import (
    NoteGenerationError, _cleanup_temp_directory, _sanitize_filename,
    _save_uploaded_images, generate_xhs_note, generate_xhs_note_report,
)
from app.schemas.xhs_note import XhsGeneratedNote


def image_bytes(color="red", fmt="JPEG"):
    buffer = BytesIO()
    Image.new("RGB", (32, 24), color).save(buffer, format=fmt)
    return buffer.getvalue()


def upload(name="photo.jpg", content=None, mime="image/jpeg"):
    return UploadFile(BytesIO(image_bytes() if content is None else content), filename=name, headers=Headers({"content-type":mime}))


@pytest.fixture
def settings(tmp_path, monkeypatch):
    value = Settings(_env_file=None, llm_api_key="offline-test-key", data_output_dir=str(tmp_path), xhs_max_concurrent_generations=1)
    monkeypatch.setattr("app.services.xhs_note_service.get_settings", lambda: value)
    return value


def test_sanitize_and_cleanup(tmp_path):
    assert _sanitize_filename(None,"fallback.jpg") == "fallback.jpg"
    assert _sanitize_filename("  ","fallback.jpg") == "fallback.jpg"
    assert "/" not in _sanitize_filename("../../etc/passwd","fallback.jpg")
    assert len(_sanitize_filename("a"*300+".jpg","fallback.jpg")) == 255
    folder = tmp_path/"child"
    folder.mkdir()
    (folder/"test").write_text("ok")
    _cleanup_temp_directory(folder)
    assert not folder.exists()


async def test_duplicate_names_do_not_overwrite(tmp_path, settings):
    images=await _save_uploaded_images([upload("same.jpg",image_bytes("red")),upload("same.jpg",image_bytes("blue"))],tmp_path,1024,85)
    assert [image.image_id for image in images] == ["img_0","img_1"]
    assert images[0].local_path != images[1].local_path
    assert Path(images[0].local_path).read_bytes() != Path(images[1].local_path).read_bytes()


@pytest.mark.parametrize("content,mime",[(b"video data","video/mp4"),(b"not an image","image/jpeg"),(b"","image/jpeg")])
async def test_invalid_files_rejected(tmp_path,settings,content,mime):
    with pytest.raises(NoteGenerationError) as error:
        await _save_uploaded_images([upload(content=content,mime=mime)],tmp_path,1024,85)
    assert error.value.status_code == 415


async def test_animated_image_rejected(tmp_path,settings):
    buffer=BytesIO()
    Image.new("RGB",(5,5),"red").save(buffer,format="GIF",save_all=True,append_images=[Image.new("RGB",(5,5),"blue")])
    with pytest.raises(NoteGenerationError,match="动图"):
        await _save_uploaded_images([upload(content=buffer.getvalue(),mime="image/gif")],tmp_path,1024,85)


async def test_image_and_total_size_limits(tmp_path,settings):
    settings.xhs_max_image_bytes=100
    with pytest.raises(NoteGenerationError) as error:
        await _save_uploaded_images([upload()],tmp_path,1024,85)
    assert error.value.status_code==413
    settings.xhs_max_image_bytes=10000
    settings.xhs_max_total_bytes=len(image_bytes())+5
    with pytest.raises(NoteGenerationError) as error:
        await _save_uploaded_images([upload(),upload()],tmp_path,1024,85)
    assert error.value.status_code==413


async def test_no_files_and_count_limit(settings):
    assert "至少" in (await generate_xhs_note_report("test",[]))[1]
    settings.xhs_max_images=1
    with pytest.raises(NoteGenerationError,match="最多"):
        await generate_xhs_note("test",[upload(),upload()])


async def test_empty_idea_rejected(settings):
    with pytest.raises(NoteGenerationError):
        await generate_xhs_note("   ",[upload()])


@pytest.mark.parametrize("structured", [True, False])
async def test_success_selects_fast_or_full_and_cleans_uploads(settings, structured):
    file=upload()
    note=XhsGeneratedNote(title="标题",content="正文",image_order=["img_0"])
    fast=AsyncMock(return_value=(note,""))
    full=AsyncMock(return_value=("完整编辑报告",""))
    with patch("app.services.xhs_note_service.run_xhs_note_generation_flow",fast), patch("app.services.xhs_note_service.run_xhs_note_flow",full):
        if structured:
            result=await generate_xhs_note("test",[file])
            assert result.title=="标题"
            fast.assert_awaited_once()
            full.assert_not_awaited()
            request=fast.await_args.args[0]
        else:
            assert await generate_xhs_note_report("test",[file])==("完整编辑报告","")
            full.assert_awaited_once()
            fast.assert_not_awaited()
            request=full.await_args.args[0]
    assert request.idea_text=="test"
    assert [image.image_id for image in request.images]==["img_0"]
    assert not Path(request.images[0].local_path).exists()
    assert not list(Path(settings.data_output_dir).glob("xhs_note/run_*"))
    assert file.file.closed


@pytest.mark.parametrize("structured", [True, False])
@pytest.mark.parametrize("timeout_source", ["model", "deadline"])
async def test_timeout_cleans_uploads_releases_slot_and_preserves_error_contract(settings, structured, timeout_source):
    settings.xhs_generation_timeout=1
    file=upload()
    cancelled=asyncio.Event()
    requests=[]
    async def timed_out(request):
        requests.append(request)
        assert Path(request.images[0].local_path).is_file()
        if timeout_source=="model":
            return None,"模型请求超时，未自动重试"
        try:
            await asyncio.Future()
        finally:
            cancelled.set()
    selected=AsyncMock(side_effect=timed_out)
    unused=AsyncMock(side_effect=AssertionError("调用了错误的生成流程"))
    fast,full=(selected,unused) if structured else (unused,selected)
    with patch("app.services.xhs_note_service.run_xhs_note_generation_flow",fast), patch("app.services.xhs_note_service.run_xhs_note_flow",full):
        if structured:
            with pytest.raises(NoteGenerationError,match="超时") as error:
                await generate_xhs_note("test",[file])
            assert error.value.status_code==504
        else:
            result,error=await generate_xhs_note_report("test",[file])
            assert result is None
            assert "超时" in error
    selected.assert_awaited_once()
    unused.assert_not_awaited()
    if timeout_source=="deadline":
        assert cancelled.is_set(),"截止时间到达必须取消生成协程"
    assert file.file.closed
    assert not Path(requests[0].images[0].local_path).exists()
    assert not list(Path(settings.data_output_dir).glob("xhs_note/run_*"))
    # 同一事件循环上的下次请求可立即使用已释放的唯一并发槽。
    settings.xhs_demo_mode=True
    assert (await generate_xhs_note("test",[upload()])).is_demo


async def test_exception_and_cancel_cleanup(settings):
    with patch("app.services.xhs_note_service.run_xhs_note_generation_flow",AsyncMock(side_effect=RuntimeError("failed"))):
        with pytest.raises(RuntimeError):
            await generate_xhs_note("test",[upload()])
    entered=asyncio.Event()
    async def slow(*args):
        entered.set()
        await asyncio.Future()
    with patch("app.services.xhs_note_service.run_xhs_note_generation_flow",slow):
        task=asyncio.create_task(generate_xhs_note("test",[upload()]))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not list(Path(settings.data_output_dir).glob("xhs_note/run_*"))
    # 取消后必须释放并发槽。
    settings.xhs_demo_mode=True
    assert (await generate_xhs_note("test",[upload()])).is_demo


async def test_busy_rejected_without_queueing(settings):
    entered=asyncio.Event()
    release=asyncio.Event()
    note=XhsGeneratedNote(title="标题",content="正文",image_order=["img_0"])
    async def slow(*args):
        entered.set()
        await release.wait()
        return note,""
    with patch("app.services.xhs_note_service.run_xhs_note_generation_flow",slow):
        task=asyncio.create_task(generate_xhs_note("test",[upload()]))
        await entered.wait()
        with pytest.raises(NoteGenerationError) as error:
            await generate_xhs_note("test",[upload()])
        assert error.value.status_code==429
        release.set()
        await task


async def test_missing_key_is_explicit_and_cleanup(settings):
    settings.llm_api_key=""
    with pytest.raises(NoteGenerationError) as error:
        await generate_xhs_note("test",[upload()])
    assert error.value.status_code==503
    assert not list(Path(settings.data_output_dir).glob("xhs_note/run_*"))


async def test_production_demo_forbidden(settings):
    settings.env="production"
    settings.xhs_demo_mode=True
    with pytest.raises(NoteGenerationError) as error:
        await generate_xhs_note("test",[upload()])
    assert error.value.status_code==503
