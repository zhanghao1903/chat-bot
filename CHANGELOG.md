# Changelog

## Unreleased

### Added

- Original `lezhi-v1.0` Character Bundle with one immutable Trigger, Recognition, and Effector
  snapshot, 15 original examples, and 22 fixed evaluation cases.
- Explicit `persona_direct` and `persona_full` modes while preserving `fixed` as the default and
  rollback path.
- Bounded writer effector with at most three model calls, two read-only context tools, one
  external effect, and OpenAI-compatible structured model transport.
- Selective contextual participation with a hard minimum of 15 minutes and five human messages.
- Group-scoped recent-message context, durable member recognition, confidence decay, revision,
  reset generations, and background retry/lease recovery.
- Public memory enable/disable and member/group reset commands with live Telegram administrator
  authorization.
- Production persona evaluation carrier, aggregate verification matrix, deployment guidance, and
  exact bundle integrity configuration.

### Changed

- Persona modes use the SQLite database for idempotency, audited model/tool runs, bounded raw
  message retention, and group-scoped derived recognition; fixed mode keeps its compatible
  delivery behavior.
- Docker and local configuration templates now expose persona, model, budget, retention, and
  memory-capability settings without embedding secrets or silently activating a persona.

### Security

- Model-selected tools cannot override group/member scope, invoke external writes, or access
  credentials.
- Persistent member understanding remains disabled until a Telegram administrator successfully
  publishes the in-group disclosure; reset operations invalidate stale queued recognition.
- Logs and safe exceptions exclude Telegram/model credentials, prompts, tool payloads, and raw
  provider response bodies.

### Limitations

- Provider-specific 22-case persona scoring and a real Telegram persona smoke require
  operator-selected model credentials, group authorization, and explicit external execution.
- Only one configured public Telegram group, text messages, one bundled persona, and an
  OpenAI-compatible model protocol are supported in this phase.

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
