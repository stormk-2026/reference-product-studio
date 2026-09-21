import hashlib
import io
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from studio.repositories.db import identifier, now

MAX_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 20_000_000
MIME = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def decode(data: bytes, mime: str) -> Image.Image:
    if len(data) > MAX_BYTES or not data:
        raise ValueError("图片为空或超过 15 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
            if image.format not in MIME or MIME[image.format] != mime:
                raise ValueError("文件 MIME 与实际图片格式不匹配；仅支持 PNG/JPEG/WebP")
            if image.width * image.height > MAX_PIXELS or getattr(image, "n_frames", 1) != 1:
                raise ValueError("仅支持不超过 2000 万像素的静态图片")
            image.verify()
            image = Image.open(io.BytesIO(data))
            image.load()
            return ImageOps.exif_transpose(image).convert("RGBA")
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("无法安全解码此图片") from exc


def safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve() / "assets"):
        raise ValueError("资源路径非法")
    return path


def save_image(root: Path, image: Image.Image, source: str, fixture: bool, *, storage=None):
    from studio.config import Settings
    from studio.storage.backend import AssetStorage

    resource_id = identifier()
    stream = io.BytesIO()
    # Hash the sanitized PNG identically for both storage backends.
    image.save(stream, "PNG")
    content = stream.getvalue()
    storage = storage or AssetStorage(root, Settings(storage_dir=root))
    relative = storage.write(resource_id, content)
    return dict(
        id=resource_id,
        path=relative,
        sha256=hashlib.sha256(content).hexdigest(),
        format="PNG",
        width=image.width,
        height=image.height,
        bytes=len(content),
        source=source,
        created_at=now(),
        fixture=fixture,
    )
