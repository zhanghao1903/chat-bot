# Changelog

## Unreleased

### Added

- Default-disabled, administrator-governed weekday lunch/dinner automation with member opt-in,
  Shanghai-local scheduling, a 30-minute grace window, stable occurrences and at-most-once group
  delivery.
- Strict scheduled-food Writer output with one primary, two distinct alternatives, recent-primary
  exclusion, typed aggregate preferences and application-owned source/render validation.
- Tavily-backed read-only `web_search` and `web_fetch` with a separate five-call budget, opaque
  result IDs, URL/SSRF controls, bounded untrusted content and redacted usage audit.

- Bounded static Telegram media intake and OpenAI-compatible visual understanding that runs only
  after existing trigger eligibility, keeps image content untrusted, and stores no media binary.
- Deterministic 48-item Lezhi expression candidate set with transparent masters, Telegram WebP,
  light/dark previews, canonical semantic catalog, exact source traceability, and five avatar crops.
- LLM-owned text/sticker/composite/silence decisions from full conversation, relationship, memory,
  and vision context, with application-owned structured-output validation, enabled-catalog
  allowlisting, final mapping revalidation, relationship metadata, and consecutive-repeat bounds.
- Text-first two-component bundles, per-component uncertain-send suppression, and restart
  reconciliation without an online sticker-frequency metric or quota.
- Explicit operator-only catalog promotion and sticker-pack publication, plus one-shot default
  profile-photo apply bound to exact catalog/image/bot/authorization identity and Telegram API
  success without automated readback, retry, or rollback.
- Adaptive read-only Writer budget with three ordinary calls, auditable calls four and five only
  after novel evidence and a remaining gap, and a hard prohibition on a sixth call.

- Immutable `lezhi-v2.0` Character Bundle with complete nineteen-field source preservation, 37
  paired examples/evaluation cases, exact source traceability, and shared Trigger, Recognition,
  and Effector snapshot identity.
- Real-provider persona evaluation and fail-closed release gates with exact v1 rollback pins,
  bounded Telegram smoke verification, and redacted local release evidence.

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
- High-precision direct addressing through the Character Bundle formal name, plus semantic
  continuity for replies to the bot's latest confirmed group message within ten minutes and five
  subsequent human messages.
- Minimal trigger-evaluation audit records for final category, decision, reason, persona-name hit,
  and confirmed continuity anchor ID without extending raw-text retention.

### Changed

- Inbound persona replies may contain one text component followed by at most one enabled Lezhi
  sticker; scheduled food, control commands, tools, and other external writes remain single-effect.
- Sticker-bearing rate is offline evaluation context only. It does not decide pass/fail, change a
  valid Writer decision, create an online runtime metric, or impose a quota.

- Writer model completions are capped at eleven so independent context 3/5 and Web 0–5 budgets can
  share one deadline, 16 KiB admitted-result ceiling and reserved final completion without an
  unbounded loop.

- Writer can emit a bounded mood signal with text, sticker, or silence; media turns never
  contribute to global avatar mood state.
- Runtime and deployment templates keep vision, production expressions, and automatic avatar
  rotation disabled until their separate user-confirmation and Telegram verification gates pass.

- Compose persona releases now preserve the explicitly selected database file and named data
  volume, including deployments whose historical SQLite filename differs from the default.
- The production persona can be explicitly pinned to `lezhi-v2.0`; subjective memory remains
  snapshot-bound while persona-neutral observations remain available across v1/v2 transitions.

- Persona modes use the SQLite database for idempotency, audited model/tool runs, bounded raw
  message retention, and group-scoped derived recognition; fixed mode keeps its compatible
  delivery behavior.
- Docker and local configuration templates now expose persona, model, budget, retention, and
  memory-capability settings without embedding secrets or silently activating a persona.
- `persona_direct` now supports formal-name and recent-conversation responses while continuing to
  exclude unrelated proactive participation; `persona_full` keeps the existing 15-minute/five-
  human-message gate for unrelated ordinary messages.

### Security

- Automation, Tavily Web access and every group subscription remain disabled by default; group
  messages cannot create schedules, broaden URL scope, expose provider credentials or replay an
  uncertain Telegram effect.

- Models and group messages cannot upload assets, promote catalogs, expose Telegram asset IDs,
  change the bot profile, or expand read-only tool budgets beyond application-owned limits.
- Media downloads are bounded by bytes, pixels, dimensions, MIME and timeout; token-bearing URLs,
  raw pixels, prompts and provider bodies do not enter durable audits.

- Model-selected tools cannot override group/member scope, invoke external writes, or access
  credentials.
- Persistent member understanding remains disabled until a Telegram administrator successfully
  publishes the in-group disclosure; reset operations invalidate stale queued recognition.
- Logs and safe exceptions exclude Telegram/model credentials, prompts, tool payloads, and raw
  provider response bodies.
- Group text cannot teach trigger aliases or override the continuity window, trigger priority,
  Character Bundle, group boundary, or safety contract; ambiguous and failed continuity checks
  fall back to ordinary cadence or silence.

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
