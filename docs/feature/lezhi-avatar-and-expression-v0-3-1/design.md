# Technical Design: 乐枝默认头像部署与复合表情回复 v0.3.1

- Status: Design Complete — LLM Reply-Form Boundary Revision
- Feature branch: `codex/lezhi-v031-provider-gate-fix`
- Confirmed requirements commit: `596a754419bc971ac71436bbb85f408ecc7962f0`
- Safe forward baseline: `origin/main@85998708aa9a1d85b33a4477a818339498846868`
- Requirements SHA-256: `71e6b25fc970a4a6aa78697369a1a194081102f943138e699ae0a5a642caacc9`
- Design date: 2026-08-04

## 1. Purpose And Design Boundary

This revision preserves the two already implemented v0.3.1 capabilities while
changing the reply-form responsibility boundary:

1. An inbound persona reply may contain one text message, one sticker, or one
   text message followed by one sticker.
2. An explicitly authorized operator may apply the approved `lezhi-default`
   bot profile photo, with Telegram's explicit `setMyProfilePhoto=true`
   response as the system success condition.
3. The Writer LLM is the sole semantic owner of whether the final form is
   `reply`, `reply_with_sticker`, `sticker`, or `silence`. The application does
   not reinterpret natural-language content to change that choice.

The design does not add a second visible effect to scheduled food delivery,
control commands, tools, avatar operations, or any other write path. It does
not enable VISION, automatic avatar rotation, or mood-avatar application. It
does not modify the 48 expression assets or their Telegram mapping.

The implementation is based on `main@85998708...`, which already contains the
merged v0.3.1 bundle/avatar work and all v0.4 subscription, food
recommendation, command, scheduling, Web-tool, and runtime behavior. Earlier
`88c775c8...` and `c1e820a...` snapshots are historical evidence only.

## 2. Current Constraints And Refactoring Gate

The current code has three high-risk concentration points:

- `runs.py` owns model runs, external effects, tool audit, memory audit, legacy
  expression observations, and mood state in one large repository.
- `effector.py` combines orchestration, response schema, final validation,
  sticker policy, and degradation.
- `avatar.py` combines catalog handling, rotation policy, platform mutation,
  readback, rollback, and audit.

The feature therefore uses additive boundaries instead of adding another state
machine to `RunRepository`:

- `effect_bundle.py` owns reply-bundle persistence and delivery state; the
  online frequency metric is retired;
- `expression_policy.py` is reduced to pure non-semantic catalog,
  relationship-metadata, and repetition validation;
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
| `expression_policy.py` | Non-semantic validation of catalog availability, structured relationship-rank compatibility, and consecutive-repeat rejection. It never reads message or vision text. |
| `effector.py` | Runs the model/tool loop, validates text and selected semantic ID, and returns one immutable `FinalEffect`. It never sends Telegram effects. |
| `effect_bundle.py` | Atomic bundle/component preparation, component state transitions, restart reconciliation, and duplicate detection. Existing metric columns remain readable for schema compatibility but are not used as an online policy or denominator. |
| `effect_delivery.py` | Sends inbound persona bundle components in order and records the returned platform message identities. |
| `runs.py` | Existing model/effect run audit and legacy single-effect paths only. A composite final maps to the existing terminal `reply` run status. |
| `automation_delivery.py` | Unchanged v0.4 scheduled single-text claim/delivery boundary. |
| `avatar.py` | Default-avatar preflight, one explicit platform write, outcome classification, and audit. |
| `operator_cli.py` | Local operator authorization reference, bot identity binding, and one-shot avatar apply. The online `expression-metrics` command is removed. |

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
- a non-semantic sticker validation outcome for audit compatibility;
- no platform `file_id` and no additional media.

The existing effect-run table does not need a new status. Completing a
`REPLY_WITH_STICKER` model run records `effect_runs.status='reply'`; the exact
visible form and component outcomes live in the bundle tables.

### 4.3 Sticker policy

The Writer prompt receives the complete bounded scene, relationship context,
member memory, vision evidence when available, and enabled catalog
descriptions. It tells the LLM to avoid stickers in serious, safety, medical,
permission, relationship-repair, and exclusive/favoritism contexts; to prefer
a sticker when it naturally contributes emotion or action; and never to force
one for a target rate. This semantic guidance is not duplicated in Python.

