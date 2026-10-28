"""Apply an explicit line/paragraph count using existing clauses only.

This module performs no generation or I/O. It may change whitespace and, for
an explicit one-sentence-per-line request, terminal punctuation. It never adds,
removes, reorders, or divides words to make a requested count fit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


_NUMBER_TEXT = r"(?:\d{1,3}|[一二两三四五六七八九十]+)"
_COUNT = re.compile(rf"(?<![\d一二两三四五六七八九十])(?P<number>{_NUMBER_TEXT})\s*(?P<unit>行|段)")
_SCOPE_SEPARATOR = re.compile(r"[，,。！？!?；;\n]")
_NEGATIVE = re.compile(r"不要|不必|不需要|无需|不用|不能|不可|不许|别|避免|不是|勿")
_RESET_NEGATIVE = re.compile(r"但要|但是要|而是|改为|改成")
_LIMIT_PREFIX = re.compile(r"不超过|不得超过|至多|最多|至少|最少|不低于|不少于|大于|小于|不满|控制在|大约|大概|差不多|约")
_LIMIT_SUFFIX = re.compile(r"^\s*(?:个)?(?:以内|之内|以下|以上|左右|上下|前后|内|外)")
_RANGE_BEFORE = re.compile(rf"{_NUMBER_TEXT}\s*(?:行|段)?\s*[-—–~～至到或/、]\s*$")
_RANGE_AFTER = re.compile(rf"^\s*[-—–~～至到或/、]\s*{_NUMBER_TEXT}\s*(?:行|段)")
_CONTEXT = re.compile(r"背景|图中|图片(?:中|里|上)?|照片(?:中|里|上)?|原文|示例|例如|比如|假如|假设|如果|提到|写着|显示|印着|原来|原本|已有|现有")
_REQUEST = re.compile(r"写|要求|需要|用|分成|分为|排成|改为|改成|整理|调整|保持|限定|恰好|正好|必须|只|仅|一共|总共")
_ONE_SENTENCE = re.compile(r"(?:每|各)行(?:只|仅)?(?:一|1)(?:个)?句(?:子)?|(?:一|1)行(?:一|1)句")
_CLOSERS = '\"\'”’」』）)]】'
_BOUNDARY = re.compile(
    rf"[。！？；，;!?,]+[{re.escape(_CLOSERS)}]*"
    rf"|(?<!\d)\.(?!\d)(?=\s|$|[{re.escape(_CLOSERS)}])[{re.escape(_CLOSERS)}]*"
    r"|\r?\n(?:[ \t]*\r?\n)*"
)
_ONLY_PUNCTUATION = re.compile(rf"^[。！？；，;!?,.\s{re.escape(_CLOSERS)}]+$")


@dataclass
class _Clause:
    text: str
    weak_boundary: int


def _number(value: str) -> int | None:
    if value.isascii() and value.isdigit():
        result = int(value)
    else:
        digits = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
        if value == "十":
            result = 10
        elif value in {"十一", "十二"}:
            result = 10 + digits[value[-1]]
        else:
            result = digits.get(value, 0)
    return result if 1 <= result <= 12 else None


def _prefix(text: str, start: int) -> str:
    previous = list(_SCOPE_SEPARATOR.finditer(text, 0, start))
    return text[previous[-1].end() if previous else 0:start]


def _negative_scope(prefix: str) -> bool:
    resets = list(_RESET_NEGATIVE.finditer(prefix))
    if resets:
        prefix = prefix[resets[-1].end():]
    return bool(_NEGATIVE.search(prefix))


def _requested_count(idea_text: str) -> tuple[str, int] | None:
    requests: set[tuple[str, int]] = set()
    for match in _COUNT.finditer(idea_text):
        count = _number(match["number"])
        if count is None:
            continue
        prefix = _prefix(idea_text, match.start())
        suffix = idea_text[match.end():]
        if _negative_scope(prefix) or _LIMIT_PREFIX.search(prefix) or _LIMIT_SUFFIX.search(suffix):
            continue
        if _RANGE_BEFORE.search(prefix) or _RANGE_AFTER.search(suffix):
            continue
        if prefix.endswith(("第", "每")) or re.search(r"每(?:一|1)?段\s*$", prefix):
            continue
        if count == 1 and re.search(r"(?:每|各|逐)(?:一|1)?(?:条|项|句|段|个要点).{0,6}$", prefix):
            # "Each item on its own line" is not a request for one line total.
            continue
        if count == 1 and (prefix.endswith("句") or (match["unit"] == "行" and re.match(r"(?:一|1)(?:个)?句", suffix))):
            # "One sentence per line" describes a distribution, not a total
            # of one line. It must not collapse otherwise unconstrained prose.
            continue
        contexts = list(_CONTEXT.finditer(prefix))
        if contexts and not _REQUEST.search(prefix[contexts[-1].end():]):
            continue
        requests.add((match["unit"], count))
    # Different counts, or simultaneous line and paragraph requirements, need
    # interpretation that a punctuation-only formatter cannot safely provide.
    return next(iter(requests)) if len(requests) == 1 else None


def _one_sentence_per_line(idea_text: str) -> bool:
    return any(not _negative_scope(_prefix(idea_text, match.start())) for match in _ONE_SENTENCE.finditer(idea_text))


def _count_blocks(content: str, unit: str) -> int:
    if unit == "行":
        return sum(bool(line.strip()) for line in content.splitlines())
    return len([part for part in re.split(r"\r?\n(?:[ \t]*\r?\n)+", content.strip()) if part.strip()])


def _clauses(content: str) -> list[_Clause]:
    result: list[_Clause] = []
    pending = ""
    cursor = 0
    for match in _BOUNDARY.finditer(content):
        text = content[cursor:match.end()].strip()
        cursor = match.end()
        boundary = match.group()
        weak = int(not any(char in boundary for char in "。！？!?；;.\n\r"))
        if not text:
            continue
        if _ONLY_PUNCTUATION.fullmatch(text):
            if result:
                result[-1].text += text
                result[-1].weak_boundary = min(result[-1].weak_boundary, weak)
            else:
                pending += text
            continue
        result.append(_Clause(pending + text, weak))
        pending = ""
    tail = content[cursor:].strip()
    if tail:
        result.append(_Clause(pending + tail, 0))
    elif pending and result:
        result[-1].text += pending
    return result


def _partition(clauses: list[_Clause], count: int) -> list[str]:
    size = len(clauses)
    if size < count:
        raise ValueError(f"现有完整短句不足，无法在不改写文字的前提下排成{count}个块")
    prefix_lengths = [0]
    for clause in clauses:
        prefix_lengths.append(prefix_lengths[-1] + len(clause.text))
    total = prefix_lengths[-1]
    # Lexicographic cost: prefer sentence/semicolon/existing-newline cuts, then
    # balance lengths. Integer scaling avoids floating-point tie differences.
    previous: list[tuple[int, int] | None] = [None] * (size + 1)
    previous[0] = (0, 0)
    parents = [[-1] * (size + 1) for _ in range(count + 1)]
    for block in range(1, count + 1):
        current: list[tuple[int, int] | None] = [None] * (size + 1)
        for end in range(block, size - (count - block) + 1):
            for start in range(block - 1, end):
                if previous[start] is None:
                    continue
                length = prefix_lengths[end] - prefix_lengths[start]
                weak = clauses[end - 1].weak_boundary if end < size else 0
                score = (previous[start][0] + weak, previous[start][1] + (length * count - total) ** 2)
                if current[end] is None or score < current[end]:
                    current[end] = score
                    parents[block][end] = start
        previous = current
    result = []
    end = size
    for block in range(count, 0, -1):
        start = parents[block][end]
        result.append("".join(clause.text for clause in clauses[start:end]))
        end = start
    return list(reversed(result))


def _finish_sentence(value: str) -> str:
    closers = re.escape(_CLOSERS)
    if re.search(rf"[,，;；](?=[{closers}]*$)", value):
        return re.sub(rf"[,，;；](?=[{closers}]*$)", "。", value)
    return value


def apply_requested_layout(content: str, idea_text: str) -> str:
    """Satisfy one unambiguous exact count by reflowing complete clauses.

    Correct layouts and non-exact requests are returned byte-for-byte. If an
    exact request needs more reliable boundaries than the text contains, raise
    rather than split a word, discard text, or invent another sentence.
    """
    request = _requested_count(idea_text)
    if request is None:
        return content
    unit, count = request
    if _count_blocks(content, unit) == count:
        return content
    blocks = _partition(_clauses(content), count)
    if unit == "行" and _one_sentence_per_line(idea_text):
        blocks = [_finish_sentence(block) for block in blocks]
    return ("\n" if unit == "行" else "\n\n").join(blocks)
