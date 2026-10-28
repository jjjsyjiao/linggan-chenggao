"""LLM 工厂；仅在完整 Crew 流程需要时加载 CrewAI 适配器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.crews.llm.aliyun_llm import AliyunLLM

__all__ = ["AliyunLLM", "get_llm"]


def __getattr__(name: str):
    if name == "AliyunLLM":
        from app.crews.llm.aliyun_llm import AliyunLLM
        return AliyunLLM
    raise AttributeError(name)


def get_llm(
    provider: str | None = None,
    model: str | None = None,
    image_model: str | None = None, # 专门的多模态模型；优先使用显式入参，其次尝试从配置读取，最后使用默认值。
    **kwargs: object,
) -> AliyunLLM:
    """
    根据配置返回 LLM 实例。当前仅支持 aliyun。

    Args:
        provider: 不传则用 APP_LLM_PROVIDER
        model: 不传则用 APP_LLM_MODEL
        image_model: 专门的多模态模型；优先使用显式入参，其次尝试从配置读取，最后使用默认值。  qwen3-vl-plus
        **kwargs: 透传给 AliyunLLM（如 api_key、region、temperature、timeout、retry_count）

    Returns:
        AliyunLLM 实例（其他 provider 可在此扩展）
    """
    settings = get_settings()
    provider = (provider or settings.llm_provider).lower()
    if provider == "aliyun":
        llm_type = globals().get("AliyunLLM") or __getattr__("AliyunLLM")
        return llm_type(
            model=model or settings.llm_model,
            api_key=kwargs.get("api_key") or settings.llm_api_key,
            region=kwargs.get("region") or settings.llm_region,
            temperature=kwargs.get("temperature"),
            timeout=kwargs.get("timeout") if kwargs.get("timeout") is not None else settings.llm_timeout,
            retry_count=kwargs.get("retry_count") if kwargs.get("retry_count") is not None else settings.llm_retry_count,
            image_model=image_model or settings.llm_image_model,
            image_paths=kwargs.get("image_paths"),
        )
    raise ValueError(f"不支持的 LLM provider: {provider}，当前支持: aliyun")
