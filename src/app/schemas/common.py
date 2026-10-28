"""通用 Response 契约：code、message、request_id。"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """统一错误响应体。"""

    code: int = Field(..., description="业务/HTTP 错误码")
    message: str = Field(..., description="可展示给用户的信息")
    request_id: str = Field("", description="便于日志关联的请求 ID")


class ApiResponse(BaseModel, Generic[T]):
    """统一成功响应体。"""

    code: int = Field(0, description="0 表示成功")
    message: str = Field("ok", description="提示信息")
    data: T | None = Field(None, description="业务数据")
    request_id: str = Field("", description="请求 ID")
