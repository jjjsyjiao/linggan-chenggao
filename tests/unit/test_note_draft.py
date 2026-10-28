"""Offline tests for intent preservation and narrowly scoped provenance checks."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.note_draft import IntentAwareGeneration
from app.services.note_draft import render_intent_note


def generation(content="我把秋天写进心里。\n\n一朵菊花，也能安放温柔。", *, title="菊花写给秋天的诗", tags=None, context=None, category="nature"):
    return IntentAwareGeneration.model_validate({
        "images": [{"image_id": "img_0", "category": category, "subject": {"text": "黄色菊花", "certainty": "certain"}, "observations": []}],
        "user_context_used": context or [],
        "draft": {"title": title, "content": content, "tags": [] if tags is None else tags},
    })


def render(result, idea="给菊花写一首温柔的小诗，不要互动引导"):
    return render_intent_note(result, idea, ["img_0"])


def test_poem_first_person_healing_emoji_and_no_question_are_preserved():
    content = "今天想慢一点。🌼\n\n我把秋天写进心里，\n让这朵菊花，治愈自己的忙碌。"
    result = generation(content, title="给自己一点温柔🌼")
    note = render(result)
    assert note.title == result.draft.title
    assert note.content == content
    assert note.tags == []
    assert "？" not in note.content
    assert "细节可以之后再补充" not in note.content


def test_real_poem_keeps_its_words_and_applies_explicit_four_line_request():
    text = "金焰盘旋成塔，赤霞铺作锦毯；粉绡垂落如雾，碧缕飞散似电。管瓣收束成珠，丝瓣舒展成星，千姿在静默中迸发灼热的秩序。"
    note = render(generation(text, title="菊之形色"), "现代短诗，正文恰好4行，每行一句，80字以内，不要话题。")
    assert note.content == "金焰盘旋成塔，赤霞铺作锦毯。\n粉绡垂落如雾，碧缕飞散似电。\n管瓣收束成珠，丝瓣舒展成星。\n千姿在静默中迸发灼热的秩序。"
    assert note.title == "菊之形色" and note.tags == []
    assert note.report.count(note.content) == 1


@pytest.mark.parametrize("content", ["四周都是盛开的花。", "花朵四周可见层叠的叶片。", "镜头四周铺满黄色花瓣。"])
def test_spatial_surroundings_are_not_misread_as_a_duration(content):
    assert render(generation(content)).content == content


def test_different_user_directed_drafts_are_not_collapsed_into_one_template():
    poem = render(generation("花在风里，\n我在秋天里。"))
    plain = render(generation("这是一朵黄色菊花，花瓣层层展开。", title="黄色菊花"), "客观描述，不要诗歌")
    assert poem.content != plain.content
    assert plain.content == "这是一朵黄色菊花，花瓣层层展开。"


def test_explicit_user_background_is_allowed_and_preserved():
    idea = "北京植物园菊花已到最佳观赏期。用治愈的语气写，不要提问。"
    result = generation("北京植物园的菊花已到最佳观赏期。让颜色替忙碌的心松一口气。", context=["北京植物园菊花已到最佳观赏期"])
    assert render(result, idea).content == result.draft.content


def test_fact_and_style_instruction_can_share_one_literal_context_excerpt():
    idea = "北京植物园菊花已到最佳观赏期，不要提问。"
    result = generation("北京植物园已到最佳观赏期，温柔就在花瓣间。", context=[idea])
    assert render(result, idea).content == result.draft.content


def test_literal_context_with_final_punctuation_and_background_label_is_used():
    background = "这两张菊花照片是我在自家阳台拍的。"
    result = generation("我在自家阳台拍下这些菊花，留下属于自己的秋意。", context=[background])
    assert render(result, "背景：" + background + "请写轻松一点。").content == result.draft.content


@pytest.mark.parametrize("content", ["花瓣向四周展开。", "可以试着拍下花瓣层次。", "具体花期请以园方公告为准。"])
def test_spatial_description_composition_advice_and_unknown_bloom_are_allowed(content):
    assert render(generation(content)).content == content


def test_four_weeks_as_actual_bloom_duration_still_needs_source():
    note = render(generation("花期长达四周。"))
    assert note.content == "花期长达四周。"
    assert any("具体数值" in warning for warning in note.review_warnings)


def test_nonpersonal_poetic_motion_is_not_treated_as_a_visit_history():
    content = "风去了远方，秋天来到花间。\n这一刻，是一场视觉旅行。"
    assert render(generation(content)).content == content


@pytest.mark.parametrize("content", [
    "这束菊花只要99元。", "花期可达30天。", "2026年10月28日在这里拍下。", "养护温度保持25℃。",
    "每天服用2片。", "浇水500毫升。", "在苏州植物园拍下这束菊花。", "我亲手种下了这盆菊花。",
    "我去了北京看菊花。", "菊花可以清热明目。", "看花能够治愈失眠。", "现在是最佳观赏期。",
])
def test_clear_unsourced_claims_are_retained_with_review_warnings(content):
    note = render(generation(content))
    assert note.content == content
    assert note.review_warnings
    assert all("核对" in warning for warning in note.review_warnings)


def test_amount_requires_matching_unit_not_just_the_same_number():
    result = generation("这束花价格100元。", context=["100字"])
    note = render(result, "写100字")
    assert note.content == result.draft.content
    assert any("具体数值" in warning for warning in note.review_warnings)


def test_explicit_amount_duration_and_photo_history_are_allowed():
    idea = "这束花花了99元，我在北京拍的照片，花期30天。"
    result = generation("99元的花束，花期30天。我在北京拍下这抹黄色。", context=["这束花花了99元", "我在北京拍的照片", "花期30天"])
    assert render(result, idea).content == result.draft.content


def test_made_up_context_cannot_authorize_a_claim():
    note = render(generation("花期30天。", context=["花期30天"]))
    assert note.content == "花期30天。"
    assert any("未逐字匹配" in warning for warning in note.review_warnings)
    assert any("具体数值" in warning and "30天" in warning for warning in note.review_warnings)


def test_negative_source_cannot_be_clipped_to_authorize_a_claim():
    note = render(generation("花期30天。", context=["30天"]), "不要编造30天花期")
    assert note.content == "花期30天。"
    assert any("具体数值" in warning for warning in note.review_warnings)


def test_food_fine_ingredients_are_not_authorized_by_visual_certainty():
    result = generation("配菜含黑豆、白豆、南瓜块。", category="food")
    note = render(result, "根据图片自由写一段")
    assert note.content == result.draft.content
    assert any("食材" in warning for warning in note.review_warnings)


def test_user_supplied_food_context_can_be_used():
    idea = "这盘是三文鱼、黑豆和南瓜，我亲手做的。写轻松些。"
    result = generation("亲手做的三文鱼，搭配黑豆和南瓜。把生活过成喜欢的颜色。", context=["这盘是三文鱼、黑豆和南瓜", "我亲手做的"], category="food")
    assert render(result, idea).content == result.draft.content


def test_food_visual_coarse_categories_and_poetic_style_are_allowed():
    content = "鱼肉和绿色叶菜相遇，橙色与绿色也有了自己的小合唱。"
    assert render(generation(content, category="food")).content == content


@pytest.mark.parametrize("location", ["title", "tag"])
def test_provenance_checks_also_cover_title_and_tags(location):
    result = generation(title="北京赏菊" if location == "title" else "菊花", tags=["清热明目"] if location == "tag" else [])
    note = render(result)
    assert note.title == result.draft.title and note.tags == result.draft.tags
    assert note.review_warnings


def test_copy_budget_includes_tags_and_does_not_truncate():
    oversized = render(generation("花" * 998, tags=["菊花"]))
    assert oversized.content == "花" * 998
    assert any("1000" in warning for warning in oversized.review_warnings)
    result = generation("花" * 995, tags=["菊花"])
    assert render(result).content == "花" * 995


def test_copy_budget_counts_separated_tag_tokens_like_flutter():
    note = render(generation("花" * 994, tags=["甲 乙"]))
    assert note.content == "花" * 994
    assert any("1000" in warning for warning in note.review_warnings)


def test_existing_body_hashtag_is_not_counted_twice_or_removed_from_draft():
    content = "花" * 996 + " #菊花"
    result = generation(content, tags=["菊花", "##菊花"])
    note = render(result)
    assert len(note.content) == 1000
    assert note.content == content
    assert note.tags == ["菊花", "##菊花"]


def test_duplicate_missing_or_unknown_image_ids_are_rejected():
    result = generation()
    with pytest.raises(ValueError):
        render_intent_note(result, "", ["img_1"])
    result.images.append(result.images[0])
    with pytest.raises(ValueError):
        render_intent_note(result, "", ["img_0", "img_1"])


@pytest.mark.parametrize("mutation", [
    lambda data: data["draft"].update(title="花" * 201),
    lambda data: data["draft"].update(content="花" * 8001),
    lambda data: data["draft"].update(tags=["花"] * 17),
    lambda data: data["draft"].update(tags=["花" * 101]),
    lambda data: data["draft"].update(tags=[""]),
    lambda data: data["draft"].update(extra="free"),
    lambda data: data.update(extra="free"),
    lambda data: data.update(user_context_used=["花"] * 13),
    lambda data: data.update(user_context_used=["花" * 301]),
])
def test_schema_is_strict_and_bounded(mutation):
    data = generation().model_dump()
    mutation(data)
    with pytest.raises(ValidationError):
        IntentAwareGeneration.model_validate(data)


def test_platform_targets_are_warnings_below_absolute_resource_caps():
    title, content, tags = "花" * 200, "花" * 8000, ["花" * 100] * 16
    note = render(generation(content, title=title, tags=tags))
    assert note.title == title and note.content == content and note.tags == tags
    assert any("标题" in warning for warning in note.review_warnings)
    assert any("正文" in warning for warning in note.review_warnings)
    assert any("话题" in warning for warning in note.review_warnings)


def test_impossible_layout_keeps_the_complete_original_and_warns():
    note = render(generation("花开。"), "恰好4行，每行一句")
    assert note.content == "花开。"
    assert any("排版" in warning for warning in note.review_warnings)


def test_warnings_are_separate_from_body_and_copied_report():
    note = render(generation("花期30天。"))
    assert note.review_warnings
    assert "待核对" not in note.content
    assert "待核对" not in note.report
    assert "verified" not in note.model_dump()


def test_identical_warnings_are_deduplicated_and_all_matches_are_collected():
    note = render(generation("99元。99元。花期30天。"))
    assert sum("99元" in warning for warning in note.review_warnings) == 1
    assert any("30天" in warning for warning in note.review_warnings)
    assert any("花期" in warning for warning in note.review_warnings)


def test_review_warning_list_is_bounded_without_losing_the_draft():
    content = "。".join(f"{number}元" for number in range(1, 30))
    note = render(generation(content))
    assert note.content == content
    assert len(note.review_warnings) == 12
    assert "另有" in note.review_warnings[-1]
    assert "不是完整事实核验" in note.review_warnings[-1]


@pytest.mark.parametrize("context", [
    [], ["北京植物园"], ["目前已到最佳观赏期。"],
    ["吸引大家来北京植物园观赏菊花，目前已到最佳观赏期。"],
    ["北京植物园菊花目前正值最佳观赏期"],
    ["北京植物园的菊花已经进入最佳观赏期。错过就没机会了。"],
])
@pytest.mark.parametrize("content", [
    "北京植物园的菊花已到最佳观赏期，别错过眼前的颜色。",
    "北京植物园的菊花正值最好看的时候，给忙碌的心一点温柔。",
    "来北京植物园观赏菊花吧，目前已进入最佳观赏期。",
])
def test_current_real_prompt_and_varied_model_contexts_never_discard_a_draft(context, content):
    idea = "吸引大家来北京植物园观赏菊花，目前已到最佳观赏期。错过机会就没有了。"
    note = render(generation(content, context=context), idea)
    assert note.content == content
    assert note.title == "菊花写给秋天的诗"
    assert len(note.review_warnings) <= 12


def test_old_clients_can_parse_a_note_without_review_warning_field():
    from app.schemas.xhs_note import XhsGeneratedNote
    note = XhsGeneratedNote(title="菊花", content="花开。", image_order=["img_0"])
    assert note.review_warnings == []
