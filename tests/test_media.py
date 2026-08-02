from __future__ import annotations

import unittest
from io import BytesIO
from unittest.mock import Mock

from PIL import Image

from group_llm_agent.events import InboundMedia, MediaKind
from group_llm_agent.media import (
    MediaLimits,
    MediaProcessingError,
    TelegramMediaLoader,
    normalize_image,
)
from group_llm_agent.platforms.telegram import TelegramFile


def _image_bytes(*, image_format: str = "PNG", size: tuple[int, int] = (40, 20)) -> bytes:
    image = Image.new("RGBA", size, (20, 80, 160, 128))
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


class MediaTests(unittest.TestCase):
    def test_normalizes_and_strips_metadata(self) -> None:
        normalized = normalize_image(
            _image_bytes(),
            expected_mime_type="image/png",
            limits=MediaLimits(maximum_model_edge=24),
        )

        self.assertEqual("image/png", normalized.mime_type)
        self.assertEqual((24, 12), (normalized.width, normalized.height))
        self.assertEqual(64, len(normalized.sha256))
        with Image.open(BytesIO(normalized.content)) as reopened:
            self.assertEqual((24, 12), reopened.size)
            self.assertNotIn("exif", reopened.info)

    def test_rejects_mime_mismatch_damage_and_pixel_limits(self) -> None:
        cases = (
            (
                lambda: normalize_image(_image_bytes(), expected_mime_type="image/jpeg"),
                "mime_mismatch",
            ),
            (
                lambda: normalize_image(b"not-an-image", expected_mime_type="image/png"),
                "invalid_image",
            ),
            (
                lambda: normalize_image(
                    _image_bytes(size=(100, 100)),
                    expected_mime_type="image/png",
                    limits=MediaLimits(maximum_pixels=1000),
                ),
                "pixels_too_large",
            ),
        )
        for invoke, category in cases:
            with self.subTest(category=category), self.assertRaises(MediaProcessingError) as caught:
                invoke()
            self.assertEqual(category, caught.exception.category)

    def test_declared_oversize_does_not_call_telegram(self) -> None:
        client = Mock()
        loader = TelegramMediaLoader(
            client=client,
            limits=MediaLimits(maximum_download_bytes=100),
        )
        media = InboundMedia(
            kind=MediaKind.PHOTO,
            file_id="secret-file-id",
            file_unique_id="safe-unique",
            mime_type="image/jpeg",
            file_size=101,
        )

        with self.assertRaises(MediaProcessingError) as caught:
            loader.load(media)

        self.assertEqual("declared_too_large", caught.exception.category)
        client.get_file.assert_not_called()
        self.assertNotIn(media.file_id, str(caught.exception))

    def test_loader_uses_get_file_and_normalizes_bytes(self) -> None:
        client = Mock()
        content = _image_bytes()
        client.get_file.return_value = TelegramFile(
            file_path="photos/file.png", file_size=len(content)
        )
        client.download_file.return_value = content
        loader = TelegramMediaLoader(client=client)
        media = InboundMedia(
            kind=MediaKind.PHOTO,
            file_id="opaque",
            file_unique_id="safe-unique",
            mime_type="image/png",
        )

        normalized = loader.load(media)

        self.assertEqual("image/png", normalized.mime_type)
        client.get_file.assert_called_once_with(file_id="opaque")
        self.assertNotIn("opaque", repr(normalized))


if __name__ == "__main__":
    unittest.main()
