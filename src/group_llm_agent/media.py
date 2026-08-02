from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import Final

from PIL import Image, ImageOps, UnidentifiedImageError

from group_llm_agent.events import InboundMedia
from group_llm_agent.platforms.telegram import TelegramApiError, TelegramBotApiClient

ALLOWED_IMAGE_MIME_TYPES: Final = frozenset({"image/jpeg", "image/png", "image/webp"})


class MediaProcessingError(RuntimeError):
    """A redacted, application-owned media failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(f"media_category={category}")


@dataclass(frozen=True)
class MediaLimits:
    maximum_download_bytes: int = 8 * 1024 * 1024
    hard_maximum_download_bytes: int = 20 * 1024 * 1024
    maximum_pixels: int = 12_000_000
    maximum_source_edge: int = 4096
    maximum_model_edge: int = 1536
    maximum_model_bytes: int = 2 * 1024 * 1024

    def __post_init__(self) -> None:
        if not 0 < self.maximum_download_bytes <= self.hard_maximum_download_bytes:
            raise ValueError("invalid download byte limits")
        if (
            min(
                self.maximum_pixels,
                self.maximum_source_edge,
                self.maximum_model_edge,
                self.maximum_model_bytes,
            )
            <= 0
        ):
            raise ValueError("media limits must be positive")


@dataclass(frozen=True)
class NormalizedMedia:
    content: bytes
    mime_type: str
    width: int
    height: int
    sha256: str


class TelegramMediaLoader:
    def __init__(
        self,
        *,
        client: TelegramBotApiClient,
        limits: MediaLimits | None = None,
        timeout_seconds: int = 15,
    ) -> None:
        self.client = client
        self.limits = limits or MediaLimits()
        self.timeout_seconds = timeout_seconds

    def load(self, media: InboundMedia) -> NormalizedMedia:
        self._validate_declared_metadata(media)
        try:
            telegram_file = self.client.get_file(file_id=media.file_id)
            declared_size = telegram_file.file_size
            if declared_size is not None and declared_size > self.limits.maximum_download_bytes:
                raise MediaProcessingError("declared_too_large")
            raw = self.client.download_file(
                file_path=telegram_file.file_path,
                maximum_bytes=self.limits.maximum_download_bytes,
                timeout_seconds=self.timeout_seconds,
            )
        except TelegramApiError as exc:
            raise MediaProcessingError(f"telegram_{exc.category}") from None
        try:
            return normalize_image(raw, expected_mime_type=media.mime_type, limits=self.limits)
        finally:
            raw = b""

    def _validate_declared_metadata(self, media: InboundMedia) -> None:
        if media.is_animated or media.is_video:
            raise MediaProcessingError("unsupported_dynamic_media")
        if media.mime_type not in ALLOWED_IMAGE_MIME_TYPES:
            raise MediaProcessingError("unsupported_mime")
        if media.file_size is not None and media.file_size > self.limits.maximum_download_bytes:
            raise MediaProcessingError("declared_too_large")
        if media.width is not None and media.height is not None:
            if max(media.width, media.height) > self.limits.maximum_source_edge:
                raise MediaProcessingError("declared_dimensions_too_large")
            if media.width * media.height > self.limits.maximum_pixels:
                raise MediaProcessingError("declared_pixels_too_large")


def normalize_image(
    raw: bytes,
    *,
    expected_mime_type: str | None,
    limits: MediaLimits | None = None,
) -> NormalizedMedia:
    active_limits = limits or MediaLimits()
    if not raw:
        raise MediaProcessingError("empty_file")
    if len(raw) > active_limits.maximum_download_bytes:
        raise MediaProcessingError("download_too_large")
    try:
        with Image.open(BytesIO(raw)) as probe:
            probe.verify()
        with Image.open(BytesIO(raw)) as opened:
            source_format = str(opened.format or "").upper()
            actual_mime = _mime_for_format(source_format)
            if actual_mime is None:
                raise MediaProcessingError("unsupported_format")
            if expected_mime_type is not None and expected_mime_type != actual_mime:
                raise MediaProcessingError("mime_mismatch")
            width, height = opened.size
            if width <= 0 or height <= 0:
                raise MediaProcessingError("invalid_dimensions")
            if max(width, height) > active_limits.maximum_source_edge:
                raise MediaProcessingError("dimensions_too_large")
            if width * height > active_limits.maximum_pixels:
                raise MediaProcessingError("pixels_too_large")
            image = ImageOps.exif_transpose(opened)
            if image is None:
                raise MediaProcessingError("invalid_image")
            has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
            image = image.convert("RGBA" if has_alpha else "RGB")
            image.thumbnail(
                (active_limits.maximum_model_edge, active_limits.maximum_model_edge),
                Image.Resampling.LANCZOS,
            )
            content, output_mime = _encode_bounded(image, active_limits)
            return NormalizedMedia(
                content=content,
                mime_type=output_mime,
                width=image.width,
                height=image.height,
                sha256=sha256(content).hexdigest(),
            )
    except MediaProcessingError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
        raise MediaProcessingError("invalid_image") from None


def _encode_bounded(image: Image.Image, limits: MediaLimits) -> tuple[bytes, str]:
    current = image.copy()
    for _ in range(6):
        buffer = BytesIO()
        if current.mode == "RGBA":
            current.save(buffer, format="PNG", optimize=True)
            mime_type = "image/png"
        else:
            current.save(buffer, format="JPEG", quality=88, optimize=True, progressive=True)
            mime_type = "image/jpeg"
        content = buffer.getvalue()
        if len(content) <= limits.maximum_model_bytes:
            return content, mime_type
        next_size = (max(1, current.width * 3 // 4), max(1, current.height * 3 // 4))
        if next_size == current.size:
            break
        current = current.resize(next_size, Image.Resampling.LANCZOS)
    raise MediaProcessingError("normalized_too_large")


def _mime_for_format(value: str) -> str | None:
    return {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
    }.get(value)
