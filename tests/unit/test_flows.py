"""流程编排（flows.py）的单元测试，使用 mock 模拟 Crew 执行。"""

from __future__ import annotations

import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from app.schemas.xhs_note import (
    XhsContentStrategyBrief,
    XhsCopywritingOutput,
    XhsImageEditBatchReport,
    XhsImageEditPlan,
    XhsImageVisualAnalysis,
    XhsNoteIdeaRequest,
    XhsSEOOptimizedNote,
    XhsVisualBatchReport,
)
from tests.conftest import (
    MockCrewResult,
    MockTaskOutput,
    make_idea_request,
    make_visual_analysis,
    make_edit_plan,
    make_strategy_brief,
    make_copywriting,
    make_seo_note,
    make_visual_batch,
    make_edit_batch,
)


# ---------------------------------------------------------------------------
# _generate_final_report
# ---------------------------------------------------------------------------


class TestGenerateFinalReport:
    def test_basic_report(self):
        from app.crews.xhs_note.flows import _generate_final_report
        idea = make_idea_request(2)
        edit_batch = make_edit_batch(2)
        seo_note = make_seo_note()
        report = _generate_final_report(idea, edit_batch, seo_note)
        assert isinstance(report, str)
        assert "地中海饮食" in report
        assert "img_0" in report
        assert "生成笔记标题" in report

    def test_report_contains_edit_plans(self):
        from app.crews.xhs_note.flows import _generate_final_report
        idea = make_idea_request(1)
        edit_batch = make_edit_batch(1)
        seo_note = make_seo_note()
        report = _generate_final_report(idea, edit_batch, seo_note)
        assert "编辑方案" in report or "edit" in report.lower()


# ---------------------------------------------------------------------------
# _handle_crew_error
# ---------------------------------------------------------------------------


class TestHandleCrewError:
    def test_logs_error(self):
        from app.crews.xhs_note.flows import _handle_crew_error
        exc = RuntimeError("test error")
        # Should not raise, just log
        _handle_crew_error(exc, ["test_agent"])


# ---------------------------------------------------------------------------
# _run_visual_analysis_phase (mocked Crew)
# ---------------------------------------------------------------------------


class TestRunVisualAnalysisPhase:
    @pytest.mark.asyncio
    async def test_empty_images(self):
        from app.crews.xhs_note.flows import _run_visual_analysis_phase
        idea = XhsNoteIdeaRequest(idea_text="test", images=[])
        visual_by_id, summary = await _run_visual_analysis_phase(idea)
        assert visual_by_id == {}
        assert summary == ""

    @pytest.mark.asyncio
    @patch("app.crews.xhs_note.flows.Crew")
    @patch("app.crews.xhs_note.flows.build_visual_analysis_summary_task")
    @patch("app.crews.xhs_note.flows.build_visual_analysis_task")
    @patch("app.crews.xhs_note.flows.get_xhs_visual_analyst")
    async def test_with_images(self, mock_agent, mock_build_task, mock_build_summary, mock_crew_cls):
        mock_agent.return_value = MagicMock()
        mock_build_task.return_value = MagicMock()
        mock_build_summary.return_value = MagicMock()

        visual = make_visual_analysis(0)
        crew_result = MockCrewResult([
            MockTaskOutput(pydantic=visual),
            MockTaskOutput(raw="视觉分析总结"),
        ])

        mock_crew_instance = MagicMock()
        mock_crew_instance.kickoff = MagicMock(return_value=crew_result)
        mock_crew_cls.return_value = mock_crew_instance

        from app.crews.xhs_note.flows import _run_visual_analysis_phase
        idea = make_idea_request(1)
        visual_by_id, summary = await _run_visual_analysis_phase(idea)
        assert "img_0" in visual_by_id
        assert summary == "视觉分析总结"


# ---------------------------------------------------------------------------
# _run_image_edit_phase (mocked Crew)
# ---------------------------------------------------------------------------


