"""小红书爆款笔记项目的流程编排。

提供对外函数 run_xhs_note_flow，接收领域请求模型并返回最终报告。

对比原始实现：
- 之前：使用一个 Crew，内部是“批处理” Task（一次性处理全部图片），按顺序执行；
- 现在：按照图片拆分为多个异步任务：
  1）每张图片一个视觉分析 Task，并发执行；
  2）在拿到视觉分析结果后，每张图片一个编辑方案 Task，并发执行；
  3）将所有图片的分析与编辑方案汇总，再顺序执行内容策划、内容撰写、搜索优化，生成最终报告。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Dict, List, Tuple

from crewai import Agent, Crew, Process, Task

# 官方 Process 仅支持 sequential / hierarchical，见 https://docs.crewai.com/en/concepts/processes
# 多图任务在同一 Crew 内用 sequential 按顺序执行（无 concurrent 选项）
from app.crews.xhs_note.agents import (
    get_xhs_content_writer,
    get_xhs_growth_strategist,
    get_xhs_image_editor,
    get_xhs_seo_expert,
    get_xhs_visual_analyst,
)
from app.crews.xhs_note.tasks import (
    build_visual_analysis_task,
    build_visual_analysis_summary_task,
    build_image_edit_task,
    build_image_edit_plan_summary_task,
    get_task_content_strategy,
    get_task_copywriting,
    get_task_seo_optimization,
)
from app.core.config import get_settings
from app.observability.logging import get_crew_log_file_path, get_logger
from app.observability.metrics import (
    ai_agent_error_total,
    crew_execution_seconds,
)
from app.schemas.xhs_note import (
    XhsContentStrategyBrief,
    XhsCopywritingOutput,
    XhsImageEditBatchReport,
    XhsImageEditPlan,
    XhsImageVisualAnalysis,
    XhsNoteIdeaRequest,
    XhsSEOOptimizedNote,
    XhsVisualBatchReport,
    XhsGeneratedNote,
)


logger = get_logger(__name__)

def _generate_final_report(idea_request: XhsNoteIdeaRequest, edit_batch: XhsImageEditBatchReport, xhsSEOOptimizedNote: XhsSEOOptimizedNote) -> str:
    """生成最终报告。"""
    report = ""
    report += f"原始创作意图: {idea_request.idea_text}\n"
    report += f"生成笔记标题: {xhsSEOOptimizedNote.optimized_title}\n"
    report += f"生成笔记正文: {xhsSEOOptimizedNote.optimized_content}\n"
    report += f"生成笔记图片顺序: {xhsSEOOptimizedNote.optimized_picture_order}\n"
    report += f"生成笔记标签: {xhsSEOOptimizedNote.tags}\n"
    report += "生成笔记图片编辑方案: \n"
    for img in edit_batch.images_edit_plan:
        report += f"图片ID: {img.image_id}\n"
        report += f"图片编辑方案: {img.overall_edit_strategy}\n"
        report += f"图片剪裁建议: {img.crop_suggestion}\n"
        report += f"图片亮度/对比度/饱和度调整建议: {img.light_color_adjustment}\n"
        report += f"图片滤镜建议: {img.filter_suggestion}\n"
        report += f"图片文字建议: {img.text_overlay_suggestion}\n"
        report += f"图片美颜建议: {img.beauty_adjustment_suggestion}\n"
        report += f"图片是否建议作为首图: {img.is_recommended_as_cover}\n"
        report += f"图片需要规避的审美风险/平台审核风险: {img.risk_and_pitfall_notes}\n"
    return report

def _handle_crew_error(exc: Exception, agent_roles: list[str]) -> None:
    """统一处理Crew执行错误：记录指标和日志。
    
    Args:
        exc: 捕获的异常
        agent_roles: 相关的Agent角色列表，用于记录指标
    """
    error_type = type(exc).__name__
    for role in agent_roles:
        ai_agent_error_total.labels(agent_role=role, error_type=error_type).inc()
    logger.exception("crew_execution_failed", agent_roles=agent_roles, error=str(exc))

def _get_tasks_agents(tasks: List[Task]) -> List[Agent]:
    """获取任务的Agent列表。"""
    agents = []
    for task in tasks:
        agents.append(task.agent)
    return agents

# ============================================================================
# Step 1：为每张图片创建「视觉分析」任务（并发执行）
# ============================================================================


async def _run_visual_analysis_phase(
    idea_request: XhsNoteIdeaRequest,
) -> Tuple[Dict[str, XhsImageVisualAnalysis], str]:
    """并发执行所有图片的视觉分析，返回按 image_id 索引的结果字典。"""
    if not idea_request.images:
        return {}, ""
    phase_started = time.perf_counter()

    tasks: List[Task] = []
    # 为每张图片构建一个独立的视觉分析 Task，实现“多图并发分析”
    for img in idea_request.images:
        tasks.append(build_visual_analysis_task(img, idea_request.idea_text))
    if not tasks:
        return {}, ""
    summary_task = build_visual_analysis_summary_task(tasks)
    tasks.append(summary_task)
    agents = _get_tasks_agents(tasks)


    # 单个 Crew 内部仍然是 sequential，但外层通过 async_execution=True + akickoff
    # 来实现整体上的并发 IO 调度
    crew = Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=False,
        
    )

    try:
        
        settings = get_settings()
        timeout = settings.crew_execution_timeout

        # 使用 asyncio.wait_for 为 Crew 执行增加超时控制，避免任务“卡死”
        result = await asyncio.wait_for(asyncio.to_thread(crew.kickoff), timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        _handle_crew_error(exc, ["xhs_visual_analyst"])
        raise

    # 将结果按 image_id 索引，方便后续阶段快速关联
    visual_by_id: Dict[str, XhsImageVisualAnalysis] = {}
    tasks_output = getattr(result, "tasks_output", []) or []
    
    # 提取每张图片的视觉分析结果（跳过最后一个 summary task）
    for task_output in tasks_output[:-1] if len(tasks_output) > 1 else tasks_output:
        visual = getattr(task_output, "pydantic", None)
        if isinstance(visual, XhsImageVisualAnalysis):
            visual_by_id[visual.image_id] = visual
    
    # summary task 是最后一个任务，提取其输出字符串
    visual_summary = ""
    if tasks_output:
        # summary task 的输出在最后一个 task_output 中
        summary_output = tasks_output[-1]
        # TaskOutput 的 raw 属性包含原始字符串输出
        visual_summary = getattr(summary_output, "raw", "") or ""
        if not isinstance(visual_summary, str):
            # 如果不是字符串，尝试转换为字符串
            visual_summary = str(visual_summary)

    logger.info(
        "xhs_note_visual_phase_done",
        image_count=len(idea_request.images),
        duration_seconds=round(time.perf_counter() - phase_started, 3),
        visual_result=visual_by_id,
    )
    return visual_by_id, visual_summary


# ============================================================================
# Step 2：为每张图片创建「编辑方案」任务（并发执行）
# ============================================================================


async def _run_image_edit_phase(
    idea_request: XhsNoteIdeaRequest,
    visual_by_id: Dict[str, XhsImageVisualAnalysis],
) -> Tuple[Dict[str, XhsImageEditPlan], str]:
    """并发执行所有图片的编辑方案任务，返回按 image_id 索引的结果字典。"""
    phase_started = time.perf_counter()
    tasks: List[Task] = []
    # 仅为“视觉分析已成功”的图片创建编辑方案任务
    for img in idea_request.images:
        visual = visual_by_id.get(img.image_id)
        if not visual:
            continue
        # 这里需要携带用户意图 + 图片基础信息 + 视觉分析结果
        tasks.append(build_image_edit_task(idea_request.idea_text, img, visual))

    if not tasks:
        return {}, ""
    
    summary_task = build_image_edit_plan_summary_task(tasks)
    tasks.append(summary_task)

    crew = Crew(
        agents=_get_tasks_agents(tasks),
        tasks=tasks,
        process=Process.sequential,
        verbose=False,
        
    )

    try:
        # 添加超时控制，防止图片编辑方案阶段长时间阻塞
        settings = get_settings()
        timeout = settings.crew_execution_timeout

        result = await asyncio.wait_for(asyncio.to_thread(crew.kickoff), timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        _handle_crew_error(exc, ["xhs_image_editor"])
        raise

    # 将编辑方案结果按 image_id 索引
    edit_by_id: Dict[str, XhsImageEditPlan] = {}
    tasks_output = getattr(result, "tasks_output", []) or []
    
    # 提取每张图片的编辑方案结果（跳过最后一个 summary task）
    for task_output in tasks_output[:-1] if len(tasks_output) > 1 else tasks_output:
        plan = getattr(task_output, "pydantic", None)
        if isinstance(plan, XhsImageEditPlan):
            edit_by_id[plan.image_id] = plan
    
    # summary task 是最后一个任务，提取其输出字符串
    edit_summary = ""
    if tasks_output:
        # summary task 的输出在最后一个 task_output 中
        summary_output = tasks_output[-1]
        # TaskOutput 的 raw 属性包含原始字符串输出
        edit_summary = getattr(summary_output, "raw", "") or ""
        if not isinstance(edit_summary, str):
            # 如果不是字符串，尝试转换为字符串
            edit_summary = str(edit_summary)

    logger.info(
        "xhs_note_edit_phase_done",
        image_count=len(idea_request.images),
        duration_seconds=round(time.perf_counter() - phase_started, 3),
        edit_result=edit_by_id,
    )
    return edit_by_id, edit_summary


# ============================================================================
# Step 3：基于图片分析与编辑方案，顺序执行：内容策略 -> 文案 -> SEO
# ============================================================================


async def _run_content_phase(
    idea_request: XhsNoteIdeaRequest,
    visual_batch: XhsVisualBatchReport,
    edit_batch: XhsImageEditBatchReport,
) -> Tuple[XhsContentStrategyBrief, XhsCopywritingOutput, XhsSEOOptimizedNote]:
    """顺序执行内容策划、文案撰写、搜索优化三个任务，并返回三类结构化中间结果。"""

    phase_started = time.perf_counter()
    content_strategy_task = get_task_content_strategy()
    copywriting_task = get_task_copywriting(content_strategy_task)
    seo_task = get_task_seo_optimization(content_strategy_task, copywriting_task)

    crew = Crew(
        agents=_get_tasks_agents([content_strategy_task, copywriting_task, seo_task]),
        tasks=[content_strategy_task, copywriting_task, seo_task],
        process=Process.sequential,
        verbose=False,
        
    )

    try:
        settings = get_settings()
        timeout = settings.crew_execution_timeout

        # 下游内容相关任务依赖上游图像阶段的聚合报告，这里通过 inputs 传入 JSON 字符串
        result = await asyncio.wait_for(
            asyncio.to_thread(crew.kickoff,
                inputs={
                    "idea_text": idea_request.idea_text,
                    "visual_report": visual_batch.model_dump_json(indent=2),
                    "edit_report": edit_batch.model_dump_json(indent=2),
                }
            ),
            timeout=timeout,
        )

        # 约定 tasks_output 顺序分别为：内容策略、原始文案、SEO 优化
        strategy_brief: XhsContentStrategyBrief = result.tasks_output[0].pydantic
        copywriting: XhsCopywritingOutput = result.tasks_output[1].pydantic
        seo_note: XhsSEOOptimizedNote = result.tasks_output[2].pydantic

        logger.info("xhs_note_content_phase_done", duration_seconds=round(time.perf_counter() - phase_started, 3))
        return strategy_brief, copywriting, seo_note
    except Exception as exc:  # noqa: BLE001
        _handle_crew_error(
            exc,
            ["xhs_growth_strategist", "xhs_content_writer", "xhs_seo_expert"]
        )
        raise



# ============================================================================
# 对外入口：run_xhs_note_flow
# ============================================================================


async def run_xhs_note_generation_flow(
    idea_request: XhsNoteIdeaRequest,
) -> Tuple[XhsGeneratedNote | None, str]:
    """执行小红书爆款笔记多 Agent 流程（按图片异步 + 下游串行）。
    
    Returns:
        (final_report, error_message): 成功时返回 (report, "")，失败时返回 (None, error_msg)
    """
    flow_name = "xhs_note_flow"
    start_time = time.perf_counter()
    
    logger.info(
        "xhs_note_flow_start",
        idea_text=idea_request.idea_text[:100],
        image_count=len(idea_request.images),
    )

    if not idea_request.images:
        return None, "本次请求未上传任何图片"

    try:
        # Step 1：全部图片视觉分析（并发）
        visual_by_id, visual_summary = await _run_visual_analysis_phase(idea_request)
        if set(visual_by_id) != {image.image_id for image in idea_request.images}:
            raise ValueError("图片视觉分析结果不完整，请重试")

        # Step 2：全部图片编辑方案（并发）
        edit_by_id, edit_summary = await _run_image_edit_phase(idea_request, visual_by_id)
        if set(edit_by_id) != set(visual_by_id):
            raise ValueError("图片编辑方案结果不完整，请重试")

        # 将逐图结果汇总为批次报告 + 每图完整信息
        images_visual: List[XhsImageVisualAnalysis] = []
        images_edit_plan: List[XhsImageEditPlan] = []

        for img in idea_request.images:
            visual = visual_by_id.get(img.image_id)
            plan = edit_by_id.get(img.image_id)
            if not (visual and plan):
                continue
            images_visual.append(visual)
            images_edit_plan.append(plan)
            

        visual_batch = XhsVisualBatchReport(
            user_raw_intent=idea_request.idea_text,
            images_visual=images_visual,
            summary=visual_summary,
        )

        edit_batch = XhsImageEditBatchReport(
            images_edit_plan=images_edit_plan,
            summary=edit_summary,
        )

        # Step 3：内容策划 -> 文案撰写 -> 搜索优化（顺序执行）
        strategy_brief, copywriting, seo_note = await _run_content_phase(
            idea_request,
            visual_batch,
            edit_batch,
        )

        # 将结构化中间结果组装为最终字符串报告
        final_report = _generate_final_report(idea_request, edit_batch, seo_note)
        expected_ids = [image.image_id for image in idea_request.images]
        # 模型偶尔会漏图、重复或编造 ID。保留有效建议顺序，再追加遗漏图片。
        order = list(dict.fromkeys(
            image_id for image_id in seo_note.optimized_picture_order if image_id in expected_ids
        ))
        order.extend(image_id for image_id in expected_ids if image_id not in order)
        note = XhsGeneratedNote(
            title=seo_note.optimized_title.strip(),
            content=seo_note.optimized_content.strip(),
            tags=list(dict.fromkeys(tag.strip().lstrip("#") for tag in seo_note.tags if tag.strip().lstrip("#"))),
            image_order=order,
            report=final_report,
        )

        # 记录成功执行的耗时
        duration = time.perf_counter() - start_time
        crew_execution_seconds.labels(flow_name=flow_name).observe(duration)

        logger.info(
            "xhs_note_flow_success",
            image_count=len(images_edit_plan),
            duration_seconds=round(duration, 2),
        )
        return note, ""

    except Exception as exc:  # noqa: BLE001
        # 记录失败执行的耗时
        duration = time.perf_counter() - start_time
        crew_execution_seconds.labels(flow_name=flow_name).observe(duration)
        
        error_msg = "流程执行超时，请减少图片数量后重试" if isinstance(exc, TimeoutError) else "流程执行失败，请检查模型配置、网络或服务日志"
        logger.exception("xhs_note_flow_failed", error=error_msg, duration_seconds=round(duration, 2))
        return None, error_msg


async def run_xhs_note_flow(idea_request: XhsNoteIdeaRequest) -> Tuple[str | None, str]:
    """保留旧报告接口，结构化输出由同一流程生成。"""
    note, error = await run_xhs_note_generation_flow(idea_request)
    return note.report if note else None, error