After the LLM selects a form, the application validates only facts that do not
require interpreting language:

1. the closed Writer schema and field combination are exact;
2. the catalog is enabled and its version/digest match the decision;
3. the semantic ID resolves to an enabled entry;
4. the entry's declared `minimum_relationship` does not exceed the structured
   relationship rank already supplied to the Writer;
5. the semantic ID differs from the immediately preceding successfully sent
   sticker in the chat; and
6. the trigger path and effect/component bounds authorize the selected form.

`expression_policy.py` must not search current-message, recent-scene, memory,
or vision natural-language fields. It contains no semantic keyword, regular
expression, synonym table, subject/negation grammar, or replacement classifier.

DEC-016 owns failure degradation. A structurally invalid/unknown overall model
result ends in silence after the bounded protocol attempts. A valid composite
keeps its already validated text when only the sticker fails a non-semantic
invariant. A sticker-only decision whose sticker fails a non-semantic invariant
ends in silence. No fallback text is synthesized from message semantics.

## 5. Durable Bundle Model

Schema migration 6 is additive and follows v0.4 migration 5.

### 5.1 `effect_bundles`

The table stores one row per inbound persona trigger:

| Field group | Fields |
| --- | --- |
| Identity | `id`, `bundle_id`, `bot_user_id`, `chat_id`, `trigger_event_id`, `trigger_message_id` |
| Immutable snapshots | `persona_version`, `persona_digest`, `catalog_version`, `catalog_digest` |
| Decision | `requested_form`, `reason_code`, legacy-compatible `sticker_eligible`, `eligibility_reason` |
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

## 7. Offline Evaluation Reference

The application no longer computes an online sticker-eligible denominator,
rolling rate, minimum sample threshold, quota, or corrective input. The legacy
bundle columns remain readable so migration 6 and deployed databases stay
compatible, but runtime and operator policy do not query them as a frequency
metric. The `expression-metrics` operator command and its seven-day/latest-100
calculation are removed.

The fixed evaluation carrier remains a provider-review input. Its scenario
labels help an independent Reviewer assess whether reply forms are natural in
ordinary, serious, safety, medical, permission, and relationship contexts; the
labels are not compiled into runtime policy. The report verifier owns only
deterministic evidence: exact case/catalog/persona/model snapshots, closed
output shape, valid enabled sticker IDs, structured relationship compatibility,
and adjacent-repeat rejection.

The report may display a sticker-bearing observation rate. `0.4–0.7` is a
historical product-reference band only: values below, inside, or above it do
not alter deterministic report validity, block release, or change runtime
behavior. Semantic quality requires a separately authorized provider run plus
independent human/Reviewer assessment; the existing report is retained as
immutable historical evidence and is insufficient for the revised release
gate.

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
- No online expression-rate read participates in policy or send permission.
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
   `main@85998708...`.
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
- Proof that arbitrary serious, relationship, or novel wording cannot change
  application validation: every schema-valid model form is preserved unless a
  non-semantic invariant fails.
- Catalog digest, unknown/disabled semantic ID, structured relationship rank,
  and consecutive-repeat rules for sticker-only and composite output.
- Bundle uniqueness, ordering, component transitions, explicit failure,
  uncertain result, crash/restart reconciliation, and duplicate replay.
- Absence of online rate/denominator commands and decision-path queries.
- Offline evaluation rate is reported but does not affect deterministic pass;
  semantic scenario quality remains an explicit deferred provider/reviewer gate.
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
| LLM semantics, deterministic boundary, offline evaluation reference | REQ-016–REQ-019, REQ-024–REQ-028; AC-006–AC-007, AC-011–AC-013 |
| Scheduled/other write isolation | REQ-029; AC-014 |
| Migration, review, safe-forward baseline | REQ-030–REQ-032; AC-015–AC-016 |
| Production invariants and bounded deployment | REQ-033–REQ-034; AC-017–AC-018 |

## 15. Deferred Work

- automatic avatar rotation and mood-avatar application;
- VISION enablement or any external image analysis;
- multiple stickers, multiple text messages, or additional media in one reply;
- member-facing avatar controls or public anomaly-report commands;
- any online sticker-rate metric, quota, target, or automatic prompt tuning;
- the separately authorized provider/evaluation run required by REQ-031;
- second visible effects for scheduled food, controls, or tools.
