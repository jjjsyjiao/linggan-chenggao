"""健康检查：/health/live（存活）、/health/ready（就绪）。"""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_request_id
from app.core.config import get_settings
from app.schemas.common import ApiResponse

router = APIRouter()


@router.get("/live")
async def liveness() -> dict[str, str]:
    """K8s liveness：仅校验进程存活。"""
    return {"status": "ok"}


@router.get("/ready", response_model=ApiResponse[dict])
async def readiness(request_id: str = Depends(get_request_id)) -> ApiResponse[dict]:
    """K8s readiness：当前仅返回应用状态；后续接入 DB/Redis 后再做真实探测。"""
    settings = get_settings()
    return ApiResponse(
        code=0,
        message="ok",
        data={"env": settings.env},
        request_id=request_id,
    )
