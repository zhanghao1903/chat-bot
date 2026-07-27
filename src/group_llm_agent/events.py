from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TelegramTextMessage:
    event_id: str
    group_id: str
    message_id: str
    sender_id: str
    sender_display_name: str
    text: str
    timestamp: datetime
    mentioned_bot: bool = False
    raw_event_ref: str | None = None
