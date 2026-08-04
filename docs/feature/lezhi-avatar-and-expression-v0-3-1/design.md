# Technical Design: 乐枝默认头像部署与复合表情回复 v0.3.1

- Status: Design Complete
- Feature branch: `codex/lezhi-avatar-and-expression-v0-3-1`
- Confirmed requirements commit: `86ace06b0704da458646747e3ca0468456235851`
- Safe forward baseline: `origin/main@88c775c8ef0be7d1c63fd71b5924334b12492d75`
- Requirements SHA-256: `66b82b3db77ffba968d26b651a2cccfc7a85e500b36a79a8aa41722a6b67593d`
- Design date: 2026-08-04

## 1. Purpose And Design Boundary

This design adds two bounded capabilities without weakening the v0.4 production
baseline:

1. An inbound persona reply may contain one text message, one sticker, or one
   text message followed by one sticker.
2. An explicitly authorized operator may apply the approved `lezhi-default`
   bot profile photo, with Telegram's explicit `setMyProfilePhoto=true`
   response as the system success condition.

The design does not add a second visible effect to scheduled food delivery,
control commands, tools, avatar operations, or any other write path. It does
not enable VISION, automatic avatar rotation, or mood-avatar application. It
does not modify the 48 expression assets or their Telegram mapping.

The implementation is based on `main@88c775c...`, including schema migration
5 and all v0.4 subscription, food recommendation, command, scheduling, Web
tool, and runtime behavior. The previous `c1e820a...` production snapshot is
historical evidence only and is not a build or deployment base.

## 2. Current Constraints And Refactoring Gate

The current code has three high-risk concentration points:

- `runs.py` owns model runs, external effects, tool audit, memory audit,
  expression metrics, and mood state in one large repository.
- `effector.py` combines orchestration, response schema, final validation,
  sticker policy, and degradation.
- `avatar.py` combines catalog handling, rotation policy, platform mutation,
  readback, rollback, and audit.

The feature therefore uses additive boundaries instead of adding another state
machine to `RunRepository`:

- new `effect_bundle.py` owns reply-bundle persistence and metrics;
- new `expression_policy.py` owns pure sticker eligibility/selection rules;
- new `writer_contract.py` owns the Writer response schema and protocol text;
- `effect_delivery.py` becomes the orchestration adapter over the bundle
  repository and Telegram port;
- `avatar.py` keeps catalog/rotation compatibility but narrows the explicit
  apply path to preflight, one upload call, and audit.

`RunRepository` remains the owner of trigger/effect/model runs and legacy
single external effects. Scheduled automation keeps using
`AutomationDeliveryRepository` and `external_effects` unchanged.

## 3. Component Ownership

| Component | Ownership |
| --- | --- |
| `writer_contract.py` | Application-owned Writer decision schema and exact output protocol, including `reply_with_sticker`. |
| `writer_prompt.py` | Prompt assembly; imports the canonical protocol instead of duplicating operation names. |
| `model.py` | Parses the canonical Writer kinds into typed decisions. It never accepts arbitrary Telegram identifiers. |
| `expression_policy.py` | Pure classification of sticker eligibility, sticker-only eligibility, relationship bounds, and consecutive-repeat rejection. |
| `effector.py` | Runs the model/tool loop, validates text and selected semantic ID, and returns one immutable `FinalEffect`. It never sends Telegram effects. |
| `effect_bundle.py` | Atomic bundle/component preparation, component state transitions, restart reconciliation, duplicate detection, and privacy-safe rate metrics. |
| `effect_delivery.py` | Sends inbound persona bundle components in order and records the returned platform message identities. |
| `runs.py` | Existing model/effect run audit and legacy single-effect paths only. A composite final maps to the existing terminal `reply` run status. |
| `automation_delivery.py` | Unchanged v0.4 scheduled single-text claim/delivery boundary. |
| `avatar.py` | Default-avatar preflight, one explicit platform write, outcome classification, and audit. |
| `operator_cli.py` | Local operator authorization reference, bot identity binding, one-shot avatar apply, and privacy-safe metrics output. |

