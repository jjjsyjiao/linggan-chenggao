"""基于 Pydantic Settings 的配置管理，支持环境变量与 .env 分层加载。"""

import os
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    全局配置。环境变量前缀 APP_，优先级：环境变量 > .env > 默认值。
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "staging", "production"] = "development"
    port: int = 8072
    log_level: str = "INFO"
    # 日志目录，按小时轮转；app.log 为全部级别，error.log 仅 ERROR
    log_dir: str = "./logs"

    database_url: str = "sqlite+aiosqlite:///./app.db"
    database_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"

    llm_api_key: str = ""
    llm_provider: str = "aliyun"
    llm_model: str = "qwen-plus"
    llm_image_model: str = "qwen3-vl-plus"
    llm_base_url: str | None = None
    # 阿里云通义千问：cn / intl / finance
    llm_region: Literal["cn", "intl", "finance"] = "cn"
    llm_timeout: int = Field(120, gt=0, le=600)
    llm_retry_count: int = 3  # LLM 请求失败时的重试次数
    llm_max_concurrency: int = Field(3, ge=1, le=20)

    secret_key: str = "dev-secret-change-in-production"
    api_keys: str = ""  # 逗号分隔的合法 API Key，空表示不校验（仅开发）

    # 百度千帆搜索（AppBuilder）
    baidu_api_key: str = ""
    baidu_search_timeout: int = 30

    # 目录读取工具：若设置则仅允许列出该根目录下的路径，防目录穿越；空表示不限制
    tools_directory_read_root: str = ""

    # AI 应用输出数据目录（每次运行会在其下创建子目录，如小红书笔记临时图片等）
    data_output_dir: str = "./data/output"

    # 小红书笔记：多模态调用前图片统一压缩
    # 长边最大像素，0 表示不缩放仅按质量重编码
    xhs_image_max_size: int = Field(1024, ge=0, le=4096)
    # JPEG/WebP 质量 1–100，仅影响有损格式
    xhs_image_quality: int = 85
    # 单次请求允许上传的最大图片数量，默认 20，可通过 APP_XHS_MAX_IMAGES 覆盖
    xhs_max_images: int = Field(20, ge=1, le=20)
    xhs_max_image_bytes: int = Field(10 * 1024 * 1024, gt=0)
    xhs_max_total_bytes: int = Field(50 * 1024 * 1024, gt=0)
    xhs_max_image_pixels: int = Field(40_000_000, gt=0)
    xhs_max_concurrent_generations: int = Field(2, ge=1, le=20)
    xhs_generation_timeout: int = Field(600, gt=0, le=3600)
    # 有意隔离的离线联调模式，绝不伪装为真实 AI 产物；生产环境禁止。
    xhs_demo_mode: bool = False
    # CrewAI 执行超时时间（秒），默认 10 分钟
    crew_execution_timeout: int = Field(600, gt=0, le=3600)

    @model_validator(mode="before")
    @classmethod
    def fallback_api_keys_from_env(cls, data: Any) -> Any:
        """未配置 APP_ 前缀时，可用 QWEN_API_KEY / BAIDU_API_KEY 作为备用。"""
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if not (out.get("llm_api_key") or "").strip():
            out["llm_api_key"] = os.environ.get("QWEN_API_KEY", "").strip()
        if not (out.get("baidu_api_key") or "").strip():
            out["baidu_api_key"] = os.environ.get("BAIDU_API_KEY", "").strip()
        return out

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = ("DEBUG", "INFO", "WARNING", "ERROR")
        u = v.upper()
        if u not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return u

    @field_validator("xhs_image_quality")
    @classmethod
    def validate_xhs_image_quality(cls, v: int) -> int:
        if not 1 <= v <= 100:
            raise ValueError("xhs_image_quality must be between 1 and 100")
        return v

    @field_validator("llm_retry_count")
    @classmethod
    def validate_llm_retry_count(cls, v: int) -> int:
        if v < 0:
            raise ValueError("llm_retry_count must be >= 0")
        if v > 10:
            raise ValueError("llm_retry_count must be <= 10")
        return v

    def get_valid_api_keys(self) -> set[str]:
        """返回合法 API Key 集合。"""
        if not self.api_keys or not self.api_keys.strip():
            return set()
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    """获取单例配置，便于测试时覆盖。"""
    return Settings()
