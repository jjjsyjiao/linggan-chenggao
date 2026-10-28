"""小红书爆款笔记项目的 Agent 定义。

Agent 的角色文案（role/goal/backstory 等）配置在 `app/crews/config/agents.yaml` 中，
本模块只负责两类“结构化信息”：
- 绑定使用的 LLM（如 qwen3-max-2026-01-23、qwen3-vl-plus）
- 绑定 tools（如 IntermediateTool）与 output_pydantic、多模态标记等

即：**除了 llm 和 tools（以及结构化输出模型、多模态开关），其余全部走 config。**
"""

from __future__ import annotations

from pathlib import Path

import yaml
from crewai import Agent

from app.crews.llm import get_llm
from app.crews.tools import IntermediateTool, AddImageToolLocal
from app.schemas.xhs_note import (
    XhsContentStrategyBrief,
    XhsCopywritingOutput,
    XhsImageEditPlan,
    XhsImageVisualAnalysis,
    XhsSEOOptimizedNote,
)


_INTERMEDIATE_TOOLS = [IntermediateTool()]

_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def _load_agents_config() -> dict:
    """从 agents.yaml 读取全部 Agent 文案与通用配置。"""
    try:
        with (_CONFIG_DIR / "agents.yaml").open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}


_AGENTS_CFG = _load_agents_config()


def _agent_cfg(name: str) -> dict:
    config = dict(_AGENTS_CFG.get(name, {})) if isinstance(_AGENTS_CFG, dict) else {}
    if config:
        config.update(verbose=False, max_iter=8, max_retry_limit=0)
        config["backstory"] = config.get("backstory", "") + (
            "\n【优先事实边界】只根据图片可见内容与用户明确提供的信息工作。"
            "不得把营销、增长或互动目标变成虚构事实；不得编造亲身经历、减重效果、消费价格、店名地址、"
            "赠品抽奖、优惠承诺或未经提供的活动。不能仅凭照片推定食材重量、用油克数、热量、营养含量等定量健康建议。"
            "互动引导仅可邀请分享感受或提出问题，不得承诺奖品、优惠或功效。信息不足时使用中性表达。"
            "没有用户体验资料时只使用观察或计划口吻，不得写已吃过、亲测、手作等制作方式、味道口感、香气或饱腹时长。"
            "不得编造3-2-1等饮食配比公式，不得暗示吃某盘餐就会瘦或不用计算饮食即可减脂。"
            "不能从照片确认制作方式、具体配方、酱料成分或身体瘦身机理。"
            "不确定的视觉推断必须保留不确定性：绿色酱汁不能直接断言罗勒橄榄油配方，无法确认的食材称为块状配菜或谷物。"
        )
    return config


# 多模态视觉分析 Agent：除 llm/tools/multimodal 外全部走 config
def get_xhs_visual_analyst(*, image_path: str | None = None) -> Agent:
    """每次调用创建一个新的视觉分析 Agent 实例。"""
    cfg_visual = _agent_cfg("xhs_visual_analyst")
    return Agent(
        config=cfg_visual,
        # 图片由 LLM 适配器强制附加，避免 CrewAI 自动注入可被模型跳过的图片工具。
        multimodal=False,
        llm=get_llm(image_paths=[image_path] if image_path else []),
        tools=[],
    )


# 多模态图片编辑 / P 图方案 Agent
def get_xhs_image_editor(*, image_path: str | None = None) -> Agent:
    """每次调用创建一个新的图片编辑 Agent 实例。"""
    cfg_editor = _agent_cfg("xhs_image_editor")
    return Agent(
        config=cfg_editor,
        multimodal=False,
        llm=get_llm(image_paths=[image_path] if image_path else []),
        tools=[],
    )


def get_xhs_growth_strategist() -> Agent:
    """每次调用创建一个新的增长策略 Agent 实例。"""
    cfg_growth = _agent_cfg("xhs_growth_strategist")
    return Agent(
        config=cfg_growth,
        tools=[IntermediateTool()],
        llm=get_llm(),
    )


def get_xhs_content_writer() -> Agent:
    """每次调用创建一个新的内容撰写 Agent 实例。"""
    cfg_writer = _agent_cfg("xhs_content_writer")
    return Agent(
        config=cfg_writer,
        tools=[IntermediateTool()],
        llm=get_llm(),
    )


def get_xhs_seo_expert() -> Agent:
    """每次调用创建一个新的 SEO 优化 Agent 实例。"""
    cfg_seo = _agent_cfg("xhs_seo_expert")
    return Agent(
        config=cfg_seo,
        tools=[IntermediateTool()],
        llm=get_llm(),
    )

