# Implementation Plan: 原创人格、成员认识与作家上下文能力（第一阶段）

- Lifecycle phase: F3 Implementation Plan
- Status: Complete; generic runtime ready for F4
- Requirements source: `docs/feature/maomao-persona-chat/requirements.md`
- Requirements commit: `c5ea34553e52505ff50ee421cc08efff297df01f`
- Requirements handoff: `9d436ac128ed195223045c72be7ac134dff5177d8d4de11f0ad077dc8e223c32`
- Design source: `docs/feature/maomao-persona-chat/design.md`
- Design commit: `b247b3f3bac7e5ecc4eccae53b6234a6227e8f02`
- Branch: `codex/maomao-persona-chat`
- Updated: 2026-07-29

## 1. Delivery Strategy

Implementation is split into independently testable, additive slices. Existing fixed-reply
mode remains the default until the confirmed production Character Bundle is present and
persona mode is explicitly enabled.

The generic runtime, schemas, provider port, synthetic test bundles and control paths can be
implemented before `TASK-PERSONA-001` is confirmed. The following cannot be implemented before
that confirmation:

- production character identity, background, voice or examples;
- production `manifest.json`, `character.json`, examples or evaluation cases;
- documentation claiming that a concrete persona is ready;
- real-group activation of `persona_direct` or `persona_full`.

## 2. Concrete Package Boundaries

```text
src/group_llm_agent/
  app.py                    # dependency assembly and process lifecycle
  config.py                 # environment contract and safe validation
  events.py                 # normalized Telegram and runtime values
  database.py               # SQLite connections, migration runner, PRAGMAs
  messages.py               # ingestion, recent scene, retention and source metadata
  memory.py                 # member memory, decay, revisions and reset barriers
  runs.py                   # trigger/effect/tool/control audit and external-effect claims
  persona.py                # bundle schema, digest and three-view compilation
  model.py                  # structured model port and openai-compatible adapter
  trigger.py                # platform hard gate and persona trigger decider
  context.py                # trigger/effect context assembly
  tools.py                  # bounded read-only local tool registry
  effector.py               # writer loop, protocol and final validation
  recognition.py            # durable queue worker and proposal validation
  control.py                # memory notice, disable and reset commands
  runtime.py                # group message orchestration and polling integration
  delivery.py               # legacy fixed-reply ledger retained for compatibility
  platforms/telegram.py     # Bot API transport and update normalization

src/group_llm_agent/persona_bundles/
  <persona-id>/<version>/   # production assets only after TASK-PERSONA-001 confirmation

tests/
  fixtures/personas/test-original/v1/
  helpers.py
  test_database.py
  test_messages.py
  test_memory.py
  test_persona.py
  test_model_client.py
  test_trigger.py
  test_context.py
  test_tools.py
  test_effector.py
  test_recognition.py
  test_control.py
  test_persona_runtime.py
```

The uncommitted prototype modules in the shared checkout are not copied. All code is built
from the committed Telegram 0.1 baseline and the F2 contracts.

## 3. Model Adapter Decision

The first runtime adapter is `OpenAICompatibleStructuredModelClient`, implemented with
`urllib.request` and no new runtime dependency.

Request contract:

```text
POST {MODEL_BASE_URL}/chat/completions
Authorization: Bearer {MODEL_API_KEY}
Content-Type: application/json

{
  "model": "...",
  "messages": [...],
  "response_format": {"type": "json_object"},
  "temperature": ...,
  "max_tokens": ...
}
```

Response contract:

```text
choices[0].message.content -> JSON object -> role-specific parser
```

The adapter:

- accepts only an `https` base URL in production; test clients inject an opener;
- validates the configured base URL before interpolating paths;
- translates construction, HTTP, connection, response-body, timeout, decode and schema errors
  into redacted `ModelApiError` categories;
- never logs the API key, request URL, raw provider body or prompt;
- suppresses transport causes where they could contain credentials;
- does not execute provider-native tool calls; all runtime decisions use application-owned
  JSON schemas.

Supported roles and response schemas:

| Role | Result |
| --- | --- |
| `trigger` | `{"kind":"engage|silence","reason_code":"..."}` |
| `writer` | reply, silence or one application-owned tool call |
| `recognition` | bounded list of typed memory proposals |

Tests use `ScriptedModelClient`; production never falls back to a mock response.

## 4. Schema Migration

`database.py` introduces a migration runner. Migration `001_persona_runtime` creates:

- `schema_migrations`
- `group_policies`
- `group_messages`
- `recognition_jobs`
- `member_memory_items`
- `member_memory_sources`
- `memory_reset_barriers`
- `trigger_runs`
- `effect_runs`
- `external_effects`
- `tool_call_audit`
- `recognition_change_audit`
- `control_action_audit`

Migration properties:

