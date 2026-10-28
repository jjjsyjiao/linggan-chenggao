"""AddImageToolLocal：本地图片加载工具。

参考 CrewAI 的 AddImageTool，在工具内部读取本地文件并按项目统一规则压缩，
再转为 Base64 Data URL 后返回，便于多模态 LLM 使用。
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.core.image_utils import compress_image_to_standard
from app.core.config import get_settings
from app.observability.logging import get_logger

logger = get_logger(__name__)


class AddImageToolLocalSchema(BaseModel):
    """与 CrewAI AddImageTool 的 schema 保持一致。"""

    image_url: str = Field(
        ...,
        description="The URL or local file path of the image to add.",
    )

#  编码函数： 将本地文件转换为 Base64 编码的字符串
def _encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def _local_path_to_base64_data_url(image_url: str) -> str | None:
    """将本地图片路径读取为 Base64 Data URL。

    处理流程：
    1. 展开用户目录并解析为绝对路径；
    2. 检查文件是否存在；
    3. 使用项目统一的 `compress_image_to_standard` 进行压缩；
    4. 将压缩后的图片读取为字节并编码为 Base64；
    5. 根据扩展名推断 MIME 类型并拼接为 data URL。
    """
    path = Path(image_url).expanduser().resolve()
    root = get_settings().tools_directory_read_root
    if root and not path.is_relative_to(Path(root).expanduser().resolve()):
        return "拒绝读取请求图片目录之外的文件"
    logger.debug("AddImageToolLocal.resolve_path", image_url=image_url, resolved=str(path))

    if not path.is_file():
        msg = f"图片文件不存在: {image_url}"
        logger.warning("AddImageToolLocal.file_not_found", image_url=image_url)
        return msg

    try:
        # 统一压缩到较小尺寸，兼顾质量与体积
        
        b64 = _encode_image(path)

        suffix = path.suffix.lower()
        mime = "image/jpeg"
        if suffix == ".png":
            mime = "image/png"
        elif suffix == ".gif":
            mime = "image/gif"
        elif suffix == ".webp":
            mime = "image/webp"
        elif suffix == ".bmp":
            mime = "image/bmp"

        data_url = f"data:{mime};base64,{b64}"
        logger.info(
            "AddImageToolLocal.encode_success",
            b64_len=len(b64),
            mime=mime,
        )
        return data_url
    except Exception as exc:  # noqa: BLE001
        logger.exception("AddImageToolLocal.encode_error", error=str(exc))
        return f"图片处理失败: {exc}"


class AddImageToolLocal(BaseTool):
    """将本地图片加入上下文的工具。

    读取本地文件并按统一规则压缩后转为 Base64 Data URL 返回，
    返回格式与 CrewAI 的 AddImageTool 一致，可直接被多模态 LLM 使用。
    """

    # 这样 LLM 在 ReAct 输出中提到该工具时，_normalize_multimodal_tool_result 才能正确识别。
    name: str = "add_image_to_content_local"
    description: str = (
        "Load a local image file from the given path, compress it to a standard size and quality, "
        "and convert it to a base64 data URL format that can be processed by multimodal models. "
        "If an HTTP/HTTPS URL is provided, it will be returned as-is (no local loading)."
    )
    args_schema: type[BaseModel] = AddImageToolLocalSchema

    def _run(self, image_url: str, **kwargs: Any) -> str:
        """主运行入口。

        - 若为 http(s) URL：直接返回原始 URL；
        - 若为本地路径：读取并转为 Base64 Data URL；
        - 若读取或压缩失败：返回错误信息字符串。
        """
        url = image_url.strip()
        logger.debug("AddImageToolLocal.run", image_url=url)

        if url.startswith("http://") or url.startswith("https://"):
            # 已是远程 URL，交由上游工具处理
            logger.debug("AddImageToolLocal.remote_url", url=url)
            return url

        data_url = _local_path_to_base64_data_url(url)
        # data_url 为 None 的情况理论上只在异常中返回，这里做兜底
        return data_url if data_url is not None else url

