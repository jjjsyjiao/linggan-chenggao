"""SQLAlchemy 声明式 Base 与公共字段。"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """声明式基类。"""

    pass


def gen_uuid() -> str:
    return str(uuid4())


class TimestampMixin:
    """创建/更新时间混入。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
