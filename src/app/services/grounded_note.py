"""从短视觉观察组装笔记，既不接受自由文案，也不再调用模型。

过滤器是保守的本地风险筛选，并不能独立证明图中物体识别正确，亦不能
穷尽所有表达方式。它刻意省略部分本可见的品牌、文字和数量，避免把
推测扩写成体验、配方或承诺。低确定性的观察不进入最终文案。
食物类别只采用受控的粗分类、颜色和位置；即使模型标记 certain，
自由文本里的具体食材名称也不具备鉴定依据，不能用于食物标题或正文。
"""
from __future__ import annotations

import re
import unicodedata

from app.schemas.fast_note import VisualFact, VisualFactsBatch, VisualFoodItem
from app.schemas.xhs_note import XhsGeneratedNote


_CATEGORY_TAGS = {
    "food": "美食记录",
    "nature": "自然风景",
    "animal": "动物照片",
    "person": "人像记录",
    "object": "物件记录",
    "place": "空间记录",
    "other": "图片手记",
}
_FOOD_KINDS = {
    "fish": "鱼肉", "leafy_vegetables": "叶菜", "grains": "谷物", "sauce": "酱汁",
    "round_pieces": "圆形配菜", "block_pieces": "块状配菜", "drink": "饮品", "food": "食物",
}
_FOOD_COLORS = {
    "green": "绿色", "purple": "紫色", "orange": "橙色", "yellow": "黄色",
    "white": "白色", "brown": "棕色", "dark": "深色", "mixed": "多色", "unknown": "",
}
_FOOD_POSITIONS = {
    "center": "中央", "left": "左侧", "right": "右侧", "top": "上方", "bottom": "下方",
    "unspecified": "画面中",
}


def _food_item_text(item: VisualFoodItem) -> str:
    """Local enum mappings prevent free ingredient names from entering copy."""
    return f"{_FOOD_POSITIONS[item.position]}可见{_FOOD_COLORS[item.color]}{_FOOD_KINDS[item.kind]}"

