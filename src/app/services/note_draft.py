"""Preserve creative writing while checking a narrow set of sourceable claims.

This is deliberately not a factuality classifier. Literal provenance and a few
explicit assertion patterns catch common unsupported additions; they cannot
verify perception, all paraphrases, arbitrary names or the truth of user facts.
Subjective/poetic language is not replaced with a fixed caption template.
"""
from __future__ import annotations

import re
import unicodedata

from app.schemas.note_draft import IntentAwareGeneration
from app.schemas.xhs_note import XhsGeneratedNote
from app.services.note_layout import apply_requested_layout


_SPLIT = re.compile(r"[。！？!?；;\n，,]")
_CLAUSES = re.compile(r"[^。！？!?；;\n，,]+")
_NON_EVIDENCE = re.compile(r"不要|不能|不许|禁止|别写|别说|未曾|没有|并非|不是|不确定|可能|也许|假设|如果|假如|编造|虚构|杜撰|想象")
_NUMBER = r"(?:[+-]?\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千万半]+)"
_QUANTITIES = re.compile(
    rf"(?:[¥￥$€£]\s*{_NUMBER}|{_NUMBER}\s*(?:人民币|美元|欧元|块钱|元|毫秒|分钟|小时|秒|天|周|个月|月|年|微克|毫克|千克|公斤|毫升|摄氏度|℃|°c|克|斤|升|度))",
    re.IGNORECASE,
)
_DATES = re.compile(r"\b\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?\b|\d{1,2}月\d{1,2}[日号]|\d{1,2}[日号]")
_DOSAGE = re.compile(rf"{_NUMBER}\s*(?:片|粒|滴|次)")
_MEDICAL_CONTEXT = re.compile(r"服用|口服|剂量|用量|药|每日|每天")
_HEALTH = re.compile(
    r"(?:治好|治愈|治疗|预防)(?:失眠|焦虑|抑郁|疾病|感冒|咳嗽)|"
    r"(?:缓解|改善)(?:失眠|焦虑|抑郁|睡眠|疼痛)|"
    r"清热|解毒|明目|安神|助眠|抗癌|降血压|降血糖|提高免疫力|增强免疫力|减肥|减脂|瘦身|掉秤|燃脂"
)
_BLOOM = re.compile(r"最佳观赏期|花期|四季开花|全年开花|常年开花|久开不败|不易凋谢|永不凋谢")
_SEASONS = re.compile(r"春季|夏季|秋季|冬季|春天|夏天|秋天|冬天")
_POETIC = re.compile(r"愿|仿佛|好像|梦里|心里|心中|诗里")
_PLACES = re.compile(r"北京|上海|广州|深圳|苏州|杭州|南京|成都|重庆|武汉|西安|天津|厦门|青岛|长沙|云南|大理|丽江")
_NAMED_SITE = re.compile(r"(?:在|到|于|来自|位于|地点是|地址是|坐落于)([\u4e00-\u9fff]{2,12}(?:植物园|公园|博物馆|美术馆|景区))")
_EXPERIENCES = (
    (re.compile(r"去过|去了|到过|曾去|到访"), re.compile(r"去过|去了|到过|曾去|到访|旅游|旅行")),
    (re.compile(r"拍下|拍了|拍的|拍摄于|摄于|拍摄地"), re.compile(r"拍|摄于")),
    (re.compile(r"买过|买了|买来|购入"), re.compile(r"买|购入")),
    (re.compile(r"种过|种了|种下|养了|养过|亲手种"), re.compile(r"种|养")),
    (re.compile(r"吃过|吃了|尝过|尝了|喝过|喝了"), re.compile(r"吃|尝|喝")),
    (re.compile(r"亲测|实测|亲身体验|亲手制作|亲手做|带回来|带回来的"), re.compile(r"亲测|实测|亲身|亲手|带回")),
)
# Source checks target finer food identities and sensory/preparation claims,
# not prose style. This lexicon is intentionally incomplete and cannot turn a
# creative-writing validator into independent ingredient identification.
_FINE_FOOD = re.compile(
    r"三文鱼|金枪鱼|鳕鱼|鲈鱼|鲑鱼|鳗鱼|鲫鱼|鲤鱼|龙利鱼|巴沙鱼|"
    r"鹰嘴豆|芸豆|扁豆|豌豆|毛豆|蚕豆|黑豆|白豆|红豆|黄豆|绿豆|"
    r"南瓜|土豆|紫薯|红薯|山药|胡萝卜|西兰花|花椰菜|生菜|芝麻菜|菠菜|油麦菜|"
    r"黄瓜|西葫芦|番茄|西红柿|牛油果|鳄梨|柠檬|青柠|芒果|草莓|蓝莓|苹果|香蕉|"
    r"藜麦|燕麦|糙米|大米|小米|薏米|黑米|白米|玉米|荞麦|"
    r"罗勒|橄榄油|黄油|奶油|酱油|蚝油|蜂蜜|黑胡椒|芝士|奶酪|沙拉酱|蛋黄酱|青酱|松露|芥末|"
    r"鸡肉|牛肉|猪肉|鸭肉|羊肉|鸡胸|牛排|猪排|鸡蛋|鸭蛋|鲜虾|龙虾|扇贝|生蚝|牡蛎|鲍鱼|鱿鱼|章鱼|螃蟹"
)
_FOOD_PROCESS = re.compile(r"香煎|油煎|清蒸|水煮|烘烤|油炸|炙烤|腌制|手作|自制|亲手做|现做|鲜榨|打成|搅拌制成")
_FOOD_SENSORY = re.compile(r"鲜嫩|酥脆|软糯|香甜|咸香|酸甜|爽口|饱腹|管饱|香气|闻起来|吃起来")


