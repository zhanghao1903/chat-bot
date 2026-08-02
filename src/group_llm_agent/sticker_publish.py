from __future__ import annotations

from dataclasses import dataclass

from group_llm_agent.expression import ExpressionCatalog, ExpressionCatalogError, file_sha256
from group_llm_agent.expression_manage import TelegramStickerMapping
from group_llm_agent.platforms.telegram import TelegramBotApiClient
from group_llm_agent.telegram_multipart import TelegramMultipartTransport


@dataclass(frozen=True)
class StickerPublishRequest:
    owner_user_id: str
    sticker_set_name: str
    sticker_set_title: str
    approved_catalog_sha256: str


class StickerPackPublisher:
    """Explicit operator-only publisher; never reachable from Writer tools."""

    def __init__(
        self,
        *,
        telegram: TelegramBotApiClient,
        multipart: TelegramMultipartTransport,
    ) -> None:
        self.telegram = telegram
        self.multipart = multipart

    def publish(
        self,
        catalog: ExpressionCatalog,
        *,
        request: StickerPublishRequest,
    ) -> tuple[TelegramStickerMapping, ...]:
        if catalog.status != "approved" or catalog.digest != request.approved_catalog_sha256:
            raise ExpressionCatalogError("approved_catalog_snapshot_mismatch")
        approved = tuple(entry for entry in catalog.entries if entry.status == "approved")
        if not approved:
            raise ExpressionCatalogError("approved_catalog_empty")
        uploaded: list[tuple[str, str, str]] = []
        for entry in approved:
            path = (catalog.path.parent / entry.telegram_path).resolve()
            if file_sha256(path) != entry.telegram_sha256:
                raise ExpressionCatalogError("catalog_asset_digest_mismatch")
            file_id, unique_id = self.multipart.upload_sticker_file(
                owner_user_id=request.owner_user_id,
                content=path.read_bytes(),
                filename=f"{entry.semantic_id}.webp",
            )
            uploaded.append((entry.semantic_id, file_id, unique_id))
        self.telegram.create_new_sticker_set(
            owner_user_id=request.owner_user_id,
            name=request.sticker_set_name,
            title=request.sticker_set_title,
            stickers=[
                {
                    "sticker": file_id,
                    "format": "static",
                    "emoji_list": [entry.emoji],
                    "keywords": [entry.interaction_intent[:64]],
                }
                for entry, (_, file_id, _) in zip(approved, uploaded, strict=True)
            ],
        )
        actual_by_unique = {
            unique_id: file_id
            for file_id, unique_id in self.telegram.get_sticker_set(name=request.sticker_set_name)
        }
        if any(unique_id not in actual_by_unique for _, _, unique_id in uploaded):
            raise ExpressionCatalogError("published_sticker_identity_mismatch")
        return tuple(
            TelegramStickerMapping(
                semantic_id=semantic_id,
                file_id=actual_by_unique[unique_id],
                file_unique_id=unique_id,
            )
            for semantic_id, _, unique_id in uploaded
        )
