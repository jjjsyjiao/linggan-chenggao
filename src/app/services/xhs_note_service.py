"""图片校验、资源限制、临时文件生命周期与笔记生成。"""
from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
import warnings
from pathlib import Path
from typing import List
from weakref import WeakKeyDictionary

import aiofiles
from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings
from app.core.image_utils import compress_image_to_standard
from app.crews.xhs_note.runner import run_xhs_note_flow, run_xhs_note_generation_flow
from app.observability.logging import get_logger
from app.schemas.xhs_note import XhsGeneratedNote, XhsImageInput, XhsNoteIdeaRequest

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

logger = get_logger(__name__)
_generation_slots: WeakKeyDictionary = WeakKeyDictionary()


class NoteGenerationError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _sanitize_filename(filename: str | None, fallback_name: str, max_length: int = 255) -> str:
    name = (filename or fallback_name).replace("/", "_").replace("\\", "_")
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip() or fallback_name
    if len(name) <= max_length:
        return name
    suffix = Path(name).suffix[:20]
    return name[:max_length - len(suffix)] + suffix


async def _offload(function, *args, **kwargs):
    """线程工作完成后才允许清理目录，包括请求被取消的情况。"""
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


def _validate_and_compress(path: Path, max_size: int, quality: int) -> Path:
    settings = get_settings()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format not in {"JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF", "HEIF"}:
                    raise NoteGenerationError("仅支持 JPEG、PNG、WebP、静态 GIF、BMP、TIFF、HEIC 图片", 415)
                if image.width * image.height > settings.xhs_max_image_pixels:
                    raise NoteGenerationError("图片像素过大，请压缩到 4000 万像素以内", 413)
                if getattr(image, "n_frames", 1) != 1:
                    raise NoteGenerationError("仅支持静态图片，不支持视频、动图或多帧图片", 415)
                image.verify()
        return compress_image_to_standard(path, max_size=max_size, quality=quality)
    except NoteGenerationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise NoteGenerationError("图片像素过大，请缩小图片后重试", 413) from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise NoteGenerationError("图片无法解码或已损坏，请选择有效的静态图片", 415) from exc


async def _save_uploaded_images(files: List[UploadFile], base_dir: Path, max_size: int, quality: int) -> List[XhsImageInput]:
    settings = get_settings()
    images = []
    total_bytes = 0
    base_dir.mkdir(parents=True, exist_ok=True)
    for idx, file in enumerate(files):
        mime = (file.content_type or "").lower()
        if mime and not mime.startswith("image/") and mime != "application/octet-stream":
            raise NoteGenerationError("仅允许上传图片，不支持视频或其他文件", 415)
        image_id = f"img_{idx}"
        # 磁盘路径仅由服务端序号生成，重名图片与路径穿越均不会覆盖其他文件。
        path = base_dir / f"{image_id}.upload"
        size = 0
        async with aiofiles.open(path, "wb") as output:
            while chunk := await file.read(64 * 1024):
                size += len(chunk)
                total_bytes += len(chunk)
                if size > settings.xhs_max_image_bytes:
                    raise NoteGenerationError(f"单张图片不能超过 {settings.xhs_max_image_bytes // 1024 // 1024} MB", 413)
                if total_bytes > settings.xhs_max_total_bytes:
                    raise NoteGenerationError(f"图片总大小不能超过 {settings.xhs_max_total_bytes // 1024 // 1024} MB", 413)
                await output.write(chunk)
        if size == 0:
            raise NoteGenerationError("不能上传空图片", 415)
        local_path = await _offload(_validate_and_compress, path, max_size, quality)
        images.append(XhsImageInput(
            image_id=image_id,
            file_name=_sanitize_filename(file.filename, f"{image_id}.jpg", max_length=120),
            local_path=str(local_path),
        ))
    return images


def _cleanup_temp_directory(base_dir: Path) -> None:
    try:
        if base_dir.exists():
            shutil.rmtree(base_dir)
    except OSError:
        logger.warning("temp_directory_cleanup_failed", base_dir=str(base_dir))


def _get_slots() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if loop not in _generation_slots:
        _generation_slots[loop] = asyncio.Semaphore(get_settings().xhs_max_concurrent_generations)
    return _generation_slots[loop]


async def _generate(idea_text: str, files: List[UploadFile], *, structured: bool):
    settings = get_settings()
    idea_text = idea_text.strip()
    if not idea_text or len(idea_text) > 2000:
        raise NoteGenerationError("创作意图请填写 1～2000 个字符")
    if not files:
        raise NoteGenerationError("至少需要上传一张图片")
    if len(files) > settings.xhs_max_images:
        raise NoteGenerationError(f"最多支持上传 {settings.xhs_max_images} 张图片")
    slots = _get_slots()
    if slots.locked():
        raise NoteGenerationError("生成任务较多，请稍后重试", 429)
    await slots.acquire()
    base_dir = None
    try:
        output_root = Path(settings.data_output_dir).resolve() / "xhs_note"
        output_root.mkdir(parents=True, exist_ok=True)
        base_dir = Path(tempfile.mkdtemp(prefix="run_", dir=output_root))
        async with asyncio.timeout(settings.xhs_generation_timeout):
            images = await _save_uploaded_images(files, base_dir, settings.xhs_image_max_size, settings.xhs_image_quality)
            request = XhsNoteIdeaRequest(idea_text=idea_text, images=images)
            if settings.xhs_demo_mode:
                if settings.is_production:
                    raise NoteGenerationError("生产环境禁止开启演示模式", 503)
                note = XhsGeneratedNote(
                    title="[演示] 记录生活里的小美好",
                    content=f"[离线演示示例，非 AI 生成]\n\n创作方向：{idea_text[:300]}\n\n已收到 {len(images)} 张图片。配置模型密钥并关闭演示模式后，可生成基于图片的真实笔记。",
                    image_order=[image.image_id for image in images],
                    tags=["演示示例"], is_demo=True,
                )
                note.report = f"生成笔记标题: {note.title}\n生成笔记正文: {note.content}"
                return note if structured else note.report
            if not settings.llm_api_key or settings.llm_api_key.startswith("<"):
                raise NoteGenerationError("服务端尚未配置模型密钥，请设置 APP_LLM_API_KEY", 503)
            runner = run_xhs_note_generation_flow if structured else run_xhs_note_flow
            result, error = await runner(request)
            if error or result is None:
                raise NoteGenerationError(error or "模型未生成有效结果", 504 if "超时" in error else 502)
            return result
    except TimeoutError as exc:
        raise NoteGenerationError("生成超时，请减少图片数量后重试", 504) from exc
    finally:
        if base_dir is not None:
            await _offload(_cleanup_temp_directory, base_dir)
        slots.release()
        for file in files:
            await file.close()


async def generate_xhs_note(idea_text: str, files: List[UploadFile]) -> XhsGeneratedNote:
    return await _generate(idea_text, files, structured=True)


async def generate_xhs_note_report(idea_text: str, files: List[UploadFile]) -> tuple[str | None, str]:
    """兼容旧的 (report, error) 契约。"""
    try:
        return await _generate(idea_text, files, structured=False), ""
    except NoteGenerationError as exc:
        return None, str(exc)
    except Exception:
        logger.exception("xhs_note_service_exception")
        return None, "服务异常，请检查服务日志"