# 这些内容通常无法仅由一张照片确认。黑名单不能替代语义事实验证；
# 因此最终正文只复用通过筛选的观察句，不再让写作模型改写或扩展。
_UNOBSERVABLE_PHRASES = (
    # 食谱、制作过程及无法从视觉确认的精确酱料成分。
    "配方", "食谱", "做法", "制作", "烹饪", "煎", "烤", "焗", "蒸", "炸", "炒", "炖",
    "煮", "烘", "腌", "烩", "卤", "炙", "熬", "焖", "焯", "汆", "涮", "出炉",
    "自制", "手作", "手工", "亲手", "现做", "现切", "调制", "拌入",
    "配料", "成分", "打成", "制成", "搅拌", "磨成", "压成", "揉成", "捣碎", "榨汁",
    "加入", "淋上", "撒上", "裹上", "罗勒", "橄榄油", "黄油", "奶油", "蜂蜜", "秘制", "配比", "公式",
    # 味觉、嗅觉、体感和营养、健康结论。
    "味道", "口味", "口感", "新鲜", "香气", "闻起来", "吃起来", "入口", "好吃", "美味", "鲜嫩", "鲜美",
    "酥脆", "爽口", "软糯", "香甜", "咸香", "酸甜", "清甜", "香浓", "浓郁", "解腻",
    "很香", "好香", "香喷喷", "香味", "香醇", "醇香", "鲜香", "焦香", "香酥", "酥香",
    "浓香", "果香", "甜味", "咸味", "酸味", "辣味", "苦味", "鲜味", "鲜甜", "甜度",
    "辣度", "酸度", "回甘", "顺滑", "绵密", "多汁", "爆汁", "q弹", "弹牙", "有嚼劲", "咬下",
    "不腻", "饱腹", "管饱", "扛饿", "耐饿", "顶饿", "减脂", "减肥", "掉秤", "瘦",
    "低卡", "低脂", "低糖", "无糖", "零糖", "卡路里", "热量", "大卡", "千卡", "蛋白",
    "营养", "碳水", "膳食", "高纤", "控糖", "血糖", "代谢", "消化", "抗氧化", "功效",
    "疗效", "健康", "养生", "治愈", "助眠", "免疫", "长胖", "不胖", "不怕胖", "燃脂",
    # 购买、营销活动、店铺与地址。
    "价格", "售价", "人均", "性价比", "划算", "折扣", "优惠", "促销", "抽奖", "赠品", "赠送",
    "送你", "领取", "下单", "购买", "领券", "限时", "包邮", "开业", "新店", "必买",
    "链接", "地址", "店名", "门店", "营业", "预约", "到店", "探店", "打卡", "位于",
    "坐落", "北京", "上海", "广州", "深圳", "杭州", "成都", "苏州", "品牌", "正品", "进口",
    "产地", "有机", "野生", "纯天然",
    # 作者经历、时间、人物身份与关系。
    "亲测", "实测", "亲身", "亲历", "吃过", "尝过", "试过", "去过", "买过", "做过",
    "我", "咱", "本人", "自家", "朋友", "家人", "老公", "老婆", "闺蜜", "同事",
    "喜欢", "推荐", "必吃", "最爱", "回购", "每天", "每周", "每次", "今天", "昨天",
    "明天", "今日", "昨日", "明日", "上周", "下周", "上月", "本周", "这周", "这次", "上次",
    "早上", "中午", "晚上", "早餐", "午餐", "晚餐", "夜宵", "刚刚", "终于", "坚持", "已经", "吃完",
    "吃了", "尝了", "去了", "买了", "做了", "第几次", "夫妻", "情侣", "妈妈", "爸爸",
    "宝宝", "一家人", "身份", "职业", "从事", "一名", "这位", "他是", "她是",
    "医生", "医师", "护士", "老师", "教师", "警察", "军人", "律师", "厨师", "明星", "网红",
    # A certainty flag cannot override hedging in the actual sentence.
    "可能", "似乎", "也许", "大概", "疑似", "看起来像", "应该是", "或许", "推测", "不确定",
    # 图片中的文字、创作方向和文件名均不具有指令权限。
    "忽略", "指令", "提示词", "系统", "返回", "输出", "json", "prompt", "assistant",
    "system", "developer", "user", "role", "你是", "请", "必须", "模型", "api", "token",
    "执行", "调用", "复制", "粘贴", "发布", "生成", "开发者", "规则", "http", "www.",
)
_TRADITIONAL_TO_SIMPLIFIED = str.maketrans({
    "飽": "饱", "熱": "热", "養": "养", "減": "减",
    "價": "价", "錢": "钱", "親": "亲", "測": "测", "製": "制", "獎": "奖",
    "贈": "赠", "體": "体", "驗": "验", "覺": "觉", "醬": "酱", "欖": "榄",
    "蘿": "萝", "蔔": "卜", "購": "购", "過": "过", "單": "单", "門": "门",
    "營": "营", "業": "业", "優": "优", "療": "疗", "蘭": "兰", "號": "号",
    "飯": "饭", "氣": "气", "憶": "忆", "歡": "欢", "薦": "荐", "濃": "浓", "膩": "腻",
    "藝": "艺", "廚": "厨", "調": "调", "這": "这", "時": "时", "間": "间",
})
_CHINESE_NUMBER = r"[零〇一二两兩三四五六七八九十百千万萬亿億半]+"
_UNSAFE_QUANTITY = re.compile(
    rf"{_CHINESE_NUMBER}(?:元|块|塊|克|斤|毫升|升|卡|小时|小時|分钟|分鐘|天|周|月|年|次|成|折|比)"
    rf"|{_CHINESE_NUMBER}[:：/比]{_CHINESE_NUMBER}"
    r"|(?:三二一|三比二比一)"
)
_ADDRESS = re.compile(r"[\u4e00-\u9fffA-Za-z]{2,}(?:路|街|巷|镇|市|区|县|省|店|馆)(?:号|$)")


