"""OceanBase/MySQL 异步连接池（SQLAlchemy 2.0 + aiomysql）。"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.models.base import Base

_engine = None
_async_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.database_echo,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """依赖注入：获取异步 DB Session，用毕自动关闭。"""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """初始化表结构（开发/测试用；生产建议用 Alembic 迁移）。"""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