def _normal(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def _evidence(idea_text: str, excerpts: list[str], warnings: list[str] | None = None) -> list[str]:
    warnings = warnings if warnings is not None else []
    valid_excerpts = []
    for excerpt in excerpts:
        if excerpt not in idea_text:
            preview = excerpt[:60] + ("…" if len(excerpt) > 60 else "")
            warnings.append(f"来源待核对：背景摘录“{preview}”未逐字匹配你的描述，未作为事实依据。")
        else:
            valid_excerpts.append(excerpt)
    clauses = list(_CLAUSES.finditer(idea_text))
    # Inspect the original surrounding clause as well, so a model cannot quote
    # "30天" out of "不要编造30天花期" and treat it as supplied fact.
    evidence = []
    for excerpt in valid_excerpts:
        # Original offsets retain surrounding labels ("背景：") and terminal
        # punctuation without requiring two differently split strings to match.
        for occurrence in re.finditer(re.escape(excerpt), idea_text):
            for part in _CLAUSES.finditer(excerpt):
                value = part.group().strip()
                start, end = occurrence.start() + part.start(), occurrence.start() + part.end()
                original = next((clause.group() for clause in clauses if clause.start() <= start and end <= clause.end()), "")
                if value and original and not _NON_EVIDENCE.search(value) and not _NON_EVIDENCE.search(original):
                    evidence.append(value)
    return evidence


def _require_source(claim: str, evidence: list[str], label: str, warnings: list[str]) -> None:
    if not any(_normal(claim) in _normal(source) for source in evidence):
        warnings.append(f"待核对：{label}“{claim}”未在你的描述中找到对应依据。")


def _check_claims(text: str, evidence: list[str], *, has_food: bool) -> list[str]:
    warnings: list[str] = []
    for match in _QUANTITIES.finditer(text):
        before = text[max(0, match.start() - 12):match.start()]
        after = text[match.end():match.end() + 8]
        spatial = re.search(r"(?:向|朝|往|围绕|环顾|环绕)$", before) or re.match(r"都|是|有|环绕|围绕|铺满|可见|一片|布满|开满|摆着|遍布", after)
        temporal = re.search(r"花期|持续|长达|维持|可达|保持|历时|养了|用了", before)
        if match.group() == "四周" and spatial and not temporal:
            # Four weeks and "toward the surroundings" share the same Chinese
            # characters. Directional composition language is not a duration.
            continue
        _require_source(match.group(), evidence, "具体数值", warnings)
    for match in _DATES.finditer(text):
        _require_source(match.group(), evidence, "日期", warnings)
    for clause in _SPLIT.split(text):
        if _MEDICAL_CONTEXT.search(clause):
            for match in _DOSAGE.finditer(clause):
                _require_source(match.group(), evidence, "剂量或频率", warnings)
        for match in _HEALTH.finditer(clause):
            _require_source(match.group(), evidence, "健康功效断言", warnings)
        if not _POETIC.search(clause):
            bloom_uncertain = re.search(r"以.{0,20}为准|无法确认|无法判断|不确定|尚未确认|需核实|请.{0,12}(?:核实|确认|查阅|参考)", clause)
            if not bloom_uncertain:
                for match in _BLOOM.finditer(clause):
                    _require_source(match.group(), evidence, "花期或观赏期断言", warnings)
            if _BLOOM.search(clause) and not bloom_uncertain:
                for match in _SEASONS.finditer(clause):
                    _require_source(match.group(), evidence, "花期季节", warnings)
            for match in _PLACES.finditer(clause):
                _require_source(match.group(), evidence, "具体地点", warnings)
            for match in _NAMED_SITE.finditer(clause):
                _require_source(match.group(1), evidence, "具体地点", warnings)
            for assertion, source_pattern in _EXPERIENCES:
                # "风去了远方" or "一场视觉旅行" is not a personal history
                # claim. Check explicit first-person actions or concrete photo/
                # first-hand attribution, rather than every occurrence of a verb.
                personal = re.search(r"我|我们|本人|咱们|拍下|拍了|拍的|拍摄于|摄于|拍摄地|亲测|实测|亲手", clause)
                advice = re.search(r"可以|不妨|试着|尝试|建议|记得|拍摄时", clause)
                if personal and not advice and assertion.search(clause) and not any(source_pattern.search(source) for source in evidence):
                    warnings.append("经历待核对：文案中的亲身经历未在你的描述中找到对应依据。")
        if has_food:
            for match in _FINE_FOOD.finditer(clause):
                _require_source(match.group(), evidence, "具体食材名称", warnings)
            for match in _FOOD_PROCESS.finditer(clause):
                _require_source(match.group(), evidence, "食物制作方式", warnings)
            if not re.search(r"看起来|看着|想象|仿佛|好像", clause):
                for match in _FOOD_SENSORY.finditer(clause):
                    _require_source(match.group(), evidence, "食物口感或体验", warnings)
    return warnings


def render_intent_note(result: IntentAwareGeneration, idea_text: str, image_ids: list[str]) -> XhsGeneratedNote:
    """Keep the complete draft; flag editorial risks for visible human review.

    The copied body includes tags. Explicit line/paragraph requests may adjust
    whitespace and boundary punctuation only; no words are invented or removed.
    Nothing is truncated or retried.
    Image coverage and literal excerpts are protocol checks, not proof of truth.
    """
    actual_ids = [image.image_id for image in result.images]
    if not image_ids or len(image_ids) > 20 or len(set(image_ids)) != len(image_ids):
        raise ValueError("上传图片标识必须唯一且完整")
    if len(actual_ids) != len(image_ids) or set(actual_ids) != set(image_ids):
        raise ValueError("图片视觉结果与上传图片不一致")
    warnings: list[str] = []
    evidence = _evidence(idea_text, result.user_context_used, warnings)
    draft = result.draft
    try:
        content = apply_requested_layout(draft.content, idea_text)
        if len(content) > 8000:
            content = draft.content
            warnings.append("排版待调整：重新排版会超过安全长度上限，已保留完整原稿。")
    except ValueError:
        content = draft.content
        warnings.append("排版待调整：无法仅用现有短句满足行数或段落要求，已保留完整原稿。")
    if len(draft.title) > 20:
        warnings.append("标题待精简：标题超过20字，已保留完整原稿供编辑。")
    # Match Flutter's copy logic without mutating the returned model draft:
    # split tag separators, strip # prefixes, deduplicate, skip tags in the body.
    tag_tokens = list(dict.fromkeys(
        token.lstrip("#").strip()
        for raw_tag in draft.tags for token in re.split(r"[\s,，]+", raw_tag)
        if token.lstrip("#").strip()
    ))
    copied_tags = " ".join(
        f"#{tag}" for tag in tag_tokens
        if not re.search(rf"(?:^|\s)#{re.escape(tag)}(?:\s|$)", content)
    )
    copied_body = content + ("\n\n" + copied_tags if copied_tags else "")
    if len(copied_body) > 1000:
        warnings.append("正文待精简：正文连同话题标签超过1000字，已保留完整原稿供编辑。")
    if len(draft.tags) > 8 or any(len(tag) > 24 for tag in draft.tags):
        warnings.append("话题待精简：话题超过建议数量或长度，已保留供编辑。")
    warnings.extend(_check_claims("\n".join([draft.title, content, *draft.tags]), evidence, has_food=any(image.category == "food" for image in result.images)))
    unique_warnings = list(dict.fromkeys(warnings))
    if len(unique_warnings) > 12:
        unique_warnings = unique_warnings[:11] + [f"另有{len(unique_warnings) - 11}项待核对。以上提示不是完整事实核验，请结合原图和实际背景检查。"]
    note = XhsGeneratedNote(title=draft.title, content=content, tags=list(draft.tags), image_order=list(image_ids), review_warnings=unique_warnings)
    note.report = f"生成笔记标题: {note.title}\n生成笔记正文: {note.content}\n生成笔记图片顺序: {note.image_order}\n生成笔记标签: {note.tags}"
    return note
