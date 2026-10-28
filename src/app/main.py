"""框架入口：FastAPI 初始化、中间件、全局异常处理、健康检查与 API 挂载。"""

from uuid import uuid4

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1 import health
from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.upload_limits import UploadBodyLimitMiddleware
from app.observability.http_trace import http_trace_middleware
from app.observability.logging import get_logger, set_request_id, get_request_id
from app.schemas.common import ErrorDetail

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化日志与配置，关闭时清理。"""
    settings = get_settings()
    from app.observability.logging import configure_logging

    configure_logging(settings.log_level, settings.log_dir)
    logger.info("application_started", env=settings.env, port=settings.port)
    yield
    logger.info("application_shutdown")


def create_application() -> FastAPI:
    from slowapi import Limiter

    settings = get_settings()
    limiter = Limiter(
        key_func=lambda request: request.client.host if request.client else "unknown"
    )

    app = FastAPI(
        title="Enterprise AI App",
        description="企业级生成式 AI 应用 Web 服务框架",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.env != "production" else None,
        redoc_url="/redoc" if settings.env != "production" else None,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(UploadBodyLimitMiddleware, max_bytes=settings.xhs_max_total_bytes + 1024 * 1024, max_concurrent=settings.xhs_max_concurrent_generations)

    # 后注册的先执行：request_id 先注册，trace 后注册，故 trace 先执行，request_id 可读到 trace_id
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = (
            request.headers.get("X-Request-ID")
            or getattr(request.state, "trace_id", None)
            or str(uuid4())
        )
        set_request_id(rid)
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        """Trace 中间件：设置 trace_id/span_id，统一打印请求参数与返回结果（OpenTracing 兼容）。"""
        return await http_trace_middleware(request, call_next)

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        rid = getattr(request.state, "request_id", None) or get_request_id() or ""
        logger.exception("unhandled_exception", request_id=rid, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=ErrorDetail(code=500, message="Internal server error", request_id=rid).model_dump(),
        )

    from fastapi import HTTPException

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        rid = getattr(request.state, "request_id", None) or get_request_id() or ""
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content=ErrorDetail(
            code=exc.status_code,
            message=str(exc.detail) if exc.detail is not None else "",
            request_id=rid,
        ).model_dump(),
        )

    app.include_router(health.router, prefix="/health", tags=["health"])
    app.include_router(api_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    return app


app = create_application()
