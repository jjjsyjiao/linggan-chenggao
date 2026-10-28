"""图片压缩工具的单元测试。"""

import tempfile
from pathlib import Path

import pytest


try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from app.core.image_utils import compress_image_to_standard


def _create_test_image(path: Path, size: tuple = (200, 150), mode: str = "RGB", fmt: str = "JPEG"):
    """创建测试用图片文件。"""
    if not HAS_PIL:
        pytest.skip("Pillow not installed")
    img = Image.new(mode, size, color="red")
    img.save(str(path), fmt)
    return path


@pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
class TestCompressImageToStandard:
    def test_no_resize_quality_only(self):
        """max_size=0 时仅重编码不缩放。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "test.jpg"
            _create_test_image(src, size=(100, 80))

            result = compress_image_to_standard(src, max_size=0, quality=85)
            assert result.exists()
            with Image.open(result) as im:
                assert im.size == (100, 80)

    def test_resize_large_image(self):
        """长边超过 max_size 时应等比缩放。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "big.jpg"
            _create_test_image(src, size=(2000, 1500))

            result = compress_image_to_standard(src, max_size=500, quality=85)
            assert result.exists()
            with Image.open(result) as im:
                w, h = im.size
                assert max(w, h) <= 500

    def test_resize_tall_image(self):
        """竖版图片长边也应缩放。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "tall.jpg"
            _create_test_image(src, size=(800, 1600))

            result = compress_image_to_standard(src, max_size=400, quality=85)
            with Image.open(result) as im:
                assert max(im.size) <= 400

    def test_small_image_no_resize(self):
        """小于 max_size 的图片不缩放。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "small.jpg"
            _create_test_image(src, size=(50, 50))

            result = compress_image_to_standard(src, max_size=500, quality=85)
            with Image.open(result) as im:
                assert im.size == (50, 50)

    def test_output_to_different_path(self):
        """指定 output_path 时保存到目标路径。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "input.jpg"
            out = Path(tmpdir) / "output.jpg"
            _create_test_image(src, size=(100, 100))

            result = compress_image_to_standard(src, max_size=0, quality=50, output_path=out)
            assert result.exists()
            assert "output" in str(result)

    def test_rgba_to_png(self):
        """RGBA 图片应保存为 PNG。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "rgba.png"
            _create_test_image(src, size=(100, 100), mode="RGBA", fmt="PNG")

            result = compress_image_to_standard(src, max_size=0, quality=85)
            assert result.suffix.lower() == ".png"

    def test_file_not_found(self):
        """不存在的文件应抛出 FileNotFoundError。"""
        with pytest.raises(FileNotFoundError):
            compress_image_to_standard(Path("/nonexistent/image.jpg"), max_size=0, quality=85)

    def test_quality_clamping(self):
        """质量参数应被正确限制。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "test.jpg"
            _create_test_image(src, size=(50, 50))
            # quality=200 should be clamped to 100
            result = compress_image_to_standard(src, max_size=0, quality=200)
            assert result.exists()

    def test_palette_mode_conversion(self):
        """P 模式图片应正确转换。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "palette.png"
            img = Image.new("P", (50, 50))
            img.save(str(src), "PNG")

            result = compress_image_to_standard(src, max_size=0, quality=85)
            assert result.exists()

    def test_l_mode(self):
        """灰度图应正确处理。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "gray.jpg"
            _create_test_image(src, size=(50, 50), mode="L")

            result = compress_image_to_standard(src, max_size=0, quality=85)
            assert result.exists()