- one transaction per migration;
- `PRAGMA foreign_keys=ON`;
- WAL mode and bounded busy timeout on every connection;
- no alteration or deletion of the existing `delivery_ledger`;
- explicit indexes beginning with `chat_id` for message, member and source lookups;
- unique `(chat_id, telegram_message_id)` ingestion key;
- unique `(chat_id, trigger_event_id)` external-effect key;
- `CHECK` constraints for status/category/confidence where SQLite supports them;
- migration restart is idempotent.

Tests create a database containing only the legacy `delivery_ledger`, apply the migration,
reopen it and prove both fixed mode and new tables remain usable.

## 5. Slice Plan

### Slice F4-1: Foundation Contracts And Database

Files:

- add `database.py`
- add `runs.py`
- extend `events.py`
- update `delivery.py` only if a shared timestamp/helper can be reused without changing legacy
  semantics
- add `tests/test_database.py`
- add `tests/helpers.py`

Behavior:

- define enums/frozen values for trigger decisions, effect decisions, memory categories,
  run/control statuses and typed error codes;
- normalize reply-to member identity and command metadata;
- apply additive migration and repository transactions;
- implement external-effect claim/status with one outward effect per trigger;
- implement trigger/effect/tool/control audit metadata without message/prompt content.

Proof:

- legacy database migration;
- idempotent migration rerun;
- foreign-key and group-scope constraints;
- unique external-effect claim across action kind and persona version;
- crash-state transitions `sending`, `sent`, `failed`, `uncertain`.

Commit scope: foundation contracts, database and deterministic tests only.

### Slice F4-2: Character Bundle And Structured Model Port

Files:

- add `persona.py`
- add `model.py`
- update `pyproject.toml` package-data configuration
- add `tests/fixtures/personas/test-original/v1/*`
- add `tests/test_persona.py`
- add `tests/test_model_client.py`

Behavior:

- validate the four-file bundle and canonical SHA-256 digest;
- reject missing confirmation/evaluation references;
- compile deterministic Trigger, Recognition and Effector views;
- preserve one `persona_id`, `persona_version` and digest across all views;
- implement the openai-compatible structured client and redacted errors;
- provide role-specific parsers with size/type/enumeration bounds.

Synthetic fixture rule:

- fixture identity is visibly test-only;
- it is stored only under `tests/fixtures`;
- runtime package lookup cannot discover or activate it;
- no README or deployment default references it.

Proof:

- valid bundle produces three consistent immutable views;
- changing any bundle byte changes/rejects the digest;
- unsafe path, unknown field, missing section and stale manifest fail closed;
- invalid URL, HTTP, timeout, body-read and malformed JSON errors contain no API key;
- provider content cannot inject a tool name outside the application schema.

Commit scope: bundle and model ports only.

### Slice F4-3: Messages, Memory And Context

Files:

- add `messages.py`
- add `memory.py`
- add `context.py`
- add `tests/test_messages.py`
- add `tests/test_memory.py`
- add `tests/test_context.py`

Behavior:

- keep a 20-message in-memory ring while persistent memory is disabled;
- after notice enablement, persist current-group public text with seven-day expiry;
- purge text to `NULL` while retaining source metadata;
- store fact/observation/shared-experience as persona-neutral when valid;
- require persona version for impression/preference;
- calculate effective confidence using category half-life;
- supersede/weaken/revoke with optimistic revisions;
- assemble bounded TriggerContext and EffectContext from one persona snapshot;
- enforce `(chat_id, Telegram user_id)` lookup in all public repository methods.

Proof:

- no cross-group lookup is possible through repository APIs;
- last-20 ordering and bounds;
- expired or reset text never appears in tools/context;
- low-confidence and incompatible-persona items are excluded;
- unknown member produces empty memory and stranger behavior inputs;
- later evidence can revise or revoke an old impression.

Commit scope: message/memory/context persistence only.

### Slice F4-4: Platform Gate And Persona Trigger

Files:

- add `trigger.py`
- update `platforms/telegram.py`
- update `events.py`
- update `tests/test_telegram_adapter.py`
- add `tests/test_trigger.py`

Behavior:

- route memory control commands before persona behavior;
- direct trigger on mention, reply to bot or non-control bot command;
- hard contextual gate requires 15 minutes and five new human messages;
- direct trigger bypasses the persona-trigger model but not safety/delivery/rate gates;
- contextual candidate calls the Trigger view once with no tools and a five-second deadline;
- any trigger-model error, invalid result or uncertainty becomes silence;
- record `trigger_runs` with version/digest and reason code.

Proof:

- direct trigger cannot be silenced by the participation model;
- Character Bundle changes can change contextual engage/silence fixtures;
- the same bundle version is present in trigger and resulting EffectRequest;
- hard cadence cannot be weakened by bundle/model content;
- injection attempts in group text cannot change the trigger schema.

