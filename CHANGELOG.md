# Changelog

## 0.1.0 - 2026-07-27

### Added

- Verified Telegram Bot API long-polling startup for one configured group.
- Ordinary group-text normalization with group, sender, and message identifiers.
- Exact `1 → 1` reply behavior with self/bot protection and durable at-most-once delivery.
- Redacted startup, polling, parsing, and reply-failure handling.
- Docker Compose deployment and service-management assets under `deploy/`.
- Deterministic configuration, adapter, transport, runtime, storage, and startup tests.

### Fixed

- Reject unsafe Telegram token characters without echoing credentials in startup output.
- Translate URL, connection, and response-body timeout failures into redacted polling errors that follow the configured retry path.

### Limitations

- No LLM, moderation, media, private chat, multi-group UI, or message-content persistence.
- A real Telegram group smoke test requires operator-owned credentials and permissions.
