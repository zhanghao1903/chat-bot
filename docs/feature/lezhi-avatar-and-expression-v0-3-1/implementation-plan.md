# Implementation Plan: 乐枝默认头像部署与复合表情回复 v0.3.1

- Status: Ready For Implementation — LLM Reply-Form Boundary Revision
- Confirmed requirements: `596a754419bc971ac71436bbb85f408ecc7962f0`
- Technical design: `a23bb6640aec97f7c781abb45767231cee966aeb`
- Safe forward baseline: `origin/main@85998708aa9a1d85b33a4477a818339498846868`
- Plan date: 2026-08-04

## 1. Delivery Strategy

Implement as a deletion-first, independently testable revision on the existing
PR #8 branch. The exact safe-forward main baseline remains an ancestor. No
slice may remove or bypass v0.4 automation behavior.

The implementation order is intentionally state-first:

1. preserve the closed Writer contract and move all reply-form semantics to the
   Writer prompt;
2. delete natural-language gates while retaining non-semantic selection
   validation and DEC-016 degradation;
3. remove the online frequency command/query and make offline rate reporting
   non-normative;
4. preserve durable bundle/delivery/avatar/v0.4 behavior;
5. replace keyword matrices with deterministic boundary tests;
6. run full local verification and prepare a new exact-head review.

Production, Telegram writes, default-avatar application, and Compose restart
remain deferred until implementation is committed, reviewed, approved, merged,
backed up, and built from the exact merge artifact.

## 2. Slice A — Writer Contract And Non-Semantic Sticker Boundary

### Files

- retain `src/group_llm_agent/writer_contract.py`
- simplify `src/group_llm_agent/expression_policy.py`
- update `src/group_llm_agent/events.py`
- update `src/group_llm_agent/model.py`
- update `src/group_llm_agent/writer_prompt.py`
- update `src/group_llm_agent/effector.py`
- update `src/group_llm_agent/runs.py` narrowly for composite run completion
- add/update `tests/test_writer_contract.py`
- update `tests/test_model_client.py`
- update `tests/test_persona_runtime.py`
- update `tests/test_food_effector.py`
- update `tests/test_expression.py`

### Changes

1. Add `WriterDecisionKind.REPLY_WITH_STICKER` and
   `FinalEffectKind.REPLY_WITH_STICKER`.
2. Define the closed composite JSON shape in `writer_contract.py` and expose
   the canonical prompt protocol from the same module.
3. Preserve the bounded composite fields and legacy-compatible sticker audit
   metadata without using it as a semantic denominator.
4. Parse exactly one text and one semantic sticker ID; reject unknown fields,
   raw Telegram identifiers, URLs, and missing snapshots.
5. Update `writer_prompt.py` to make the LLM the sole reply-form semantic
   decision maker. Guide it to avoid stickers in serious/safety/medical/
   permission/relationship-repair/exclusive contexts, prefer them when they
   naturally add emotion/action, and never force a rate. Retain v0.4 food and
   independent Web/context tool budgets.
6. Reject composite output for scheduled requests before effect completion.
7. Delete message/vision keyword regexes, synonym and subject registries,
   prefix/negation parsing, and any equivalent semantic classifier from
   `expression_policy.py`. Keep only enabled catalog, structured relationship
   rank, and consecutive-repeat validation.
8. Keep final text privacy, protocol, deadline, and persona checks unchanged.
9. Apply DEC-016: degrade an invalid composite sticker to the already validated
   text; degrade invalid sticker-only and exhausted invalid/unknown Writer
   output to silence for both direct and contextual paths.
10. Map composite model-run completion to the existing `reply` effect-run
    terminal state.

### Checks

- prompt/schema/parser kind sets are identical;
- valid single- and multi-sentence composite payloads parse;
- second text, second sticker, arbitrary file ID, URL, and extra field fail;
- scheduled composite fails closed while food output remains accepted;
- arbitrary natural-language content cannot change a schema-valid Writer form;
- enabled catalog/digest/ID, structured relationship metadata, scheduled-path,
  and adjacent-repeat guards remain effective;
