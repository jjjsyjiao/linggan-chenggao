"""单次视觉调用的最小协议；不接收模型自由撰写的标题或正文。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictVisualModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class VisualFact(_StrictVisualModel):
    """视觉模型的短观察；certain 仍然只是模型判断，并非事实核验。"""

    text: str = Field(min_length=1, max_length=40)
    certainty: Literal["certain", "uncertain"]


class VisualSubject(VisualFact):
    text: str = Field(min_length=1, max_length=18)


class VisualFoodItem(_StrictVisualModel):
    """Coarse visual shapes/categories, never fine ingredient identification."""

    kind: Literal["fish", "leafy_vegetables", "grains", "sauce", "round_pieces", "block_pieces", "drink", "food"]
    color: Literal["green", "purple", "orange", "yellow", "white", "brown", "dark", "mixed", "unknown"]
    position: Literal["center", "left", "right", "top", "bottom", "unspecified"]
    certainty: Literal["certain", "uncertain"]


class ImageVisualFacts(_StrictVisualModel):
    image_id: str = Field(pattern=r"^img_(?:0|[1-9][0-9]*)$")
    category: Literal["food", "nature", "animal", "person", "object", "place", "other"]
    subject: VisualSubject
    observations: list[VisualFact] = Field(default_factory=list, max_length=2)
    food_items: list[VisualFoodItem] = Field(default_factory=list, max_length=3)


class VisualFactsBatch(_StrictVisualModel):
    images: list[ImageVisualFacts] = Field(min_length=1, max_length=20)