def _normalized_for_screening(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().translate(_TRADITIONAL_TO_SIMPLIFIED)
    return "".join(character for character in normalized if not character.isspace() and unicodedata.category(character) != "Cf")


def _safe_fact_text(fact: VisualFact) -> str | None:
    if fact.certainty != "certain":
        return None
    value = fact.text.strip()
    compact = _normalized_for_screening(value)
    if not compact or not any(character.isalpha() for character in compact):
        return None
    # Do not preserve invisible controls, multiline instructions, URLs or markup.
    if any(unicodedata.category(character) in {"Cc", "Cf"} for character in value):
        return None
    # The protocol requests Chinese common nouns. English prose and labels can
    # bypass Chinese risk words ("homemade", "keeps you full", identities/brands).
    # Reject them conservatively instead of pretending to verify their meaning.
    if re.search(r"[a-z]", compact):
        return None
    if any(character.isnumeric() and character not in "零〇一二两兩三四五六七八九十百千万萬亿億半" for character in compact):
        return None
    if any(character in compact for character in "<>{}[]=\\¥￥$€£"):
        return None
    if any(phrase in compact for phrase in _UNOBSERVABLE_PHRASES):
        return None
    if _UNSAFE_QUANTITY.search(compact) or _ADDRESS.search(compact.rstrip("。！？!?，,")):
        return None
    return value


def _sentence(value: str) -> str:
    return value if value.endswith(("。", "！", "？", ".", "!", "?")) else value + "。"


def _opening(idea_text: str) -> str:
    """Only select predefined style; never interpolate the user's statements."""
    if any(style in idea_text for style in ("简洁", "简短", "极简", "客观", "正式")):
        return "用照片留住这些画面。"
    if any(style in idea_text for style in ("温柔", "松弛", "治愈")):
        return "把目光停在照片里的小细节。"
    if any(style in idea_text for style in ("活泼", "俏皮", "可爱", "轻松")):
        return "📷 翻开相册，看看这些画面。"
    return "📷 把这些画面留在这里。"


def render_grounded_note(facts: VisualFactsBatch, idea_text: str, image_ids: list[str]) -> XhsGeneratedNote:
    """Preserve every uploaded image and assemble only screened, certain facts.

    A complete ID match proves protocol coverage, not that the model perceived
    every image correctly. This renderer never calls an LLM or uses user intent
    as evidence for facts or personal experience.
    """
    actual_ids = [image.image_id for image in facts.images]
    if not image_ids or len(image_ids) > 20 or len(set(image_ids)) != len(image_ids):
        raise ValueError("上传图片标识必须唯一且完整")
    if len(actual_ids) != len(image_ids) or set(actual_ids) != set(image_ids):
        raise ValueError("图片视觉结果与上传图片不一致")
    by_id = {image.image_id: image for image in facts.images}
    candidates: list[list[str]] = []
    safe_subjects: list[str] = []
    tags: list[str] = []
    for image_id in image_ids:
        image = by_id[image_id]
        if image.category == "food":
            # Never infer ingredient identity from the model's free text, even
            # when its certainty field says certain. A coarse enum can still be
            # visually misclassified; it reduces detail rather than proving it.
            items = [item for item in image.food_items if item.certainty == "certain"]
            subject = _FOOD_KINDS[items[0].kind] if items else None
            choices = [_food_item_text(item) for item in items]
        else:
            subject = _safe_fact_text(image.subject)
            if subject and image.category == "person":
                # A photo does not prove a person's name, profession or relationship.
                # A generic subject avoids putting identity claims in the title.
                subject = "人物"
            choices = [subject] if subject else []
            choices.extend(text for fact in image.observations if (text := _safe_fact_text(fact)))
        if subject:
            safe_subjects.append(subject)
        choices = list(dict.fromkeys(_sentence(value) for value in choices))
        has_safe_fact = bool(choices)
        if not choices:
            choices = ["这一帧先留在这里，细节可以之后再补充。"]
        candidates.append(choices)
        # A category is only useful as a visual tag when at least one observation
        # survived. Otherwise it could reintroduce an unsupported classification.
        category_tag = _CATEGORY_TAGS[image.category] if has_safe_fact else _CATEGORY_TAGS["other"]
        if category_tag not in tags:
            tags.append(category_tag)
    tags.extend(tag for tag in ("相册分享", "图片手记") if tag not in tags)
    # Match Flutter's copied body exactly: content + blank line + #tags. The
    # title has its own input field and is not part of this 1,000-character limit.
    copied_tags = " ".join(f"#{tag}" for tag in tags)
    content_budget = 1000 - len("\n\n" + copied_tags)

    title = "把这些画面留在相册里"
    if safe_subjects:
        subject_title = safe_subjects[0].rstrip("。！？!?.,，；;：:")
        if subject_title:
            title = subject_title + "｜随手记" if len(subject_title) <= 16 else subject_title

    # Start with the shortest complete safe sentence per image. Reserve space
    # for every image and the copied tags before spending it on optional detail.
    candidates = [sorted(choices, key=len) for choices in candidates]
    selected = [[choices[0]] for choices in candidates]
    prefix = _opening(idea_text)
    ending = "你最先注意到哪个细节？" if len(image_ids) == 1 else "哪一张最吸引你的目光？"

    def compose() -> str:
        paragraphs = [" ".join(values) for values in selected]
        if len(paragraphs) > 1:
            paragraphs = [f"{index + 1}. {paragraph}" for index, paragraph in enumerate(paragraphs)]
        return "\n\n".join(value for value in [prefix, *paragraphs, ending] if value)

    if len(compose()) > content_budget:
        ending = ""
    if len(compose()) > content_budget:
        prefix = ""

    # Allocate detail across images before adding a second extra detail. Never
    # truncate a fact to fit: keep the shorter complete set and cover every image.
    for detail_index in (1, 2):
        for index, choices in enumerate(candidates):
            if len(choices) <= detail_index:
                continue
            selected[index].append(choices[detail_index])
            if len(compose()) > content_budget:
                selected[index].pop()
    content = compose()
    # Maximum 20 * (40-character observation + punctuation + number + spacing)
    # plus local tags fits even when no subject is usable. Fixed style sentences
    # are expendable; a complete observation for every image is not.
    if len(content) > content_budget:
        raise ValueError("视觉事实超过笔记长度限制")
    note = XhsGeneratedNote(title=title, content=content, tags=tags, image_order=list(image_ids))
    note.report = f"生成笔记标题: {note.title}\n生成笔记正文: {note.content}\n生成笔记图片顺序: {note.image_order}\n生成笔记标签: {note.tags}"
    return note
