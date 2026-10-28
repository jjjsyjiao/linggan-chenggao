"""API Key 校验逻辑的单元测试。"""

import pytest
from unittest.mock import patch, MagicMock

from fastapi import HTTPException

from app.core.security import verify_api_key


def _mock_settings(api_keys: str = "", env: str = "development"):
    s = MagicMock()
    s.api_keys = api_keys
    s.env = env
    s.is_production = (env == "production")
    valid = set()
    if api_keys.strip():
        valid = {k.strip() for k in api_keys.split(",") if k.strip()}
    s.get_valid_api_keys.return_value = valid
    return s


class TestVerifyApiKey:
    @pytest.mark.asyncio
    async def test_valid_key(self):
        with patch("app.core.security.get_settings", return_value=_mock_settings("key1,key2")):
            result = await verify_api_key("key1")
            assert result == "key1"

    @pytest.mark.asyncio
    async def test_invalid_key(self):
        with patch("app.core.security.get_settings", return_value=_mock_settings("key1,key2")):
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key("wrong-key")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_key_when_required(self):
        with patch("app.core.security.get_settings", return_value=_mock_settings("key1")):
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(None)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_keys_configured_dev(self):
        with patch("app.core.security.get_settings", return_value=_mock_settings("", "development")):
            result = await verify_api_key(None)
            assert result == "dev-no-key"

    @pytest.mark.asyncio
    async def test_no_keys_configured_dev_with_key(self):
        with patch("app.core.security.get_settings", return_value=_mock_settings("", "development")):
            result = await verify_api_key("any-key")
            assert result == "any-key"

    @pytest.mark.asyncio
    async def test_no_keys_configured_production(self):
        with patch("app.core.security.get_settings", return_value=_mock_settings("", "production")):
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(None)
            assert exc_info.value.status_code == 500