class TestRunImageEditPhase:
    @pytest.mark.asyncio
    async def test_no_visuals(self):
        from app.crews.xhs_note.flows import _run_image_edit_phase
        idea = make_idea_request(1)
        # 没有视觉分析结果，应跳过所有图片
        edit_by_id, summary = await _run_image_edit_phase(idea, {})
        assert edit_by_id == {}

    @pytest.mark.asyncio
    @patch("app.crews.xhs_note.flows.Crew")
    @patch("app.crews.xhs_note.flows.build_image_edit_plan_summary_task")
    @patch("app.crews.xhs_note.flows.build_image_edit_task")
    @patch("app.crews.xhs_note.flows.get_xhs_image_editor")
    async def test_with_visuals(self, mock_agent, mock_build_task, mock_build_summary, mock_crew_cls):
        mock_agent.return_value = MagicMock()
        mock_build_task.return_value = MagicMock()
        mock_build_summary.return_value = MagicMock()

        plan = make_edit_plan(0)
        crew_result = MockCrewResult([
            MockTaskOutput(pydantic=plan),
            MockTaskOutput(raw="编辑方案总结"),
        ])

        mock_crew_instance = MagicMock()
        mock_crew_instance.kickoff = MagicMock(return_value=crew_result)
        mock_crew_cls.return_value = mock_crew_instance

        from app.crews.xhs_note.flows import _run_image_edit_phase
        idea = make_idea_request(1)
        visual_by_id = {"img_0": make_visual_analysis(0)}
        edit_by_id, summary = await _run_image_edit_phase(idea, visual_by_id)
        assert "img_0" in edit_by_id


# ---------------------------------------------------------------------------
# _run_content_phase (mocked Crew)
# ---------------------------------------------------------------------------


class TestRunContentPhase:
    @pytest.mark.asyncio
    @patch("app.crews.xhs_note.flows.Crew")
    @patch("app.crews.xhs_note.flows.get_task_seo_optimization")
    @patch("app.crews.xhs_note.flows.get_task_copywriting")
    @patch("app.crews.xhs_note.flows.get_task_content_strategy")
    @patch("app.crews.xhs_note.flows.get_xhs_seo_expert")
    @patch("app.crews.xhs_note.flows.get_xhs_content_writer")
    @patch("app.crews.xhs_note.flows.get_xhs_growth_strategist")
    async def test_content_phase(
        self, mock_strategist, mock_writer, mock_seo,
        mock_task_strategy, mock_task_copy, mock_task_seo, mock_crew_cls
    ):
        for m in [mock_strategist, mock_writer, mock_seo]:
            m.return_value = MagicMock()
        for m in [mock_task_strategy, mock_task_copy, mock_task_seo]:
            m.return_value = MagicMock()

        strategy = make_strategy_brief()
        copywriting = make_copywriting()
        seo = make_seo_note()

        crew_result = MockCrewResult([
            MockTaskOutput(pydantic=strategy),
            MockTaskOutput(pydantic=copywriting),
            MockTaskOutput(pydantic=seo),
        ])

        mock_crew_instance = MagicMock()
        mock_crew_instance.kickoff = MagicMock(return_value=crew_result)
        mock_crew_cls.return_value = mock_crew_instance

        from app.crews.xhs_note.flows import _run_content_phase
        idea = make_idea_request(1)
        visual_batch = make_visual_batch(1)
        edit_batch = make_edit_batch(1)
        s, c, seo_out = await _run_content_phase(idea, visual_batch, edit_batch)
        assert isinstance(s, XhsContentStrategyBrief)
        assert isinstance(c, XhsCopywritingOutput)
        assert isinstance(seo_out, XhsSEOOptimizedNote)


# ---------------------------------------------------------------------------
# run_xhs_note_flow (end-to-end mocked)
# ---------------------------------------------------------------------------


class TestRunXhsNoteFlow:
    @pytest.mark.asyncio
    async def test_no_images(self):
        from app.crews.xhs_note.flows import run_xhs_note_flow
        idea = XhsNoteIdeaRequest(idea_text="test", images=[])
        report, error = await run_xhs_note_flow(idea)
        assert report is None
        assert "未上传" in error

    @pytest.mark.asyncio
    @patch("app.crews.xhs_note.flows._run_content_phase")
    @patch("app.crews.xhs_note.flows._run_image_edit_phase")
    @patch("app.crews.xhs_note.flows._run_visual_analysis_phase")
    async def test_full_flow(self, mock_visual, mock_edit, mock_content):
        visual = make_visual_analysis(0)
        plan = make_edit_plan(0)
        mock_visual.return_value = ({"img_0": visual}, "视觉总结")
        mock_edit.return_value = ({"img_0": plan}, "编辑总结")
        mock_content.return_value = (make_strategy_brief(), make_copywriting(), make_seo_note())

        from app.crews.xhs_note.flows import run_xhs_note_flow
        idea = make_idea_request(1)
        report, error = await run_xhs_note_flow(idea)
        assert error == ""
        assert report is not None
        assert "地中海" in report

    @pytest.mark.asyncio
    @patch("app.crews.xhs_note.flows._run_visual_analysis_phase")
    async def test_flow_exception(self, mock_visual):
        mock_visual.side_effect = RuntimeError("LLM 超时")

        from app.crews.xhs_note.flows import run_xhs_note_flow
        idea = make_idea_request(1)
        report, error = await run_xhs_note_flow(idea)
        assert report is None
        assert "失败" in error
