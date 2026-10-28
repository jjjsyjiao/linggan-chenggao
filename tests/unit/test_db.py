"""数据库客户端与模型的单元测试。"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.db.models.base import Base, TimestampMixin, gen_uuid


# ---------------------------------------------------------------------------
# models/base.py
# ---------------------------------------------------------------------------


class TestBase:
    def test_base_exists(self):
        assert Base is not None
        assert hasattr(Base, "metadata")


class TestGenUuid:
    def test_returns_string(self):
        uid = gen_uuid()
        assert isinstance(uid, str)
        assert len(uid) == 36  # uuid4 format: 8-4-4-4-12

    def test_unique(self):
        ids = {gen_uuid() for _ in range(100)}
        assert len(ids) == 100


class TestTimestampMixin:
    def test_has_fields(self):
        assert hasattr(TimestampMixin, "created_at")
        assert hasattr(TimestampMixin, "updated_at")


# ---------------------------------------------------------------------------
# clients/oceanbase_client.py
# ---------------------------------------------------------------------------


class TestOceanbaseClient:
    def test_get_engine(self):
        from app.db.clients.oceanbase_client import get_engine
        engine = get_engine()
        assert engine is not None

    def test_get_session_factory(self):
        from app.db.clients.oceanbase_client import get_session_factory
        factory = get_session_factory()
        assert factory is not None

    @pytest.mark.asyncio
    async def test_get_db(self):
        """测试 get_db 生成器能正常 yield session。"""
        from app.db.clients.oceanbase_client import get_db
        async for session in get_db():
            assert session is not None
            break  # 仅测试第一次 yield


# ---------------------------------------------------------------------------
# clients/file_client.py
# ---------------------------------------------------------------------------


class TestFileClient:
    @pytest.mark.asyncio
    async def test_write_and_read(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.db.clients.file_client.FILE_ROOT", Path(tmpdir).resolve()):
                from app.db.clients.file_client import write_file, read_file
                await write_file("test.txt", b"hello world")
                content = await read_file("test.txt")
                assert content == b"hello world"

    @pytest.mark.asyncio
    async def test_delete_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.db.clients.file_client.FILE_ROOT", Path(tmpdir).resolve()):
                from app.db.clients.file_client import write_file, delete_file
                await write_file("to_delete.txt", b"data")
                result = await delete_file("to_delete.txt")
                assert result is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.db.clients.file_client.FILE_ROOT", Path(tmpdir).resolve()):
                from app.db.clients.file_client import delete_file
                result = await delete_file("nonexistent.txt")
                assert result is False

    def test_safe_path_traversal(self):
        from app.db.clients.file_client import _safe_path
        with pytest.raises(ValueError, match="outside"):
            _safe_path("../../etc/passwd")

    def test_safe_path_valid(self):
        from app.db.clients.file_client import _safe_path
        p = _safe_path("subdir/file.txt")
        assert isinstance(p, Path)

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.db.clients.file_client.FILE_ROOT", Path(tmpdir).resolve()):
                from app.db.clients.file_client import write_file
                await write_file("sub/dir/file.txt", b"data")
                assert (Path(tmpdir) / "sub" / "dir" / "file.txt").exists()
