"""中间结果保存工具：在 Agent 执行过程中保存中间思考产物，供后续步骤使用。"""

from __future__ import annotations

import json
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, field_validator

from app.observability.logging import get_logger

logger = get_logger(__name__)


class IntermediateToolSchema(BaseModel):
    """中间结果保存工具的输入。"""

    intermediate_product: Any = Field(
        ...,
        description=(
            "需要保存的中间思考产物。"
            "支持任意类型：字符串、列表、字典等，会自动转换为字符串。"
            "例如：列表 ['a', 'b'] 会转为 'a\\nb'，字典会转为 JSON 字符串。"
        ),
    )

    @field_validator("intermediate_product", mode="before")
    @classmethod
    def convert_to_string(cls, v: Any) -> str:
        """将任意类型转为字符串：str 原样，list 用换行连接，dict 用 JSON，其余 str()。"""
        if isinstance(v, str):
            return v
        if isinstance(v, list):
            return "\n".join(str(item) for item in v)
        if isinstance(v, dict):
            try:
                return json.dumps(v, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                return str(v)
        return str(v)


class IntermediateTool(BaseTool):
    """
    中间结果保存工具。用于在 Agent 执行中保存中间思考产物，便于后续步骤使用。
    支持任意类型输入，自动转为字符串，无需手动转换。
    """

    name: str = "Save_Intermediate_Product_Tool"
    description: str = (
        "A tool that can be used to save intermediate thinking products "
        "during agent execution. "
        "\n\n"
        "✅ Supports any input type (string, list, dict, etc.) and automatically converts to string format. "
        "You can pass lists, dictionaries, or any other type directly - no need to convert manually. "
        "\n\n"
        "Examples: "
        "- String: 'my text' → saved as 'my text'"
        "- List: ['item1', 'item2'] → saved as 'item1\\nitem2'"
        "- Dict: {'key': 'value'} → saved as JSON string"
    )
    args_schema: type[BaseModel] = IntermediateToolSchema

    def _run(self, intermediate_product: str, **kwargs: Any) -> str:
        """保存中间思考产物，返回固定提示。"""
        logger.debug("intermediate_saved", length=len(intermediate_product))
        return "中间结果已保存，可以进行下一步 Thought"