- static inspection finds no reply-form keyword/regex/synonym/parser gate;
- final-effect leakage/deadline/snapshot regressions remain green.

## 3. Slice B — Migration 6 And Bundle Repository

### Files

- update `src/group_llm_agent/database.py`
- add `src/group_llm_agent/effect_bundle.py`
- add `tests/test_effect_bundle.py`
- update `tests/test_database.py`

### Changes

1. Do not add a new migration; preserve existing migration 6 after scheduled
   food migration 5.
2. Preserve `effect_bundles` with unique chat/event identity,
   bot/persona/catalog snapshots, requested form, legacy-compatible eligibility
   fields, terminal status, and safe reasons.
3. Create `effect_bundle_components` with order, kind, optional semantic ID,
   length-only text metadata, state, platform ID, and safe error category.
4. Add nullable avatar audit columns `operation_id`, `api_method`, and
   `authorization_reference` without rewriting historical rows.
5. Preserve `EffectBundleRepository` transactions for:
   - atomic bundle/component preparation;
   - component compare-and-swap claim;
   - sent/failed/uncertain/skipped completion;
   - bundle terminal derivation;
   - exact chat/event lookup;
   - bounded restart reconciliation;
   - last successfully sent sticker lookup.
   Remove the online seven-day/latest-100 expression metric query.
6. Treat terminal rows as immutable and make duplicate completion idempotent.
7. Do not move controls or scheduled automation into the new tables.

### Checks

- migrations 1–6 apply once and re-initialization is idempotent;
- a production-shaped migrations 1–5 database upgrades without row loss;
- unique bundle insertion has one winner under two repository instances;
- only `planned` may claim `sending`;
- terminal component and bundle rows cannot regress;
- no schema column contains generated text, token, image, or member-sensitive
  data;
- legacy inbound, control, and scheduled `external_effects` remain readable;
- v0.4 tables, indexes, configuration, subscriptions, and occurrences remain
  unchanged.

## 4. Slice C — Ordered Delivery, Replay, And Runtime Wiring

### Files

- update `src/group_llm_agent/effect_delivery.py`
- update `src/group_llm_agent/runtime.py`
- update `src/group_llm_agent/app.py`
- update `src/group_llm_agent/messages.py` only if needed for ordinal event IDs
- update `tests/test_effect_delivery.py`
- update `tests/test_runtime.py`
- update `tests/test_persona_runtime.py`
- update `tests/test_app.py`
- retain and rerun `tests/test_automation_delivery.py` and automation suites

### Changes

1. Inject `EffectBundleRepository` into inbound `ExternalEffectDelivery` and
   `PersonaMessageProcessor`.
2. Prepare all expected components in one transaction before any Telegram call.
3. Implement text-only, sticker-only, and text-first/sticker-second delivery.
4. Resolve the exact enabled mapping immediately before a sticker send and
   retain Telegram returned `file_unique_id` matching.
5. Store distinct outbound event IDs with component ordinals.
6. Implement explicit-failure and uncertain-result matrices exactly as designed;
   remove fallback sends from sticker claims.
7. Reconcile incomplete bundles at process startup and on duplicate event
   replay without any Telegram call.
8. Check bundle, legacy external effect, then existing terminal run state when
   deciding duplicates.
9. Keep control handling and `AutomationDeliveryRepository` on the original
   single-effect path.
10. Record mood only from the final decision as today; do not enable account
    rotation or change the single-chat fail-closed scope count.

### Checks

- five requested visible forms produce the exact component count/order;
- multi-sentence text is one `sendMessage` call;
- text explicit failure prevents sticker call;
- text success/sticker explicit failure ends degraded;
- every uncertain boundary prevents retry/fallback;
- crash before preparation remains recomputable;
- crash after preparation but before send ends interrupted;
- crash after text success but before sticker claim ends text-only degraded;
- crash with a sending component becomes uncertain;
- duplicate/restart never repeats sent or uncertain components;
- scheduled food still claims and sends one text exactly once;
- `/food_enable`, `/food_subscribe`, `/food_status`, and recovery regressions
  remain green.