## 4. Writer And Final-Effect Contract

### 4.1 Writer decision kinds

The existing kinds remain valid:

- `reply`
- `sticker`
- `silence`
- `food_recommendation`
- `call_tool`

One kind is added:

```json
{
  "kind": "reply_with_sticker",
  "reason_code": "light_playful_followup",
  "text": "一条可包含多句的文本消息。第二句仍在同一条消息里。",
  "sticker_id": "lezhi.hello_wave.a01",
  "catalog_version": "lezhi-expression-v0.3",
  "catalog_digest": "<64 lowercase hex>",
  "mood_signal": "playful"
}
```

The schema remains closed with `additionalProperties=false`. It contains no
`file_id`, URL, sticker-set name, raw media, or second text field. Parser,
schema, and prompt kind sets are derived from one application-owned contract
and covered by a contract test.

`reply_with_sticker` is invalid for `TriggerPath.SCHEDULED`. Scheduled food
continues to accept only `food_recommendation`, `silence`, and bounded tool
calls, preserving REQ-029 and v0.4 behavior.

### 4.2 Final effect

`FinalEffectKind` adds `REPLY_WITH_STICKER`. A composite final contains:

- one validated `text` string, maximum 4096 characters;
- one validated expression semantic ID;
- the exact enabled catalog version and digest;
- persona snapshot and reason code;
- `sticker_eligible` and an application-owned eligibility reason;
- no platform `file_id` and no additional media.

The existing effect-run table does not need a new status. Completing a
`REPLY_WITH_STICKER` model run records `effect_runs.status='reply'`; the exact
visible form and component outcomes live in the bundle tables.

### 4.3 Sticker policy

Sticker policy is split into two questions:

1. **Is any sticker allowed for this context?** Medical, self-harm, urgent
   safety, illegal activity, permission failure, serious relationship repair,
   unsafe vision evidence, and vision uncertainty are ineligible for both
   sticker-only and composite output.
2. **Can the selected sticker be used?** The entry must be enabled in the exact
   catalog, compatible with the relationship level, and different from the
   immediately preceding successfully sent sticker in the chat.

Factual explanations and ordinary steps require text but may carry a bounded
sticker only when the sticker does not weaken or replace the information.
Sticker-only remains limited to low-stakes situations where the sticker is a
complete answer.

For a composite decision, valid text is retained if the selected sticker is
rejected. The result becomes text-only with a privacy-safe degradation reason.
For sticker-only, rejection follows the existing direct failure-reply versus
contextual silence degradation rule.

Eligibility for metrics is computed before delivery from the application rule
and exact enabled catalog, not from whether the model happened to select a
sticker. This prevents the metric from redefining safety or hiding text-only
eligible replies.

## 5. Durable Bundle Model

Schema migration 6 is additive and follows v0.4 migration 5.

### 5.1 `effect_bundles`

The table stores one row per inbound persona trigger:

| Field group | Fields |
| --- | --- |
| Identity | `id`, `bundle_id`, `bot_user_id`, `chat_id`, `trigger_event_id`, `trigger_message_id` |
| Immutable snapshots | `persona_version`, `persona_digest`, `catalog_version`, `catalog_digest` |
| Decision | `requested_form`, `reason_code`, `sticker_eligible`, `eligibility_reason` |
| Outcome | `status`, `error_code`, `created_at`, `updated_at`, `completed_at` |

`UNIQUE(chat_id, trigger_event_id)` is the bundle claim. `requested_form` is
one of `text`, `sticker`, `text_sticker`, or `failure_text`. `status` is one of
`prepared`, `delivering`, `completed`, `degraded`, `failed`, `uncertain`, or
`interrupted`.

### 5.2 `effect_bundle_components`

Each bundle has zero to two rows:

