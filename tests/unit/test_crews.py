"""Agent 和 Task 工厂方法的单元测试。"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from app.schemas.xhs_note import (
    XhsContentStrategyBrief,
    XhsCopywritingOutput,
    XhsImageEditPlan,
    XhsImageVisualAnalysis,
    XhsSEOOptimizedNote,
)


# ---------------------------------------------------------------------------
# Agent 工厂方法测试
# ---------------------------------------------------------------------------


class TestAgentFactories:
    """测试每个 get_xhs_* Agent 工厂方法。

    由于 CrewAI Agent 是 Pydantic 模型，不接受 MagicMock 作为 llm，
    因此需要同时 mock Agent 构造函数本身。
    """

    @patch("app.crews.xhs_note.agents.Agent")
    @patch("app.crews.xhs_note.agents.get_llm")
    def test_get_xhs_visual_analyst(self, mock_get_llm, mock_agent_cls):
        mock_get_llm.return_value = MagicMock()
        mock_agent_cls.return_value = MagicMock(multimodal=True)
        from app.crews.xhs_note.agents import get_xhs_visual_analyst
        agent = get_xhs_visual_analyst()
        assert agent is not None
        mock_agent_cls.assert_called_once()
        call_kwargs = mock_agent_cls.call_args[1]
        assert call_kwargs["multimodal"] is False

    @patch("app.crews.xhs_note.agents.Agent")
    @patch("app.crews.xhs_note.agents.get_llm")
    def test_get_xhs_image_editor(self, mock_get_llm, mock_agent_cls):
        mock_get_llm.return_value = MagicMock()
        mock_agent_cls.return_value = MagicMock(multimodal=True)
        from app.crews.xhs_note.agents import get_xhs_image_editor
        agent = get_xhs_image_editor()
        assert agent is not None
        call_kwargs = mock_agent_cls.call_args[1]
        assert call_kwargs["multimodal"] is False

    @patch("app.crews.xhs_note.agents.Agent")
    @patch("app.crews.xhs_note.agents.get_llm")
    def test_get_xhs_growth_strategist(self, mock_get_llm, mock_agent_cls):
        mock_get_llm.return_value = MagicMock()
        mock_agent_cls.return_value = MagicMock()
        from app.crews.xhs_note.agents import get_xhs_growth_strategist
        agent = get_xhs_growth_strategist()
        assert agent is not None
        mock_agent_cls.assert_called_once()

    @patch("app.crews.xhs_note.agents.Agent")
    @patch("app.crews.xhs_note.agents.get_llm")
    def test_get_xhs_content_writer(self, mock_get_llm, mock_agent_cls):
        mock_get_llm.return_value = MagicMock()
        mock_agent_cls.return_value = MagicMock()
        from app.crews.xhs_note.agents import get_xhs_content_writer
        agent = get_xhs_content_writer()
        assert agent is not None

    @patch("app.crews.xhs_note.agents.Agent")
    @patch("app.crews.xhs_note.agents.get_llm")
    def test_get_xhs_seo_expert(self, mock_get_llm, mock_agent_cls):
        mock_get_llm.return_value = MagicMock()
        mock_agent_cls.return_value = MagicMock()
        from app.crews.xhs_note.agents import get_xhs_seo_expert
        agent = get_xhs_seo_expert()
        assert agent is not None

    @patch("app.crews.xhs_note.agents.Agent")
    @patch("app.crews.xhs_note.agents.get_llm")
    def test_agents_are_new_instances(self, mock_get_llm, mock_agent_cls):
        """每次调用应返回新实例，不应为单例。"""
        mock_get_llm.return_value = MagicMock()
        mock_agent_cls.side_effect = [MagicMock(), MagicMock()]
        from app.crews.xhs_note.agents import get_xhs_visual_analyst
        a1 = get_xhs_visual_analyst()
        a2 = get_xhs_visual_analyst()
        assert a1 is not a2


class TestAgentConfig:
    """测试 Agent 配置加载。"""

    def test_load_agents_config(self):
        from app.crews.xhs_note.agents import _load_agents_config
        cfg = _load_agents_config()
        assert isinstance(cfg, dict)
        # YAML 中应有 5 个 Agent 配置
        assert "xhs_visual_analyst" in cfg
        assert "xhs_image_editor" in cfg
        assert "xhs_growth_strategist" in cfg
        assert "xhs_content_writer" in cfg
        assert "xhs_seo_expert" in cfg

    def test_agent_cfg_has_role(self):
        from app.crews.xhs_note.agents import _agent_cfg
        cfg = _agent_cfg("xhs_visual_analyst")
        assert "role" in cfg
        assert "goal" in cfg
        assert "backstory" in cfg

    def test_agent_cfg_nonexistent(self):
        from app.crews.xhs_note.agents import _agent_cfg
        cfg = _agent_cfg("nonexistent_agent")
        assert cfg == {}


# ---------------------------------------------------------------------------
# Task 工厂方法测试
# ---------------------------------------------------------------------------


class TestTaskConfig:
    """测试 Task 配置加载。"""

    def test_load_tasks_config(self):
        from app.crews.xhs_note.tasks import _load_tasks_config
        cfg = _load_tasks_config()
        assert isinstance(cfg, dict)
        assert "task_visual_analysis" in cfg
        assert "task_image_edit_plan" in cfg
        assert "task_content_strategy" in cfg
        assert "task_copywriting" in cfg
        assert "task_seo_optimization" in cfg

    def test_get_task_config(self):
        from app.crews.xhs_note.tasks import _get_task_config
        cfg = _get_task_config("task_visual_analysis")
        assert "description" in cfg
        assert "expected_output" in cfg

    def test_get_task_config_nonexistent(self):
        from app.crews.xhs_note.tasks import _get_task_config
        cfg = _get_task_config("nonexistent_task")
        assert cfg == {}


class TestTaskFactories:
    """测试 Task 工厂函数。

    CrewAI Task 是 Pydantic 模型，不接受 MagicMock 作为 agent 或 context，
    因此需要 mock Task 构造函数本身。
    """

    @patch("app.crews.xhs_note.tasks.Task")
    @patch("app.crews.xhs_note.tasks.get_xhs_visual_analyst")
    def test_build_visual_analysis_task(self, mock_agent, mock_task_cls):
        mock_agent.return_value = MagicMock()
        mock_task_cls.return_value = MagicMock()
        from app.crews.xhs_note.tasks import build_visual_analysis_task
        from tests.conftest import make_image_input
        task = build_visual_analysis_task(make_image_input(0), "测试意图")
        assert task is not None
        mock_task_cls.assert_called_once()
        call_kwargs = mock_task_cls.call_args[1]
        assert call_kwargs["output_pydantic"] == XhsImageVisualAnalysis
        assert call_kwargs["async_execution"] is True

    @patch("app.crews.xhs_note.tasks.Task")
    @patch("app.crews.xhs_note.tasks.get_xhs_visual_analyst")
    def test_build_visual_analysis_summary_task(self, mock_agent, mock_task_cls):
        mock_agent.return_value = MagicMock()
        mock_task_cls.return_value = MagicMock()
        from app.crews.xhs_note.tasks import build_visual_analysis_summary_task
        mock_tasks = [MagicMock(), MagicMock()]
        task = build_visual_analysis_summary_task(mock_tasks)
        assert task is not None
        call_kwargs = mock_task_cls.call_args[1]
        assert call_kwargs["async_execution"] is False

    @patch("app.crews.xhs_note.tasks.Task")
    @patch("app.crews.xhs_note.tasks.get_xhs_image_editor")
    def test_build_image_edit_task(self, mock_agent, mock_task_cls):
        mock_agent.return_value = MagicMock()
        mock_task_cls.return_value = MagicMock()
        from app.crews.xhs_note.tasks import build_image_edit_task
        from tests.conftest import make_image_input, make_visual_analysis
        task = build_image_edit_task("测试意图", make_image_input(0), make_visual_analysis(0))
        assert task is not None
        call_kwargs = mock_task_cls.call_args[1]
        assert call_kwargs["output_pydantic"] == XhsImageEditPlan

    @patch("app.crews.xhs_note.tasks.Task")
    @patch("app.crews.xhs_note.tasks.get_xhs_image_editor")
    def test_build_image_edit_plan_summary_task(self, mock_agent, mock_task_cls):
        mock_agent.return_value = MagicMock()
        mock_task_cls.return_value = MagicMock()
        from app.crews.xhs_note.tasks import build_image_edit_plan_summary_task
        task = build_image_edit_plan_summary_task([MagicMock()])
        assert task is not None

    @patch("app.crews.xhs_note.tasks.Task")
    @patch("app.crews.xhs_note.tasks.get_xhs_growth_strategist")
    def test_get_task_content_strategy(self, mock_agent, mock_task_cls):
        mock_agent.return_value = MagicMock()
        mock_task_cls.return_value = MagicMock()
        from app.crews.xhs_note.tasks import get_task_content_strategy
        task = get_task_content_strategy()
        assert task is not None
        call_kwargs = mock_task_cls.call_args[1]
        assert call_kwargs["output_pydantic"] == XhsContentStrategyBrief

    @patch("app.crews.xhs_note.tasks.Task")
    @patch("app.crews.xhs_note.tasks.get_xhs_content_writer")
    def test_get_task_copywriting(self, mock_agent, mock_task_cls):
        mock_agent.return_value = MagicMock()
        mock_task_cls.return_value = MagicMock()
        from app.crews.xhs_note.tasks import get_task_copywriting
        mock_strategy_task = MagicMock()
        task = get_task_copywriting(mock_strategy_task)
        assert task is not None
        call_kwargs = mock_task_cls.call_args[1]
        assert call_kwargs["output_pydantic"] == XhsCopywritingOutput
        assert mock_strategy_task in call_kwargs["context"]

    @patch("app.crews.xhs_note.tasks.Task")
    @patch("app.crews.xhs_note.tasks.get_xhs_seo_expert")
    def test_get_task_seo_optimization(self, mock_agent, mock_task_cls):
        mock_agent.return_value = MagicMock()
        mock_task_cls.return_value = MagicMock()
        from app.crews.xhs_note.tasks import get_task_seo_optimization
        mock_strategy = MagicMock()
        mock_copywriting = MagicMock()
        task = get_task_seo_optimization(mock_strategy, mock_copywriting)
        assert task is not None
        call_kwargs = mock_task_cls.call_args[1]
        assert call_kwargs["output_pydantic"] == XhsSEOOptimizedNote
        assert mock_strategy in call_kwargs["context"]
        assert mock_copywriting in call_kwargs["context"]

    @patch("app.crews.xhs_note.tasks.Task")
    @patch("app.crews.xhs_note.tasks.get_xhs_growth_strategist")
    def test_task_instances_are_new(self, mock_agent, mock_task_cls):
        mock_agent.return_value = MagicMock()
        mock_task_cls.side_effect = [MagicMock(), MagicMock()]
        from app.crews.xhs_note.tasks import get_task_content_strategy
        t1 = get_task_content_strategy()
        t2 = get_task_content_strategy()
        assert t1 is not t2


def test_final_writing_prompts_limit_length_and_avoid_fabricated_facts():
    from app.crews.xhs_note.tasks import _load_tasks_config
    config=_load_tasks_config()
    for name in ["task_copywriting","task_seo_optimization"]:
        text=config[name]["description"]
        assert "20" in text
        for required in ["减重数字","消费价格","店名","地址","亲历效果","图片可见内容","中性表达","赠品抽奖","优惠承诺","健康定量建议"]:
            assert required in text


def test_growth_strategy_does_not_invent_promotions_or_nutrition():
    from app.crews.xhs_note.agents import _agent_cfg
    from app.crews.xhs_note.tasks import _load_tasks_config
    for text in [_agent_cfg("xhs_growth_strategist")["backstory"],_load_tasks_config()["task_content_strategy"]["description"]]:
        for boundary in ["赠品抽奖","优惠承诺","中性表达"]:
            assert boundary in text


def test_food_copy_does_not_invent_taste_satiety_or_diet_formula():
    from app.crews.xhs_note.agents import _agent_cfg
    from app.crews.xhs_note.tasks import _load_tasks_config
    assert "饱腹" in _agent_cfg("xhs_growth_strategist")["backstory"]
    for name in ["task_content_strategy","task_copywriting","task_seo_optimization"]:
        text=_load_tasks_config()[name]["description"]
        for boundary in ["观察或计划","味觉","饱腹","3-2-1","视觉推测"]:
            assert boundary in text