## 5. Slice D — Online Metric Removal And Offline Evaluation Reference

### Files

- update `src/group_llm_agent/expression_evaluation.py`
- update `src/group_llm_agent/operator_cli.py`
- add `docs/feature/lezhi-avatar-and-expression-v0-3-1/evaluation-cases.json`
- add `tests/test_expression_bundle_evaluation.py`
- update `tests/test_expression_evaluation.py` for backward compatibility
- update `tests/test_operator_cli.py` if present, otherwise add focused CLI tests

### Changes

1. Remove the online `expression-metrics` operator command and bundle
   repository rolling-rate query. Do not add a replacement runtime metric.
2. Keep migration-6 columns readable for compatibility; do not query them as a
   semantic denominator, quota, or correction input.
3. Preserve `reply_with_sticker` in offline evaluation results and report both
   sticker-only and composite as an observed sticker-bearing count.
4. Preserve the immutable v0.3 20-case asset and its digest as historical input.
5. Preserve the canonical v0.3.1 case set as an offline semantic-review input;
   its scenario labels never enter runtime code.
6. Remove the 16–28 / 0.4–0.7 pass condition and automatic semantic guard
   verdicts. Compute deterministic pass only from report contract, snapshots,
   catalog/ID, structured relationship metadata, and adjacent-repeat rules.
7. Keep future evaluation evidence bound to exact case/catalog/persona/model/
   provider/prompt/context snapshots. A new separately authorized provider run
   plus independent review is still required; the existing report is history.

### Checks

- operator CLI exposes no online expression-rate command;
- bundle repository exposes no seven-day/latest-100 semantic denominator;
- sticker-only plus composite are counted only as offline observations;
- 0.39, 0.40, 0.70, and 0.71 all leave deterministic report validity
  unchanged;
- scenario labels and natural-language wording do not change application pass;
- fabricated `passed=true` with invalid computed results is rejected;
- the original v0.3 evaluation set still loads and verifies under its historical
  contract.

## 6. Slice E — Default Avatar API-Success Apply

### Files

- update `src/group_llm_agent/avatar.py`
- update `src/group_llm_agent/operator_cli.py`
- update `tests/test_avatar.py`
- update/add operator CLI tests
- update `deploy/README.md`

### Changes

1. Require `avatar_id=lezhi-default` for this apply command and validate the
   deployment-approved catalog/image digests.
2. Require an explicit authorization reference and safe reason code.
3. Call `getMe` before mutation and require the authenticated ID to equal the
   requested bot ID.
4. Create an operation UUID audit row before the platform write.
5. Call `setMyProfilePhoto` exactly once.
6. On exact `result=true`, record `success` and print operation identity.
7. Classify Bot API rejection/local deterministic failure as `failed`; classify
   timeout, transport, HTTP 5xx, invalid/unknown response, and unexpected
   post-call errors as `uncertain`.
8. Delete the apply path's current profile capture, post-upload readback, digest
   comparison, and automatic rollback/retry.
9. Retain historical `verified` audit compatibility and accept `success` in
   dormant default-baseline/cooldown queries.
10. Leave rotation commands and configuration disabled; do not apply mood
    avatars.

### Checks

- catalog, image, avatar ID, authorization, and bot identity mismatches produce
  zero `setMyProfilePhoto` calls;
- explicit `true` produces one call and `success`;
- API rejection produces `failed`;
- timeout/transport/invalid JSON/invalid response/invalid result produce
  `uncertain`;
- no case automatically retries or rolls back;
- success, failure, and uncertainty make zero post-upload profile/getFile/
  download/vision calls;
- audit contains every required safe field and no token, URL, response body, or
  image bytes.

## 7. Slice F — Documentation, Verification, And Release Carrier

### Files