| Field group | Fields |
| --- | --- |
| Identity/order | `id`, `bundle_id`, `ordinal`, `component_kind` |
| Request audit | `requested_effect_kind`, `asset_semantic_id`, `text_character_count` |
| Outcome | `status`, `platform_message_id`, `error_code`, `created_at`, `updated_at` |

`UNIQUE(bundle_id, ordinal)` enforces order. A text is ordinal 1. A composite
sticker is ordinal 2. Sticker-only uses ordinal 1. Component status is one of
`planned`, `sending`, `sent`, `failed`, `uncertain`, or `skipped`.

No table stores the full generated text, prompt, token, credential, image
binary, Telegram `file_id`, member profile, or sensitive member attribute.
Only the approved semantic ID is retained for a sticker.

### 5.3 Coexistence with legacy effects

- New inbound persona replies use bundle tables.
- Existing `external_effects` rows remain readable and continue to deduplicate
  older inbound events.
- Controls and v0.4 scheduled food continue using `external_effects`.
- Runtime duplicate checks test a bundle first, then the legacy external
  effect, then terminal trigger/effect-run state.
- Migration does not rewrite historical effects, messages, automation rows,
  expression mappings, avatar audits, or member memory.

## 6. Delivery State Machine

### 6.1 Preparation

Before any Telegram send, one `BEGIN IMMEDIATE` transaction inserts the bundle
and every expected component. Losing the unique insert means `duplicate`; the
caller never sends from a losing attempt.

The generated text stays in process memory only. A durable `planned` component
is a claim, not permission for a later process to reconstruct or send content.

### 6.2 Ordered delivery

For each component in ordinal order:

1. Compare-and-swap `planned -> sending`.
2. Call exactly one Telegram method.
3. On explicit success, store `sent` and the returned message ID.
4. On explicit failure, store `failed`.
5. On timeout, transport interruption, invalid/unknown response, or a sticker
   identity mismatch, store `uncertain`.

Text uses `sendMessage`; sticker uses the exact mapped file ID resolved after
catalog digest validation. Both reply to the original trigger message. The
outbound message repository receives distinct event IDs containing component
ordinals so the text and sticker cannot violate its uniqueness constraint.

### 6.3 Partial failure

| Boundary | Result |
| --- | --- |
| Text explicitly fails | Sticker becomes `skipped`; bundle `failed`; no sticker call. |
| Text is uncertain | Sticker becomes `skipped`; bundle `uncertain`; no retry or alternative. |
| Text succeeds, sticker explicitly fails | Bundle `degraded`; the text remains the only visible result. |
| Text succeeds, sticker is uncertain | Bundle `uncertain`; no retry or replacement. |
| Both succeed | Bundle `completed`. |
| Sticker-only explicitly fails | Bundle `failed`; no fallback send under the claim. |
| Sticker-only uncertain | Bundle `uncertain`; no fallback or retry. |

### 6.4 Restart and replay

Startup and duplicate-event handling run a reconciliation transaction before
returning a terminal duplicate result:

- `sending` becomes `uncertain` because the platform may have accepted it;
- a `planned` sticker after a sent text becomes `skipped`, and the bundle ends
  `degraded` with `restart_after_text_before_sticker`;
- an all-`planned` prepared bundle becomes `interrupted` and is never sent by a
  later process;
- remaining planned components after any uncertain component become skipped;
- no reconciliation path calls Telegram.

A crash before bundle preparation leaves no external claim, so the existing
pre-claim replay path may recompute. A crash at or after preparation is
at-most-once and terminalized without delayed content. Successfully sent or
uncertain components are never repeated.

## 7. Sticker-Bearing Metrics

The bundle repository exposes a privacy-safe aggregate for one exact
`bot_user_id + persona_version + persona_digest + catalog_version +
catalog_digest` tuple.

The query considers rows completed in the last seven days, newest first, and
uses at most 100 qualifying bundles. A bundle qualifies only when:

- `sticker_eligible=1`; and
- at least one component has `status='sent'`.

The numerator is qualifying bundles with a successfully sent sticker
component. This includes sticker-only and text+sticker. Silence, trigger
rejection, safety/relationship ineligibility, and bundles with no sent
component do not enter the denominator.

