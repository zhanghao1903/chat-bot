# Design: Telegram 群聊基础骨架 0.1

- Lifecycle phase: F2 Design
- Status: Accepted for implementation
- Requirements source: `docs/feature/telegram-group-v0-1/requirements.md`
- Requirements commit: `dc620c1023a3cbadc5138036553ea8284f56ba70`
- Handoff: `7dda63f45419b32aa845fa826024c70dd523672c8651fd4463dc75a84ef31071`
- Updated: 2026-07-27

## Design Goal

Deliver the smallest production-shaped Telegram group service that:

1. proves its bot identity before reporting startup success;
2. receives ordinary text updates from one configured group;
3. replies exactly once with `1` when a human sends exact text `1`;
4. remains silent for every other text;
5. isolates malformed updates and observable transport/send failures; and
6. ships all deployment and service-management assets under `deploy/`.

LLM, moderation, tools, commands, media handling, and durable message-content
storage are outside this slice.

## Components And Ownership

```text
Environment
  -> Settings validation
  -> TelegramBotApiClient.get_me()
  -> TelegramPollingService
       -> TelegramAdapter.normalize_update()
       -> FixedReplyProcessor
            -> SQLiteDeliveryLedger.claim()
            -> TelegramBotApiClient.send_message()
            -> SQLiteDeliveryLedger.mark_sent()/mark_failed()
  -> structured application logs
```

| Component | Responsibility | Must not do |
| --- | --- | --- |
| `config.py` | Parse and validate environment settings. | Contact Telegram or reveal the token. |
| `events.py` | Define the normalized Telegram group-text value. | Contain transport or persistence logic. |
| `platforms/telegram.py` | Call Bot API methods and normalize Telegram updates. | Decide whether text should receive a reply. |
| `delivery.py` | Persist a minimal delivery claim/status for at-most-once behavior. | Persist message text or bot credentials. |
| `runtime.py` | Enforce group, sender, exact-match, error-isolation, and delivery rules. | Invoke LLMs or respond to unmatched messages. |
| `app.py` | Validate startup, build dependencies, and run bounded-retry long polling. | Report connected before `getMe` succeeds. |
| `deploy/` | Package and operate the service with externalized configuration. | Contain production credentials or runtime data. |

## Configuration Contract

| Variable | Required | Contract |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | yes | BotFather token in numeric-prefix/colon/URL-safe-secret form, supplied only at runtime. Unsafe whitespace and control characters are rejected without echoing the value. |
| `TELEGRAM_CHAT_ID` | yes | Negative integer identifying the one allowed group/supergroup. |
| `DATABASE_PATH` | no | Defaults to `data/telegram_bot.sqlite3`. |
| `TELEGRAM_POLLING_TIMEOUT_SECONDS` | no | Integer `1..50`, default `25`. |
| `TELEGRAM_RETRY_DELAY_SECONDS` | no | Integer `1..60`, default `2`. |
| `LOG_LEVEL` | no | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; default `INFO`. |

Missing or invalid configuration exits non-zero before polling. Error text names
the invalid setting without echoing its secret value.

## Telegram Contract

- Transport: Bot API long polling through `getUpdates`.
- Startup proof: `getMe` must return `ok=true` with a numeric bot ID before the
  service logs that polling is starting.
- Update scope: request only `message` updates; accept only `group` or
  `supergroup` chats and ordinary `message.text`.
- Group boundary: updates outside `TELEGRAM_CHAT_ID` are ignored.
- Sender boundary: updates from any Telegram bot are ignored. The authenticated
  bot ID is also passed to the processor as an explicit self-sender guard.
- Text semantics: normalization preserves the original text. Only `text == "1"`
  matches; `" 1"`, `"1 "`, captions, and non-text media do not match.
- Reply contract: `sendMessage` uses `reply_parameters.message_id` so the fixed
  response is visibly tied to the triggering message.
- Token safety: request construction, connection, and response-body failures are
  translated to stable `TelegramApiError` categories without exposing the Bot
  API URL or token, including in rendered exception tracebacks.

## State And Idempotency

SQLite stores only the minimum delivery ledger:

| Field | Purpose |
| --- | --- |
| `chat_id` | Scope a Telegram message to its group. |
| `message_id` | Identify the trigger inside the group. |
| `action_kind` | Currently `fixed_reply`. |
| `status` | `sending`, `sent`, or `failed`. |
| `error_code` | Stable, non-secret failure category; optional. |
| timestamps | Operational traceability. |

