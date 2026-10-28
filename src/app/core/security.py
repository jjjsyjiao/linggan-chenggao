"""API Key 校验与鉴权逻辑。"""

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


async def verify_api_key(x_api_key: str | None = Header(None, alias="X-API-Key")) -> str:
    """
    校验请求头中的 X-API-Key。
    若配置了 APP_API_KEYS 则必须携带且匹配；未配置时（开发）不强制校验。
    """
    settings = get_settings()
    valid_keys = settings.get_valid_api_keys()

    if not valid_keys:
        # 未配置合法 Key 时，仅开发环境允许无 Key 或任意 Key
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server misconfiguration: no API keys configured",
            )
        return x_api_key or "dev-no-key"

    if not x_api_key or x_api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return x_api_key