- add `docs/feature/lezhi-avatar-and-expression-v0-3-1/verification.md`
- update `README.md`
- update `deploy/README.md`
- update `CHANGELOG.md`
- update `.env.example`/`deploy/.env.example` only if a real new setting is
  required; prefer no new runtime flag

### Changes

1. Document reply forms, component outcomes, offline evaluation semantics, and the one-shot
   avatar operation.
2. Record exact test/build commands, result counts, artifact identities, and
   limitations without credentials or full prompts.
3. Record the safe-forward base and prove v0.4 behavior is retained.
4. Record pre/post deployment invariants for 48 mappings, VISION, rotation,
   mood avatars, automation state, and database quick check.
5. Add release and rollback instructions, including no automatic avatar retry.

## 8. Full Verification Matrix

Run on an exact clean snapshot:

```text
python3 -m compileall -q src tests
PYTHONPATH=src:tests uv run python -m unittest discover -s tests -q
uvx ruff check src tests
uvx ruff format --check src tests
uv run mypy src/group_llm_agent
uv build
sh -n deploy/manage.sh
docker compose --env-file <redacted-env> -f deploy/compose.yaml config
git diff --check <base>...<head>
```

Also prove:

- wheel/sdist contain new modules, migration, and immutable v1/v2 persona plus
  v0.3 expression assets;
- isolated installed entry point fails safely without a Telegram token;
- tracked secret/private-key scan is empty;
- exact Docker image runs as the expected non-root user and loads 48 mappings;
- production-shaped database backup and upgraded copy both pass quick check;
- v0.4 scheduler/control focused suites remain green;
- configured Writer provider evidence remains explicitly deferred because this
  revision does not authorize a provider call; old evidence is not reused as
  proof of the new contract.

## 9. Commit And Review Plan

Use phase/slice commits that keep review boundaries clear:

1. writer contract and expression policy;
2. migration 6, bundle repository, delivery, and runtime integration;
3. online metric removal/offline evaluation reference and avatar API-success path;
4. documentation, changelog, and verification carrier.

Push after coherent green slices. Create one non-draft PR targeting `main`.
The PR must name the exact safe-forward base/head, migration 6, preserved v0.4
behavior, partial-failure semantics, avatar authorization, tests, external
limitations, deployment plan, and rollback.

Use the configured Review task for an immutable exact-head review. Do not merge
without an accepted APPROVE result and explicit merge authorization under the
workflow policy.

## 10. Post-Review Release Plan

After approval, merge authorization, and merge proof:

1. fetch exact merged `main` and build an immutable image;
2. snapshot current Compose config, image, database, mappings, feature flags,
   v0.4 automation config, and bot identity;
3. back up SQLite and prove both current and backup `quick_check=ok`;
4. deploy the exact image and apply migration 6;
5. verify startup, Telegram polling, v0.4 status commands, 48 mappings, VISION
   disabled, rotation disabled, and no mood-avatar write;
6. perform bounded text-only, sticker-only, and text+sticker group UAT;
7. execute exactly one authorized default-avatar apply;
8. record API result/operation ID and request manual visible-avatar observation;
9. if runtime verification fails, restore the prior image/config and database
   backup as necessary without republishing stickers or retrying the avatar;
10. complete post-merge/deployment traceability with exact SHAs and remaining
    operational limitations.

## 11. Definition Of Done

The feature is complete only when all of the following are proven:

- confirmed requirements, design, and plan are committed on the safe-forward
  branch;
- implementation and migration satisfy every REQ-001–REQ-034 and AC-001–AC-018;
- full deterministic/build/package/container checks pass;
- independent exact-head review has no open finding;
- the approved PR is merged with recorded merge SHA;
- production database backup and migration succeed;
- production preserves v0.4 and all stated feature invariants;
- real Telegram UAT demonstrates bounded reply forms;
- the single authorized default-avatar operation has a terminal API/audit
  outcome;
- post-merge/deployment traceability is recorded without claiming manual visual
  observation as an automated success gate.
