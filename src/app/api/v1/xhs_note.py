"""快速看图笔记与兼容的完整多 Agent 报告 API。"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from app.api.dependencies import get_request_id, require_api_key
from app.observability.logging import get_logger
from app.schemas.common import ApiResponse
from app.schemas.xhs_note import XhsGeneratedNote, XhsNoteReportResponse
from app.services.xhs_note_service import NoteGenerationError, generate_xhs_note, generate_xhs_note_report


router = APIRouter()
logger = get_logger(__name__)


async def _generate_for_request(request: Request, idea_text: str, images: List[UploadFile]):
    task = asyncio.create_task(generate_xhs_note(idea_text, images))
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=0.5)
            if done:
                return task.result()
            if await request.is_disconnected():
                raise HTTPException(499, "客户端已断开，生成任务已取消")
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


@router.post(
    "/notes/generate",
    response_model=ApiResponse[XhsGeneratedNote],
    summary="为移动客户端生成标题、正文、标签及图片顺序",
    description=(
        "一次视觉请求携带全部图片和完整创作要求，同时返回逐图观察与标题、正文、标签。"
        "用户要求决定主题、体裁、结构、篇幅和语气；本地验证来源、完整性与长度，不用固定模板覆盖成稿。"
        "不调用独立策略、修图、文案或 SEO Agent，不自动重试。结果仍需发布前人工核对。"
    ),
)
async def create_xhs_note(
    request: Request,
    idea_text: str = Form(...),
    images: List[UploadFile] = File(...),
    request_id: str = Depends(get_request_id),
    _api_key: str = Depends(require_api_key),
) -> ApiResponse[XhsGeneratedNote]:
    try:
        note = await _generate_for_request(request, idea_text, images)
    except HTTPException:
        raise
    except NoteGenerationError as exc:
        logger.warning("xhs_note_rejected", status_code=exc.status_code, reason=str(exc), request_id=request_id)
        raise HTTPException(exc.status_code, str(exc), headers={"Retry-After": "10"} if exc.status_code == 429 else None) from exc
    except Exception as exc:
        logger.exception("xhs_note_generation_failed", request_id=request_id)
        raise HTTPException(500, "笔记生成异常，请凭请求 ID 查询服务日志") from exc
    return ApiResponse(data=note, request_id=request_id)


@router.post(
    "/notes/report",
    response_model=ApiResponse[XhsNoteReportResponse],
    summary="生成小红书爆款笔记撰写报告",
    description=(
        "通过 form-data 上传创作意图与多张图片，"
        "由多 Agent 协同完成视觉分析、图片编辑方案、内容策略、文案撰写与 SEO 优化，"
        "最终返回结构化的小红书笔记撰写报告。"
    ),
    status_code=status.HTTP_200_OK,
)
async def create_xhs_note_report(
    idea_text: str = Form(..., description="笔记创作意图 / 思路"),
    images: List[UploadFile] = File(
        ..., description="多张图片，同一字段名 images 下上传多文件"
    ),
    request_id: str = Depends(get_request_id),
    _api_key: str = Depends(require_api_key),
) -> ApiResponse[XhsNoteReportResponse]:
    """生成小红书爆款笔记撰写报告。"""
    try:
        final_report, error = await generate_xhs_note_report(
            idea_text=idea_text,
            files=images,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("xhs_note_api_failed", error=str(exc), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="小红书笔记生成异常，请查询服务日志",
        ) from exc

    if error or final_report is None:
        return ApiResponse(
            code=1,
            message=f"小红书笔记生成失败: {error}",
            data=None,
            request_id=request_id,
        )

    response_payload = XhsNoteReportResponse(report=final_report)
    return ApiResponse(
        code=0,
        message="ok",
        data=response_payload,
        request_id=request_id,
    )

