"""Explicit layout repair is local, preserves words and has no model calls."""
import re
import socket

import pytest

from app.services.note_layout import apply_requested_layout


@pytest.mark.parametrize("idea", ["请客观列出三个构图观察，每条独立一行；不要诗歌。", "列出三项，每项单独1行。", "每条一行，分条列出观察。"])
def test_one_line_per_item_does_not_collapse_the_whole_list(idea):
    text = "1. 花瓣层叠。\n2. 主体清晰。\n3. 背景柔和。"
    assert apply_requested_layout(text, idea) == text


REAL_POEM = "金焰盘旋成塔，赤霞铺作锦毯；粉绡垂落如雾，碧缕飞散似电。管瓣收束成珠，丝瓣舒展成星，千姿在静默中迸发灼热的秩序。"


def words(value):
    return re.sub(r"[\s，,；;。！？!?.]", "", value)


def test_real_poem_becomes_four_complete_lines_without_changing_words():
    result = apply_requested_layout(REAL_POEM, "写一首四行短诗，每行一句，不添加说明。")
    lines = result.splitlines()
    assert len(lines) == 4
    assert all(line.endswith("。") for line in lines)
    assert words(result) == words(REAL_POEM)
    assert lines == [
        "金焰盘旋成塔，赤霞铺作锦毯。",
        "粉绡垂落如雾，碧缕飞散似电。",
        "管瓣收束成珠，丝瓣舒展成星。",
        "千姿在静默中迸发灼热的秩序。",
    ]


def test_line_request_alone_preserves_all_existing_punctuation():
    result = apply_requested_layout(REAL_POEM, "请排成4行短诗。")
    assert len(result.splitlines()) == 4
    assert result.replace("\n", "") == REAL_POEM


def test_correct_four_lines_remain_byte_for_byte_including_spaces():
    content = " 金焰盘旋成塔。\n赤霞铺作锦毯。\n粉绡垂落如雾。\n碧缕飞散似电。 "
    assert apply_requested_layout(content, "写四行，每行一句。") == content


def test_free_verse_without_a_count_is_not_reformatted():
    content = "花瓣向外舒展，光留在中央。\n\n让这一帧安静一些。"
    assert apply_requested_layout(content, "写温柔的自由诗，保持自然节奏。") == content


def test_two_paragraphs_use_complete_sentences_without_losing_text():
    content = "画面里有一朵花。花瓣向四周展开。花心颜色较深。近景呈现轮廓。背景比较简洁。"
    result = apply_requested_layout(content, "用客观语气写两段短文。")
    paragraphs = result.split("\n\n")
    assert len(paragraphs) == 2
    assert all(paragraph.endswith("。") for paragraph in paragraphs)
    assert result.replace("\n", "") == content
    assert abs(len(paragraphs[0]) - len(paragraphs[1])) < 15


@pytest.mark.parametrize("idea", [
    "不要写四行短诗。",
    "不需要四行，保持自由体。",
    "不用4行。",
    "写4行以内。",
    "最多四行。",
    "至少四行。",
    "四行左右就好。",
    "大约4行。",
    "写3到4行。",
    "写3-4行。",
    "写三至四行。",
    "写三行到四行。",
    "四行或五行均可。",
    "写四、五行。",
    "写四行、分为两段。",
    "写四行，也可以写五行。",
    "每段四行。",
    "每一行一句。",
    "每一段两句。",
    "一行一句，自由分行。",
    "一句一行，保持自由诗。",
    "原文有四行字。请描述画面。",
    "例如四行短诗，具体体裁由你决定。",
    "请修改第4行。",
    "写13行。",
])
def test_negative_approximate_or_ambiguous_requests_do_not_force_a_count(idea):
    assert apply_requested_layout(REAL_POEM, idea) == REAL_POEM


def test_negated_line_count_does_not_hide_an_explicit_paragraph_request():
    result = apply_requested_layout(REAL_POEM, "不要四行，改为两段。")
    assert len(result.split("\n\n")) == 2
    assert result.replace("\n", "") == REAL_POEM


def test_same_count_repeated_in_chinese_and_digits_is_unambiguous():
    result = apply_requested_layout(REAL_POEM, "写四行短诗，严格4行。")
    assert len(result.splitlines()) == 4


@pytest.mark.parametrize("number", ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "十", "十一", "十二", "两"])
def test_supported_counts_use_only_available_clause_boundaries(number):
    content = "，".join(f"花瓣{index}" for index in range(12)) + "。"
    expected = {"十": 10, "十一": 11, "十二": 12, "两": 2}.get(number)
    expected = int(number) if expected is None else expected
    result = apply_requested_layout(content, f"请排成{number}行。")
    assert len(result.splitlines()) == expected
    assert result.replace("\n", "") == content


def test_correct_paragraphs_with_windows_newlines_are_unchanged():
    content = "花瓣向外展开。\r\n\r\n背景比较简洁。"
    assert apply_requested_layout(content, "写成两段。") == content


def test_existing_line_breaks_can_be_merged_without_cutting_words():
    content = "花瓣向外展开\n花心颜色较深\n背景比较简洁"
    result = apply_requested_layout(content, "排成两行。")
    assert len(result.splitlines()) == 2
    assert result.replace("\n", "") == content.replace("\n", "")


@pytest.mark.parametrize("content,idea", [
    ("花瓣沿着光线静静展开", "写四行短诗。"),
    ("花瓣向外展开，花心颜色较深。", "排成三段。"),
    ("", "请用两行。"),
])
def test_insufficient_reliable_boundaries_raise_instead_of_splitting_words(content, idea):
    with pytest.raises(ValueError, match="完整短句不足"):
        apply_requested_layout(content, idea)


def test_no_network_or_model_request_is_needed(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("排版不允许发起网络或第二次模型请求")
    monkeypatch.setattr(socket, "create_connection", blocked)
    result = apply_requested_layout(REAL_POEM, "写4行短诗，每行一句。")
    assert len(result.splitlines()) == 4