The result contains only scope versions, window timestamps, denominator,
sticker-bearing count, text-only count, ratio, and status. Fewer than 30
qualifying rows returns `insufficient_data`; it does not tune prompts or force
stickers. Values outside 0.4–0.7 are operational evidence only.

The fixed evaluation carrier contains 40 sticker-eligible cases plus separate
safety/relationship guard cases. Passing requires 16–28 sticker-bearing
eligible cases, every necessary-text case to retain text, every hard-forbidden
case to contain no sticker, no repeated adjacent sticker, and valid schema for
every provider response.

## 8. Avatar Apply Contract

### 8.1 Preflight

The operator command requires:

- deployment-approved avatar catalog digest
  `b871161e68c18115893d7aea932dabf1e9101d40278d6ce9168a6eb3735d405a`;
- `avatar_id=lezhi-default`;
- source image SHA-256
  `fd7ec0efafb9dc1e36856461228cecbf7467548c7628454fe2022f7ad607badf`;
- authenticated `getMe.id` equal to the requested bot identity;
- an explicit local operator authorization reference and reason.

Any mismatch stops before `setMyProfilePhoto`. The repository candidate
catalog and image bytes remain untouched.

### 8.2 One write and no automated readback

After preflight, the controller creates an operation audit row and calls
`setMyProfilePhoto` once. It does not call `getUserProfilePhotos`, `getFile`,
`downloadFile`, a vision model, or any other post-upload verification. It does
not capture the old photo and does not automatically retry or roll back.

An exact Bot API `result=true` records `success`. Explicit Bot API rejection or
local preflight failure records `failed`. Timeout, transport interruption,
HTTP 5xx, invalid JSON/response/result, or any unknown post-call outcome records
`uncertain`. Errors are recorded by safe category, never by token-bearing URL
or response body.

### 8.3 Audit and manual anomaly handling

Migration 6 adds nullable `operation_id`, `api_method`, and
`authorization_reference` columns to the existing avatar audit table, keeping
all historical rows. New operations record operation ID, bot identity, catalog
version/digest, avatar ID, image SHA, operator, reason, API method, outcome,
safe error category, and timestamps.

The CLI prints the operation ID and terminal system status. If a user later
observes a missing, stale, or wrong avatar, the operator locates this operation
and inspects Telegram manually before deciding whether to issue a new explicit
operation. Ordinary group messages never mutate the avatar.

Historical `verified` rows remain readable. Future default-baseline and
cooldown queries accept both historical `verified` and new `success`, although
automatic rotation stays disabled.

## 9. Compatibility And v0.4 Preservation

- Migration 6 applies cleanly after migrations 1–5 and is additive.
- All existing food configuration, subscriptions, occurrences, scheduled
  effect claims, Web audit, and commands are byte-compatible.
- `reply_with_sticker` is rejected for scheduled requests, so the automation
  delivery path remains one text external effect.
- Existing `reply`, `sticker`, `silence`, food, and tool decisions remain valid.
- Existing inbound `external_effects` continue to prevent duplicate replies.
- The 48 enabled mappings, VISION disabled setting, automatic rotation false,
  and absence of mood-avatar application are deployment invariants.

## 10. Concurrency And Transactions

- Bundle preparation and each component claim use `BEGIN IMMEDIATE` and
  compare-and-swap predicates.
- Only the transaction that inserts the unique chat/event bundle may send.
- Only a `planned` component may enter `sending`.
- Terminal component and bundle rows are immutable except idempotent reads.
- Metric reads never grant send permission and do not update policy.
- Avatar apply remains protected by the existing process-level operator lock;
  the audit operation is created before the single platform write.
- Scheduled automation's lease, claim, and recovery transactions are unchanged.

## 11. Security And Privacy

- Writer input, group messages, tools, Web results, and vision results remain
  untrusted and cannot change the output schema or external-write authority.
