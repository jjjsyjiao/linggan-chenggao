"""小红书爆款笔记项目的 Task 定义与构造函数。

本模块作为「单一来源」维护所有 CrewAI Task 的结构，
供 `flows.py` 调用，避免在流程编排代码中重复手写 Task 定义。

Task描述统一从 `app/crews/config/tasks.yaml` 加载，支持变量替换。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

import yaml
from crewai import Task, Agent

from app.crews.xhs_note.agents import (
    get_xhs_content_writer,
    get_xhs_growth_strategist,
    get_xhs_image_editor,
    get_xhs_seo_expert,
    get_xhs_visual_analyst,
)
from app.schemas.xhs_note import (
    XhsContentStrategyBrief,
    XhsCopywritingOutput,
    XhsImageEditBatchReport,
    XhsImageEditPlan,
    XhsImageInput,
    XhsImageVisualAnalysis,
    XhsNoteIdeaRequest,
    XhsSEOOptimizedNote,
    XhsVisualBatchReport,
)

_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def _load_tasks_config() -> dict:
    """从 tasks.yaml 读取全部 Task 配置。"""
    try:
        with (_CONFIG_DIR / "tasks.yaml").open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as e:
        # YAML解析失败时记录错误但不中断程序
        from app.observability.logging import get_logger
        logger = get_logger(__name__)
        logger.error("tasks_yaml_load_failed", error=str(e))
        return {}


_TASKS_CFG = _load_tasks_config()

def _get_task_config(task_name: str) -> dict:
    """获取指定Task的配置。"""
    return _TASKS_CFG.get(task_name, {}) if isinstance(_TASKS_CFG, dict) else {}


def build_visual_analysis_task(image: XhsImageInput, idea_text: str) -> Task:
    """基于单张图片构建视觉分析 Task（每张图一个 Task，输出单图 XhsImageVisualAnalysis）。

    该函数负责把领域模型转换为 CrewAI 能理解的 Task 定义，文案模版统一来自 YAML 配置。
    """
    cfg = _get_task_config("task_visual_analysis")
    
    # 准备变量替换：这里只传入当前这张图片的信息
    images_json = json.dumps([{
        "image_id": image.image_id,
        "file_name": image.file_name,
    }], ensure_ascii=False, indent=2)
    
    # 使用YAML中的描述（仅 description），支持变量替换
    description_template = cfg.get("description")
    
    description = description_template.format(
        idea_text=idea_text,
        images_info=images_json,
    )
    
    expected_output = cfg.get("expected_output")

    return Task(
        description=description,
        expected_output=expected_output,
        agent=get_xhs_visual_analyst(image_path=image.local_path),
        output_pydantic=XhsImageVisualAnalysis,
        async_execution=True,  # 异步执行，避免阻塞主线程
    )

def build_visual_analysis_summary_task(context: List[Task]) -> Task:
    """基于多个视觉分析任务的结果构建视觉分析总结 Task。"""
    cfg = _get_task_config("task_visual_analysis_summary")
    return Task(
        description=cfg.get("description", ""),
        expected_output=cfg.get("expected_output", ""),
        agent=get_xhs_visual_analyst(),
        context=context,
        async_execution=False,
    )

def build_image_edit_task(
    idea_text: str,
    image: XhsImageInput,
    visual: XhsImageVisualAnalysis,
) -> Task:
    """基于单张图片及其视觉分析结果构建编辑方案 Task。

    注意：这里的入参顺序与 `flows.py` 中的调用保持严格一致：
    (idea_text, image, visual)，避免因位置参数错乱导致描述模板替换错误。
    """
    # 从YAML加载配置
    cfg = _get_task_config("task_image_edit_plan")
    images_info = json.dumps([{
        "image_id": image.image_id,
        "file_name": image.file_name,
    }], ensure_ascii=False, indent=2)
    visual_analysis_info = visual.model_dump_json(indent=2)
    # 使用YAML中的描述模板
    description_template = cfg.get("description")
    
    description = description_template.format(
        idea_text=idea_text,
        images_info=images_info,
        visual_analysis=visual_analysis_info
    )
    
    expected_output = cfg.get("expected_output")

    return Task(
        description=description,
        expected_output=expected_output,
        agent=get_xhs_image_editor(image_path=image.local_path),
        output_pydantic=XhsImageEditPlan,
        async_execution=True,  # 异步执行，避免阻塞主线程
    )

def build_image_edit_plan_summary_task(context: List[Task]) -> Task:
    """基于多个图片编辑方案任务的结果构建图片编辑方案总结 Task。"""
    cfg = _get_task_config("task_image_edit_plan_summary")
    return Task(
        description=cfg.get("description", ""),
        expected_output=cfg.get("expected_output", ""),
        agent=get_xhs_image_editor(),
        context=context,
        async_execution=False,
    )


def get_task_content_strategy() -> Task:
    """从 YAML 配置构建内容策略 Task，每次调用返回新实例。"""
    cfg = _get_task_config("task_content_strategy")
    return Task(
        description=cfg.get("description", ""),
        expected_output=cfg.get("expected_output", ""),
        agent=get_xhs_growth_strategist(),  # YAML 中配置的 agent: xhs_growth_strategist
        output_pydantic=XhsContentStrategyBrief,
        async_execution=False,
    )


def get_task_copywriting(content_strategy_task: Task) -> Task:
    """基于内容策略 Task 构建文案撰写 Task，每次调用返回新实例。"""
    cfg = _get_task_config("task_copywriting")
    return Task(
        description=cfg.get("description", ""),
        expected_output=cfg.get("expected_output", ""),
        agent=get_xhs_content_writer(),  # YAML 中配置的 agent: xhs_content_writer
        context=[content_strategy_task],  # 依赖上游内容策略任务
        output_pydantic=XhsCopywritingOutput,
        async_execution=False,
    )


def get_task_seo_optimization(
    content_strategy_task: Task,
    copywriting_task: Task,
) -> Task:
    """基于内容策略和文案撰写 Task 构建 SEO 优化 Task，每次调用返回新实例。"""
    cfg = _get_task_config("task_seo_optimization")
    return Task(
        description=cfg.get("description", ""),
        expected_output=cfg.get("expected_output", ""),
        agent=get_xhs_seo_expert(),  # YAML 中配置的 agent: xhs_seo_expert
        context=[content_strategy_task, copywriting_task],  # 依赖上游两个任务
        output_pydantic=XhsSEOOptimizedNote,
        async_execution=False,
    )