Commit scope: Telegram normalization and trigger subsystem.

### Slice F4-5: Read-only Tools And Writer Effector

Files:

- add `tools.py`
- add `effector.py`
- add `tests/test_tools.py`
- add `tests/test_effector.py`

Behavior:

- register only `lookup_member_memory` and `search_recent_group_messages`;
- inject group/member/deadline scope outside model arguments;
- cap results at 8 memory items or 10 messages/4,000 characters;
- run at most three writer calls and two serial tool calls;
- force tools disabled on call three;
- parse reply/silence/tool-call decisions and validate final text;
- direct failures produce one configured neutral failure effect;
- contextual failures produce silence;
- record model/tool counts, purpose code, latency and typed result.

Proof:

- zero-tool direct reply;
- one- and two-tool loops;
- third call cannot request a tool;
- invalid tool, args, group/member target and oversized result fail safely;
- tool result is delimited as untrusted data;
- model cannot send Telegram or write memory;
- no route produces more than one `FinalEffect`.

Commit scope: tools and effector.

### Slice F4-6: Independent Recognition Worker

Files:

- add `recognition.py`
- add `tests/test_recognition.py`

Behavior:

- enqueue a recognition job in the same transaction as persistent message ingestion;
- run a background worker with a separate SQLite connection;
- lease/recover jobs and call the Recognition view/model once;
- validate subject, sources, categories, sensitive boundaries and reset generation;
- apply proposals atomically with one database conflict retry and no second model call;
- retry provider failures with persisted bounded backoff, max three attempts;
- mark old-persona pending jobs `superseded`;
- run bounded text-retention maintenance from the worker loop.

Proof:

- recognition failure does not affect reply/polling;
- Character Bundle relationship rules change impression/preference fixtures;
- facts remain persona-neutral while impressions/preferences bind the exact bundle;
- cross-group/sensitive/fabricated-source proposals are rejected;
- reset racing a leased job prevents stale commit;
- expired lease recovery and dead-job behavior.

Commit scope: recognition subsystem.

### Slice F4-7: Transparency And Memory Control

Files:

- add `control.py`
- update `platforms/telegram.py`
- add `tests/test_control.py`
- update `tests/test_telegram_client.py`

Behavior:

- add redacted `getChatMember`;
- make `sendMessage` return the sent Telegram message ID;
- implement `/memory_enable`, `/memory_disable`, `/memory_forget_me`,
  reply-based `/memory_forget_member`, and `/memory_forget_group CONFIRM`;
- verify administrator state live for admin operations;
- enable persistence only after Telegram confirms the disclosure message;
- reset memory/text/jobs in one transaction and advance the reset generation;
- consume control commands before persona trigger/effect paths.

Proof:

- failed/uncertain notice leaves memory disabled;
- permission timeout or ambiguous status changes no state;
- self reset affects only sender/current group;
- admin target/group reset scope;
- reset acknowledgement failure does not undo a completed reset;
- one control command cannot also produce a persona reply.

Commit scope: control service and Telegram read additions.

### Slice F4-8: Runtime Assembly, Compatibility And Deployment

Files:

- update `config.py`
- update `app.py`
- update `runtime.py`
- update `__main__.py` only if shutdown wiring needs it
- update `.env.example`
- update `deploy/.env.example`
- update `deploy/compose.yaml` only for required environment/pass-through values
- add `tests/test_persona_runtime.py`
- update `tests/test_app.py`, `tests/test_config.py`, `tests/test_runtime.py`

Behavior:

- parse all F2 settings with safe secret handling and cross-field validation;
- keep `BOT_MODE=fixed` as default and preserve exact 0.1 behavior;
- in persona modes, load one active bundle before logging startup success;
- assemble the group runtime and start/stop the recognition worker cleanly;
- capture one immutable persona snapshot per inbound event;
- store outbound bot messages in recent context only after confirmed send;
- isolate per-message processing failures;
- reject persona mode if the bundle, model or required memory capability is invalid.

Proof:

- all existing 0.1 tests continue to pass in fixed mode;
- missing/unsafe model secrets are redacted;
- invalid bundle/model config fails startup before polling;
- direct and contextual end-to-end flows with scripted model;
- duplicate update/restart cannot duplicate effects/jobs;
- clean worker shutdown and startup lease recovery.

Commit scope: application composition and deployment configuration.

### Slice F4-9: Confirmed Production Character Bundle

Blocked until a new confirmed Character Bible handoff exists.

Files after confirmation:

- add `docs/feature/maomao-persona-chat/character-bible.md` from Requirements
- add `src/group_llm_agent/persona_bundles/<confirmed-id>/<version>/manifest.json`
- add `character.json`
- add `examples.jsonl`
- add `evaluation-cases.jsonl`
- add fixed evaluation tests/data as specified by the confirmed contract