`(chat_id, message_id, action_kind)` is unique. The processor atomically claims
the action before sending. A replay or restart cannot claim the same action
again, so it cannot send a second fixed reply.

This chooses at-most-once delivery. If the process stops after claiming but
before Telegram confirms the send, the ledger prevents an automatic retry.
That uncertainty is observable as `sending`; operators can inspect it rather
than risk a duplicate. An explicit retry command is deferred because 0.1 does
not define an administrative control plane.

No raw Telegram update or message text is stored. The service still reads the
text in memory and exposes message, group, and sender identifiers in structured
logs and deterministic tests.

## Processing And Failure Lifecycle

1. Validate configuration.
2. Open and initialize the SQLite ledger.
3. Call `getMe`; fail startup if identity cannot be proven.
4. Start `getUpdates` at the current in-memory offset.
5. For each update, advance the offset from its `update_id`.
6. Normalize the update. A malformed or unsupported update is logged/skipped.
7. Ignore other groups and bot senders.
8. For unmatched text, log receipt metadata and remain silent.
9. For exact text `1`, atomically claim the fixed reply.
10. If already claimed, log a duplicate and remain silent.
11. Send reply `1`, then mark `sent`.
12. On send failure, mark `failed`, log a redacted error, and continue with the
    next update.
13. On polling transport failure, including a response-body timeout, log a
    redacted error, wait the configured bounded delay, and retry until the
    process is stopped.

The offset is advanced for malformed updates so a poison update cannot
permanently stop later valid messages.

## Privacy, Permissions, And Safety

- Bot creation, group membership, privacy-mode configuration, and group
  permissions remain administrator responsibilities.
- Runtime configuration is external. Tracked examples contain placeholders.
- Logs include identifiers and status, not the bot token or full message text.
- The database stores delivery identifiers/status only.
- The service performs no delete, mute, ban, member-management, or LLM action.
- The only external write is `sendMessage` for an exact accepted trigger.

## Deployment Design

`deploy/` contains:

- `Dockerfile`: Python 3.11 slim image, non-root runtime user, package install.
- `compose.yaml`: one long-running service, restart policy, external `.env`,
  and a persistent data volume.
- `.env.example`: placeholders and non-secret defaults.
- `manage.sh`: build/start/stop/restart/status/log entry points.
- `README.md`: prerequisites, BotFather/group setup, privacy-mode guidance,
  startup, verification, recovery, and secret handling.

No CI/CD, orchestrator, zero-downtime rollout, or secret distribution system is
introduced.

## Compatibility, Rollout, And Rollback

- Python requirement remains 3.11 or newer.
- The implementation uses only the Python standard library at runtime.
- Rollout is additive: populate external `.env`, build, then start one service.
- Rollback is `deploy/manage.sh stop` followed by starting the prior image or
  checkout. The SQLite ledger can be retained across restarts.
- The 0.1 service does not promise compatibility with the uncommitted legacy
  LLM prototype because that behavior is outside the confirmed contract.

## Verification Strategy

| Proof | Requirements / criteria |
| --- | --- |
| Config unit tests | REQ-001, REQ-007; AC-001, AC-006 |
| Adapter/normalization tests | REQ-002, REQ-003, REQ-005, REQ-006; AC-002, AC-004, AC-005 |
| Processor and ledger tests | REQ-004–008; AC-003–AC-007 |
| Transport redaction/error tests | REQ-007, REQ-008; AC-006, AC-007 |
| Clean-checkout compile and unit suite | Package boundary and deterministic behavior |
| `sh -n deploy/manage.sh` and deployment file inspection | REQ-009–012; AC-008–AC-010 |
| Real group smoke with operator credentials | AC-001–AC-007; deferred if credentials are unavailable |

## Accepted Design Decisions

- D-001: use long polling; no public ingress is required.
- D-002: require one explicit `TELEGRAM_CHAT_ID`.
- D-003: use a dedicated fixed-reply processor; do not route 0.1 through an LLM.
- D-004: use a minimal SQLite delivery ledger without message-content storage.
- D-005: prefer at-most-once delivery over automatic retries that could duplicate replies.
- D-006: package the service with Docker Compose and a small management script.
