"""多模态调用前图片统一压缩：按标准分辨率与质量重编码。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Tuple
import os

from app.observability.logging import get_logger

logger = get_logger(__name__)

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None  # type: ignore[misc, assignment]


def compress_image_to_standard(
    image_path: Path,
    max_size: int,
    quality: int,
    *,
    output_path: Path | None = None,
) -> Path:
    """将图片按标准分辨率压缩后写入目标路径。

    若 max_size > 0，则按长边不超过 max_size 等比缩放；否则仅按质量重编码。
    输出格式统一为 JPEG（无透明通道）或 PNG（有透明通道时保留）。

    Args:
        image_path: 原始图片路径。
        max_size: 长边最大像素，0 表示不缩放。
        quality: JPEG/WebP 质量 1–100。
        output_path: 输出路径；不传则覆盖原文件（先写临时文件再替换）。

    Returns:
        压缩后的图片路径（与 output_path 一致或原路径）。

    Raises:
        FileNotFoundError: 原文件不存在。
        ValueError: 无法识别的图片格式或 PIL 未安装。
    """
    if Image is None:
        raise ValueError("图片压缩需要安装 Pillow，请执行: pip install Pillow")

    path = Path(image_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"图片不存在: {path}")

    out = Path(output_path).resolve() if output_path else path
    out.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(path) as source:
        im = _normalize_mode(ImageOps.exif_transpose(source))
        w, h = im.size

        if max_size > 0 and max(w, h) > max_size:
            im, (w, h) = _resize_long_edge(im, max_size)

        # 有透明通道则 PNG，否则 JPEG 以控制质量与体积
        use_png = im.mode == "RGBA"
        save_kw: dict = {}
        if use_png:
            fmt, ext = "PNG", ".png"
        else:
            fmt, ext = "JPEG", ".jpg"
            save_kw["quality"] = min(100, max(1, quality))
            save_kw["optimize"] = True

        if not output_path:
            # 覆盖原文件：先写临时文件再替换，扩展名可能变为 .jpg/.png
            suffix = ext
            fd, tmp = tempfile.mkstemp(suffix=suffix, prefix="xhs_compress_", dir=path.parent)
            os.close(fd)
            try:
                tmp_path = Path(tmp)
                im.save(tmp_path, fmt, **save_kw)
                dest = path.with_suffix(suffix)
                if path.resolve() != dest.resolve():
                    path.unlink(missing_ok=True)
                tmp_path.replace(dest)
            finally:
                Path(tmp).unlink(missing_ok=True)
            return path.with_suffix(suffix)

        out_str = str(out)
        if not out_str.lower().endswith((".jpg", ".jpeg", ".png")):
            out = out.with_suffix(ext)
        im.save(out, fmt, **save_kw)
        return out


def _normalize_mode(im: "Image.Image") -> "Image.Image":
    """转为 RGB 或 RGBA，便于统一保存为 JPEG/PNG。"""
    if im.mode in ("RGB", "RGBA", "L"):
        return im
    if im.mode == "P" and getattr(im, "palette", None):
        try:
            im = im.convert("RGBA")
        except Exception:
            im = im.convert("RGB")
        return im
    return im.convert("RGB")


def _resize_long_edge(im: "Image.Image", max_size: int) -> Tuple["Image.Image", Tuple[int, int]]:
    """按长边等比缩放到 max_size，返回新图和 (w, h)。"""
    w, h = im.size
    if w >= h:
        nw = max_size
        nh = max(1, round(h * max_size / w))
    else:
        nh = max_size
        nw = max(1, round(w * max_size / h))
    resized = im.resize((nw, nh), getattr(Image, "LANCZOS", Image.Resampling.LANCZOS))
    return resized, (nw, nh)