Behavior:

- encode only confirmed character facts and examples;
- compile the same Trigger/Recognition/Effector views;
- record requirements and Character Bible snapshot references/digest;
- set no production persona as a silent default.

Proof:

- AC-BIBLE-001 through AC-BIBLE-006;
- every fixed evaluation case scores at least 8/10;
- all critical prohibitions are zero;
- no protected character imitation or copied dialogue.

Commit scope: production bundle and its evaluation carrier only.

## 6. F5 Verification, Documentation And Manual Proof

Files:

- add `docs/feature/maomao-persona-chat/verification.md`
- update `README.md`
- update `deploy/README.md`
- update `CHANGELOG.md`

Automated commands:

```text
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
sh -n deploy/manage.sh
docker compose -f deploy/compose.yaml config
```

Verification carrier records exact full commit SHA before each clean-snapshot check, command,
result, skipped external proof and limitation.

Required real-group smoke after operator authorization:

1. fixed mode still responds `1 -> 1`;
2. enable notice is sent and memory becomes enabled only after confirmation;
3. direct mention produces one in-character reply;
4. contextual non-opportunity remains silent;
5. contextual opportunity respects cadence and produces at most one reply;
6. restart preserves member recognition;
7. `/memory_forget_me` removes prior recognition from later behavior;
8. cross-group data is not accessible;
9. logs contain no Telegram/model token, prompt or raw provider body.

Model-quality proof is separated from deterministic correctness:

- deterministic tests prove schemas, scope, budgets, storage and one-effect behavior;
- the confirmed evaluation set proves character quality using the five-dimension rubric;
- real-group smoke proves integration but does not replace the fixed evaluation set.

## 7. Documentation And Public Contract Changes

`README.md` will add:

- fixed/persona modes;
- required model configuration;
- Character Bundle integrity/activation;
- direct and contextual behavior;
- memory transparency/control commands;
- failure and rollback guidance.

`deploy/README.md` and examples will add placeholders only. No real Telegram token, model API
key, database, provider response or local Character Bundle override is committed.

`CHANGELOG.md` will describe:

- original persona chat;
- member recognition and reset;
- two bounded read-only context tools;
- compatibility/rollout and known manual-proof requirements.

No semantic package-version bump or release is performed unless the user separately requests a
release.

## 8. Implementation Invariants

Every slice must preserve:

1. one accepted requirements commit and one active Character Bundle snapshot;
2. one persona version/digest across Trigger, Recognition and Effector for an event/job;
3. only Recognition writes durable member understanding;
4. only ReplyCommitter performs Telegram writes;
5. one external effect per `(chat_id, trigger_event_id)`;
6. no model-supplied group scope, member scope, credentials or external action;
7. no cross-group/private/external-profile recognition;
8. no persistence before successful group notice;
9. no old queued work restoring reset memory;
10. fixed mode remains the default rollback path.

## 9. Requirements And Acceptance Coverage

| Slice | Primary coverage |
| --- | --- |
| F4-1 | REQ-009, REQ-020, REQ-022, REQ-030, REQ-038 |
| F4-2 | REQ-001–006, REQ-010–012, REQ-038–039 |
| F4-3 | REQ-022–035 |
| F4-4 | REQ-006–012 |
| F4-5 | REQ-009–020, REQ-036–037 |
| F4-6 | REQ-021–027, REQ-029–035 |
| F4-7 | REQ-028–033, REQ-036 |
| F4-8 | REQ-007–012, REQ-017, REQ-032, REQ-038 |
| F4-9 | REQ-001–006, REQ-023–027, REQ-039, AC-BIBLE-001–006 |

The aggregate verification matrix in F5 must cite every AC-001 through AC-022. A slice is not
complete merely because its local tests pass if an associated acceptance criterion lacks
observable proof.

## 10. Commit And Review Strategy

- Keep each slice in a focused commit with its deterministic tests.
- Push after every completed slice.
- Do not include the existing untracked `uv.lock` unless dependency/package work intentionally
  regenerates and validates it; this plan adds no runtime dependency.
- Do not create a PR before all intended F4/F5 files are committed and the production Character
  Bundle is confirmed.
- Create one non-draft PR against `main`, update the full problem/solution/test/manual-proof/
  limitation description, then query GitHub for exact base/head SHAs.
- Dispatch the immutable review request exactly once through the configured Reviewer task.
- Stop source edits while review is pending; requested changes require a new head and re-review.

## 11. Remaining Gate

The implementation plan is complete. Generic F4 slices may start immediately.

Full feature completion remains dependent on `TASK-PERSONA-001`:

- Requirements task creates a separate Character Bible snapshot;
- user explicitly confirms it;
- the confirmed artifact is committed and handed to Main Work;
- Main validates and accepts that handoff before F4-9 and real persona activation.
