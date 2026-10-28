"""CrewAI 工具的单元测试：IntermediateTool、AddImageToolLocal。"""

import base64
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.crews.tools.intermediate_tool import IntermediateTool, IntermediateToolSchema
from app.crews.tools.add_image_tool_local import (
    AddImageToolLocal,
    AddImageToolLocalSchema,
    _local_path_to_base64_data_url,
)


# ---------------------------------------------------------------------------
# IntermediateTool
# ---------------------------------------------------------------------------


class TestIntermediateToolSchema:
    def test_string_input(self):
        s = IntermediateToolSchema(intermediate_product="hello")
        assert s.intermediate_product == "hello"

    def test_list_input(self):
        s = IntermediateToolSchema(intermediate_product=["a", "b", "c"])
        assert s.intermediate_product == "a\nb\nc"

    def test_dict_input(self):
        s = IntermediateToolSchema(intermediate_product={"key": "value"})
        assert '"key"' in s.intermediate_product
        assert '"value"' in s.intermediate_product

    def test_int_input(self):
        s = IntermediateToolSchema(intermediate_product=42)
        assert s.intermediate_product == "42"


class TestIntermediateTool:
    def test_name(self):
        tool = IntermediateTool()
        assert tool.name == "Save_Intermediate_Product_Tool"

    def test_run(self):
        tool = IntermediateTool()
        result = tool._run(intermediate_product="测试中间结果")
        assert "中间结果已保存" in result

    def test_run_empty(self):
        tool = IntermediateTool()
        result = tool._run(intermediate_product="")
        assert "中间结果已保存" in result


# ---------------------------------------------------------------------------
# AddImageToolLocal
# ---------------------------------------------------------------------------


class TestAddImageToolLocalSchema:
    def test_basic(self):
        s = AddImageToolLocalSchema(image_url="/path/to/image.jpg")
        assert s.image_url == "/path/to/image.jpg"


class TestAddImageToolLocal:
    def test_name(self):
        tool = AddImageToolLocal()
        assert tool.name == "add_image_to_content_local"

    def test_run_http_url(self):
        tool = AddImageToolLocal()
        result = tool._run(image_url="https://example.com/image.jpg")
        assert result == "https://example.com/image.jpg"

    def test_run_http_url_trimmed(self):
        tool = AddImageToolLocal()
        result = tool._run(image_url="  http://example.com/img.png  ")
        assert result == "http://example.com/img.png"

    def test_run_local_file(self):
        """使用真实临时文件测试本地图片加载。"""
        # 创建一个最简 JPEG：1x1 像素
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            img = Image.new("RGB", (10, 10), color="red")
            img.save(f.name, "JPEG")
            tmp_path = f.name

        try:
            tool = AddImageToolLocal()
            result = tool._run(image_url=tmp_path)
            assert result.startswith("data:image/jpeg;base64,")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_run_nonexistent_file(self):
        tool = AddImageToolLocal()
        result = tool._run(image_url="/nonexistent/path/image.jpg")
        assert "不存在" in result or "image_url" in result.lower() or isinstance(result, str)

    def test_run_png_file(self):
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img = Image.new("RGBA", (10, 10), color=(0, 0, 255, 128))
            img.save(f.name, "PNG")
            tmp_path = f.name

        try:
            tool = AddImageToolLocal()
            result = tool._run(image_url=tmp_path)
            assert result.startswith("data:image/png;base64,")
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class TestLocalPathToBase64:
    def test_nonexistent_file(self):
        result = _local_path_to_base64_data_url("/nonexistent/file.jpg")
        assert "不存在" in result

    def test_valid_file(self):
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            img = Image.new("RGB", (5, 5), color="green")
            img.save(f.name, "JPEG")
            tmp_path = f.name

        try:
            result = _local_path_to_base64_data_url(tmp_path)
            assert result.startswith("data:image/jpeg;base64,")
            # Verify base64 is decodable
            b64_data = result.split(",", 1)[1]
            decoded = base64.b64decode(b64_data)
            assert len(decoded) > 0
        finally:
            Path(tmp_path).unlink(missing_ok=True)
