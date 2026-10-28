"""配置与安全单元测试。"""

import os
import pytest

from pydantic import ValidationError

from app.core.config import Settings, get_settings


class TestSettingsDefaults:
    def test_defaults(self, monkeypatch):
        # 清理可能覆盖默认值的环境变量
        for key in list(os.environ):
            if key.startswith("APP_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv("QWEN_API_KEY", raising=False)
        monkeypatch.delenv("BAIDU_API_KEY", raising=False)
        s = Settings(llm_api_key="k", _env_file=None)
        assert s.env == "development"
        assert s.port == 8072
        assert s.log_level == "INFO"

    def test_database_url_default(self, monkeypatch):
        for key in list(os.environ):
            if key.startswith("APP_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv("QWEN_API_KEY", raising=False)
        monkeypatch.delenv("BAIDU_API_KEY", raising=False)
        s = Settings(llm_api_key="k", _env_file=None)
        assert "sqlite" in s.database_url

    def test_xhs_defaults(self):
        s = Settings(llm_api_key="k")
        assert s.xhs_image_max_size == 1024
        assert s.xhs_image_quality == 85
        assert s.xhs_max_images == 20
        assert s.crew_execution_timeout == 600


class TestApiKeys:
    def test_empty(self):
        s = Settings(api_keys="", llm_api_key="k")
        assert s.get_valid_api_keys() == set()

    def test_single(self):
        s = Settings(api_keys="key1", llm_api_key="k")
        assert s.get_valid_api_keys() == {"key1"}

    def test_multiple(self):
        s = Settings(api_keys=" key1 , key2 ", llm_api_key="k")
        assert s.get_valid_api_keys() == {"key1", "key2"}

    def test_whitespace_only(self):
        s = Settings(api_keys="   ", llm_api_key="k")
        assert s.get_valid_api_keys() == set()


class TestValidators:
    def test_log_level_valid(self):
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "debug", "info"):
            s = Settings(log_level=level, llm_api_key="k")
            assert s.log_level == level.upper()

    def test_log_level_invalid(self):
        with pytest.raises(ValidationError):
            Settings(log_level="TRACE", llm_api_key="k")

    def test_xhs_image_quality_valid(self):
        s = Settings(xhs_image_quality=1, llm_api_key="k")
        assert s.xhs_image_quality == 1
        s = Settings(xhs_image_quality=100, llm_api_key="k")
        assert s.xhs_image_quality == 100

    def test_xhs_image_quality_invalid_low(self):
        with pytest.raises(ValidationError):
            Settings(xhs_image_quality=0, llm_api_key="k")

    def test_xhs_image_quality_invalid_high(self):
        with pytest.raises(ValidationError):
            Settings(xhs_image_quality=101, llm_api_key="k")

    def test_llm_retry_count_valid(self):
        s = Settings(llm_retry_count=0, llm_api_key="k")
        assert s.llm_retry_count == 0
        s = Settings(llm_retry_count=10, llm_api_key="k")
        assert s.llm_retry_count == 10

    def test_llm_retry_count_negative(self):
        with pytest.raises(ValidationError):
            Settings(llm_retry_count=-1, llm_api_key="k")

    def test_llm_retry_count_too_high(self):
        with pytest.raises(ValidationError):
            Settings(llm_retry_count=11, llm_api_key="k")


class TestIsProduction:
    def test_production(self):
        s = Settings(env="production", llm_api_key="k")
        assert s.is_production is True

    def test_development(self):
        s = Settings(env="development", llm_api_key="k")
        assert s.is_production is False

    def test_staging(self):
        s = Settings(env="staging", llm_api_key="k")
        assert s.is_production is False


class TestFallbackApiKeys:
    def test_fallback_qwen(self):
        env = os.environ.copy()
        os.environ["QWEN_API_KEY"] = "qwen-fallback"
        try:
            s = Settings(llm_api_key="")
            assert s.llm_api_key == "qwen-fallback"
        finally:
            os.environ.clear()
            os.environ.update(env)

    def test_fallback_baidu(self):
        env = os.environ.copy()
        os.environ["BAIDU_API_KEY"] = "baidu-fallback"
        try:
            s = Settings(llm_api_key="k", baidu_api_key="")
            assert s.baidu_api_key == "baidu-fallback"
        finally:
            os.environ.clear()
            os.environ.update(env)

    def test_explicit_takes_priority(self):
        env = os.environ.copy()
        os.environ["QWEN_API_KEY"] = "qwen-fallback"
        try:
            s = Settings(llm_api_key="explicit-key")
            assert s.llm_api_key == "explicit-key"
        finally:
            os.environ.clear()
            os.environ.update(env)


class TestGetSettings:
    def test_cached(self):
        a = get_settings()
        b = get_settings()
        assert a is b
