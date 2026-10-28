"""小红书爆款笔记多 Agent 项目相关的 Pydantic 数据模型。"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class XhsImageInput(BaseModel):
    """服务端解析表单上传图片后生成的内部表示。"""

    image_id: str = Field(..., description="服务端为每张上传图片分配的唯一标识，如 img_0。")
    file_name: str = Field(..., description="原始文件名。")
    local_path: str = Field(
        ..., description="本次请求内该图片的临时落盘路径，供多模态 Agent 读取。"
    )


class XhsNoteIdeaRequest(BaseModel):
    """从表单解析后进入业务层 / 流程编排层的领域请求模型。"""

    idea_text: str = Field(..., description="用户对笔记创作的自然语言描述 / 思路。")
    images: List[XhsImageInput] = Field(
        ..., description="本次上传参与分析与编辑的图片列表。"
    )


class XhsImageVisualAnalysis(BaseModel):
    """单张图片的视觉分析结果。"""

    image_id: str = Field(..., description="图片唯一标识，对应 XhsImageInput.image_id。")
    file_name: str = Field(..., description="图片文件名。")
    subject_description: str = Field(..., description="仅描述图片可见主体；无法确认的食材或酱料使用客观上位词并标记不确定，不推断配方、制作方式、味道或功效。")
    atmosphere_vibe: str = Field(..., description="情绪 / 氛围描述。")
    visual_details: List[str] = Field(..., description="至少 3 个容易被忽略但重要的视觉细节。")
    image_quality_score: str = Field(
        ...,
        description="质量评价（1-10 分 + 理由），综合构图、光线、清晰度等维度。",
    )
    highlight_feature: str = Field(
        ...,
        description="视觉锚点：用户第一眼最容易被吸引的元素，以及为何是锚点。",
    )


class XhsImageEditPlan(BaseModel):
    """单张图片在小红书内置编辑器中的编辑 / P 图方案。"""

    image_id: str = Field(..., description="图片唯一标识。")
    file_name: str = Field(..., description="图片文件名。")
    overall_edit_strategy: str = Field(
        ...,
        description="整体编辑思路（统一使用小红书自带内置编辑能力，不推荐外部 App），例如整体画面调性、风格方向。",
    )
    crop_suggestion: str = Field(
        ..., description="剪裁建议：横竖构图、主体位置、留白等。"
    )
    light_color_adjustment: str = Field(
        ...,
        description="亮度 / 对比度 / 饱和度等基础参数调整建议，使用相对表述而非具体数值。",
    )
    filter_suggestion: str = Field(
        ...,
        description="小红书内置滤镜建议，可给出滤镜系列或风格描述。",
    )
    text_overlay_suggestion: str = Field(
        ...,
        description="文字建议：是否加文字、文字内容方向、出现位置与数量控制，避免遮挡关键视觉锚点。",
    )
    beauty_adjustment_suggestion: str = Field(
        ...,
        description="美颜建议（仅在人像时有效），强调自然不过度美颜，可给出相对强度建议。",
    )
    is_recommended_as_cover: bool = Field(
        ..., description="是否建议作为首图 / 封面。"
    )
    risk_and_pitfall_notes: str = Field(
        ...,
        description="需要规避的审美风险 / 平台审核风险，例如不过度裸露、避免违禁文案等。",
    )


class XhsVisualBatchReport(BaseModel):
    """多张图片的视觉分析汇总报告。"""

    user_raw_intent: str = Field(..., description="用户的原始文本意图。")
    images_visual: List[XhsImageVisualAnalysis] = Field(
        ..., description="所有图片的视觉分析结果列表。"
    )
    summary: str = Field(
        ..., description="所有图片视觉分析的总结。"
    )


class XhsImageEditBatchReport(BaseModel):
    """多张图片的编辑 / P 图方案汇总报告。"""

    images_edit_plan: List[XhsImageEditPlan] = Field(
        ..., description="所有图片对应的小红书内置编辑方案列表。"
    )
    summary: str = Field(
        ..., description="所有图片编辑 / P 图方案的总结。"
    )


class XhsContentStrategyBrief(BaseModel):
    """内容策略简报，由增长策略 Agent 产出。"""

    input_evaluation: str = Field(
        ...,
        description="基于用户诉求和图片素材的综合评估，指出优势、劣势和修图建议。",
    )
    target_audience_persona: str = Field(
        ...,
        description="目标受众画像：年龄、职业、生活状态、心理诉求等。",
    )
    core_pain_point: str = Field(..., description="核心痛点 / 诉求。")
    suggested_title: str = Field(
        ...,
        description="基于用户意图和可见事实的简洁候选标题，可含Emoji，不能添加未经提供的经历或效果承诺。",
    )
    content_outline: List[str] = Field(
        ..., description="笔记大纲：如场景引入、体验描写、干货植入、结尾引导等。"
    )
    engagement_strategy: str = Field(
        ...,
        description="互动策略：邀请分享观点或提问，不能编造赠品、抽奖、活动或优惠。",
    )
    retention_strategy: str = Field(
        ...,
        description="收藏策略：总结已提供或可见的事实；信息不足不能制造饮食公式、配比或营养建议。",
    )
    seo_keywords: List[str] = Field(
        ..., description="3 个左右必须埋入文案的长尾关键词列表。"
    )


class XhsCopywritingOutput(BaseModel):
    """原始文案，由资深 MCN 内容编辑 Agent 产出。"""

    title: str = Field(..., description="带 Emoji 的小红书标题。")
    content: str = Field(..., description="完整小红书笔记正文。")
    picture_order: List[str] = Field(
        ..., description="按照发布顺序排列的图片 image_id 列表。"
    )
    highlight_hooks: List[str] = Field(
        ..., description="文中关键“钩子句”列表，便于做 A/B 测试。"
    )


class XhsSEOOptimizedNote(BaseModel):
    """SEO 优化后的笔记内容，由搜索优化 Agent 产出。"""

    optimization_summary: str = Field(
        ..., description="本次 SEO 优化的要点与改动说明。"
    )
    optimized_title: str = Field(..., min_length=1, max_length=20, description="SEO 优化后的标题，最多20个字符。")
    optimized_content: str = Field(..., min_length=1, max_length=1000, description="SEO 优化后的正文，最多1000个字符。")
    optimized_picture_order: List[str] = Field(
        ..., description="结合搜索与转化优化后的图片顺序。"
    )
    tags: List[str] = Field(..., description="5-8 个用于搜索与话题分发的标签。")


class XhsImageWithPlans(BaseModel):
    """单张图片的完整信息：基础信息 + 分析 + 编辑方案。"""

    base_info: XhsImageInput = Field(..., description="基础元信息。")
    visual_analysis: XhsImageVisualAnalysis = Field(
        ..., description="视觉分析结果。"
    )
    edit_plan: XhsImageEditPlan = Field(..., description="编辑 / P 图方案。")


class XhsNoteFinalReport(BaseModel):
    """整体笔记撰写报告，供 API 直接返回。"""

    idea_text: str = Field(..., description="原始创作意图文本。")
    strategy_brief: XhsContentStrategyBrief = Field(
        ..., description="内容策略简报。"
    )
    raw_copywriting: XhsCopywritingOutput = Field(
        ..., description="未做 SEO 优化的原始文案。"
    )
    seo_optimized_note: XhsSEOOptimizedNote = Field(
        ..., description="SEO 优化后的文案与标签。"
    )
    images: List[XhsImageWithPlans] = Field(
        ..., description="每张图片的视觉分析与编辑方案。"
    )


class XhsNoteReportResponse(BaseModel):
    """顶层响应数据结构，便于与统一 ApiResponse 泛型结合。"""

    report: str = Field(..., description="最终笔记撰写报告。")


class XhsGeneratedNote(BaseModel):
    """移动客户端可直接展示的笔记，不包含服务端临时路径。"""

    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=8000)
    tags: List[str] = Field(default_factory=list)
    image_order: List[str] = Field(..., description="上传序号 img_0、img_1 等的完整排列。")
    report: str = ""
    is_demo: bool = Field(False, description="true 代表离线示例，不是模型生成结果。")
    review_warnings: List[str] = Field(default_factory=list, description="需要用户核对或编辑的提示；无提示不代表事实已经验证。")