- Text final validation still rejects protocol JSON, internal markers, leaked
  memory fields, deadline overruns, and persona snapshot mismatches.
- Sticker selection resolves only an enabled semantic ID from the exact
  approved catalog and never accepts provider-owned identifiers.
- Bundle audit stores no message body or member-sensitive attribute.
- Avatar audit stores no token, key, credential URL, response body, or image.
- No project image is sent to a visual provider by this feature.

## 12. Rollout And Rollback

### Rollout

1. Build and review from the exact safe-forward branch based on
   `main@88c775c...`.
2. Back up the production SQLite database and record its SHA-256.
3. Prove the backup and current database both return `PRAGMA quick_check=ok`.
4. Build the exact reviewed image and prove source/package identity.
5. Verify pre-deploy invariants: 48/48 mappings enabled, VISION disabled,
   rotation disabled, no mood-avatar apply, and v0.4 automation state retained.
6. Restart the Compose service with migration 6 and verify identity, polling,
   schema, v0.4 status commands, and bundle runtime.
7. Run fixed/provider evaluation and bounded Telegram reply-form smoke.
8. Execute exactly one authorized `lezhi-default` apply.
9. Record the operation ID and ask for manual visible-avatar confirmation as
   operational evidence, not as the system success gate.

### Rollback

Code rollback restores the prior reviewed image and configuration. SQLite is
restored from the pre-deploy backup only when the new schema or runtime cannot
operate safely; additive migration 6 may otherwise remain dormant. Rollback
does not republish stickers, disable v0.4, invoke automatic avatar rotation, or
automatically attempt another avatar write. An uncertain avatar operation is
never followed by an automatic retry.

## 13. Proof Strategy

### Deterministic tests

- Writer prompt/schema/parser exact-kind agreement and rejection of malformed
  composite payloads.
- All five visible reply forms and one-message handling of multi-sentence text.
- Safety, necessary-text, relationship, catalog digest, unknown semantic ID,
  and consecutive-repeat rules for sticker-only and composite output.
- Bundle uniqueness, ordering, component transitions, explicit failure,
  uncertain result, crash/restart reconciliation, and duplicate replay.
- Metric denominator/numerator, 7-day window, newest-100 bound,
  insufficient-data threshold, and version isolation.
- Avatar preflight, bot identity, exact success, explicit failure, uncertain
  categories, no retry, and proof of zero post-upload readback calls.
- Migration 1–6 from a production-shaped database plus v0.4 scheduler/control
  regression coverage.

### Build and operational proof

- compileall, complete unit suite, Ruff check/format, Mypy, package build,
  shell syntax, Compose render, Docker build, installed entry point, secret
  scan, and Git diff checks;
- fixed evaluation using the production Writer protocol and selected provider;
- production-backup `quick_check` and exact migration inventory;
- post-restart Telegram identity/polling logs and v0.4 `/food_status` behavior;
- operator-authorized reply-form smoke and one default-avatar API operation.

## 14. Requirements Traceability

| Design area | Requirements |
| --- | --- |
| Avatar preflight/API success/audit | REQ-001–REQ-010; AC-001–AC-004 |
| Writer and final-effect forms | REQ-011–REQ-019; AC-005–AC-007 |
| Bundle idempotency/partial failure/restart | REQ-020–REQ-023; AC-008–AC-010 |
| Sticker-bearing metrics | REQ-024–REQ-028; AC-011–AC-013 |
| Scheduled/other write isolation | REQ-029; AC-014 |
| Migration, review, safe-forward baseline | REQ-030–REQ-032; AC-015–AC-016 |
| Production invariants and bounded deployment | REQ-033–REQ-034; AC-017–AC-018 |

## 15. Deferred Work

- automatic avatar rotation and mood-avatar application;
- VISION enablement or any external image analysis;
- multiple stickers, multiple text messages, or additional media in one reply;
- member-facing avatar controls or public anomaly-report commands;
- automatic prompt tuning based on online sticker rate;
- second visible effects for scheduled food, controls, or tools.
