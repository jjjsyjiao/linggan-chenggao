"""本地文件客户端：路径隔离、异步 IO、防目录穿越。"""

import os
from pathlib import Path

import aiofiles

# 根目录锁定，防止目录穿越
FILE_ROOT = Path(os.environ.get("APP_FILE_ROOT", "./data/files")).resolve()


def _safe_path(relative_path: str) -> Path:
    """将相对路径解析为绝对路径，并确保在 FILE_ROOT 下。"""
    p = (FILE_ROOT / relative_path).resolve()
    if not str(p).startswith(str(FILE_ROOT)):
        raise ValueError("path outside allowed root")
    return p


async def read_file(relative_path: str) -> bytes:
    """异步读取文件。"""
    path = _safe_path(relative_path)
    async with aiofiles.open(path, "rb") as f:
        return await f.read()


async def write_file(relative_path: str, content: bytes) -> None:
    """异步写入文件，父目录不存在则创建。"""
    path = _safe_path(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "wb") as f:
        await f.write(content)


async def delete_file(relative_path: str) -> bool:
    """删除文件，不存在则返回 False。"""
    path = _safe_path(relative_path)
    if path.exists() and path.is_file():
        path.unlink()
        return True
    return False
