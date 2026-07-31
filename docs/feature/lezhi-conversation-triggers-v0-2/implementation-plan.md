# Implementation Plan: 乐枝对话连续性触发 v0.2

- Status: Ready for implementation
- Requirements: `requirements.md` at `1e467fe7942ae057424e8600eb493759d4bc456c`
- Design: `design.md` at `b25a25bc7633f4f8761d68cbe5322ee91c9e18c1`
- Branch: `codex/lezhi-conversation-triggers-v0-2`
- Written: 2026-07-31

## 1. Delivery Contract

The implementation must satisfy all twenty confirmed requirements and all fifteen acceptance
criteria without changing the following prior contracts:

- one Telegram external effect per current-group inbound event;
- direct failure may produce one neutral failure reply, contextual failure is silent;
- Character Bundle id/version/digest is identical across Trigger and Effector;
- at most twenty recent current-group texts are assembled;
- Writer uses at most three model calls and two registered read-only tool calls;
- member recognition, retention, reset, privacy, and group isolation remain unchanged;
- group text cannot configure trigger policy, aliases, windows, priority, or safety;
- fixed mode and memory-control command behavior remain compatible.

The implementation is complete only when the deterministic AC matrix, full regression suite,
static checks, package checks, deployment checks, and available container checks are recorded in
`verification.md` against an immutable implementation snapshot.

## 2. Planned Package Boundaries

```text
src/group_llm_agent/
  addressing.py             # pure Character Bundle name-address classifier
  continuity.py             # anchor eligibility and four-way structured decider
  events.py                 # trigger categories, continuity decisions and metadata
  persona.py                # compile immutable formal-name address terms
  model.py                  # exact continuity response parser
  context.py                # optional actual outbound continuity anchor
  database.py               # additive migration 2 and audit schema
  runs.py                   # final trigger evaluation and effect-category persistence
  trigger.py                # priority coordinator and ordinary fallback orchestration
  runtime.py                # mode behavior, replay terminality and one-effect integration
  app.py                    # production wiring only

tests/
  test_addressing.py
  test_continuity.py
  test_conversation_trigger_runtime.py
  test_persona.py
  test_model_client.py
  test_context.py
  test_database.py
  test_trigger.py
  test_persona_runtime.py

docs/feature/lezhi-conversation-triggers-v0-2/
  requirements.md
  design.md
  implementation-plan.md
  verification.md
```

New focused modules prevent the existing `trigger.py`, `model.py`, and runtime modules from
absorbing unrelated lexical and continuity policy logic.

## 3. Slice 1 — Application-Owned Contracts and Migration

### Files

- `src/group_llm_agent/events.py`
- `src/group_llm_agent/database.py`
- `src/group_llm_agent/runs.py`
- `tests/test_database.py`

### Changes

1. Add a stable `TriggerCategory` enum:
   `direct_platform`, `direct_persona_name`, `conversation_continuity`,
   `ordinary_contextual`, `control`, and `ignored`.
2. Add `PlatformTriggerKind.CONTINUITY_CANDIDATE` while preserving existing enum values.
3. Add continuity result types for `continue`, `close`, `not_addressed`, and `ambiguous`.
4. Extend platform decision metadata with a persona-name hit flag and optional anchor message ID.
5. Extend `EffectRequest` with `trigger_category`; keep `TriggerPath.DIRECT` and
   `TriggerPath.CONTEXTUAL` as the existing failure-semantics boundary.
6. Add migration 2:
   - additive `effect_runs.trigger_category`, default/backfill direct versus contextual rows;
   - `trigger_evaluations` with one final record per request/event and no content fields;
   - current-group/event lookup index.
7. Add `RunRepository.record_trigger_evaluation` as an idempotent upsert.
8. Add `RunRepository.has_terminal_trigger_evaluation`; only final ignore/silence/close records are
   terminal. `effect_requested` remains resumable before an external-effect claim.
9. Persist `EffectRequest.trigger_category` in `start_effect_run`.

### Checks

- Migration applies to a new database and an existing migration-1 database.
- Existing direct/contextual effect rows receive correct categories.
- Invalid enum/category values fail at application or schema boundary.
- Final audit upsert contains category, hit flag, anchor, decision, reason, model status, and exact
  persona snapshot, but no text/prompt/provider fields.
- External-effect uniqueness remains unchanged.

### Commit intent

`feat: add conversation trigger contracts and audit schema`

## 4. Slice 2 — Character Address Vocabulary and Matcher

### Files

- `src/group_llm_agent/persona.py`
- `src/group_llm_agent/addressing.py` (new)
- `tests/test_persona.py`
- `tests/test_addressing.py` (new)
- `tests/test_production_persona.py`

### Changes

1. Compile `CharacterBundle.direct_address_terms` from the validated formal character name.
2. Reject an empty, oversized, control-character-containing, or structurally invalid name during
   bundle validation.
3. Implement a pure Unicode-normalizing matcher returning `none`, `direct`, or `mention_only` plus
   a stable reason.
4. Match standalone, opening-vocative, ending-vocative, punctuation/spacing, and bounded compact
   request forms. Ending vocatives require positive second-person or bounded question/request
   evidence; separators and whitespace alone are not address evidence.
5. Exclude balanced quoted spans, possessives, reports/history, lists, third-person references,
   another-member address, and uncertain mid-sentence uses.
6. Never mutate the address tuple from messages or model output.

### Checks

- Positive production cases include all AC-001 strings and formatting variants.
- Negative production cases include all AC-002 strings, quoted name text, reported speech,
  another-member address, a persona name as the final list member, whitespace-separated
  third-person statements, and injection attempts.
- Test persona names and the production `乐枝` name bind to their existing persona digest.
- No Character Bundle content/digest change is required for the derived formal name.

### Commit intent

Included with Slice 3 as one coherent trigger-classification commit after both unit suites pass.

## 5. Slice 3 — Continuity Eligibility, Context, and Protocol

### Files

- `src/group_llm_agent/continuity.py` (new)
- `src/group_llm_agent/context.py`
- `src/group_llm_agent/model.py`
- `src/group_llm_agent/messages.py` only if a focused current-group anchor helper is needed
- `tests/test_continuity.py` (new)
- `tests/test_context.py`
- `tests/test_model_client.py`

### Changes

1. Select the latest outbound authenticated-bot message from the current retained group scene.
2. Enforce age `<= 10 minutes`, subsequent human count `<= 5`, current-group authorship, actual
   outbound direction, available retained text, no future timestamp, and causal order. Compare the
   current Telegram timestamp and anchor at whole-second precision and require the current message
   to be strictly later; equal seconds fail closed because order is unprovable.
3. Carry the exact anchor into `TriggerContext`; resolve by message ID from the same bounded scene.
4. Add the exact four-kind response schema and `parse_continuity_decision` with strict fields and
   stable reason-code validation.
5. Build the continuity system/user messages with application definitions and untrusted group
   context separation.
6. Use the existing Trigger model role, temperature zero, no tools, a five-second deadline, and
   the exact Trigger Character view.
7. Return a typed failed result for timeout, provider error, invalid result, missing anchor, or
   persona-snapshot mismatch; the coordinator owns ordinary fallback.

### Checks

- Exact boundary cases: 10:00 accepted, 10:00 plus one microsecond rejected; five humans accepted,
  six rejected.
- Other-group, inbound-as-anchor, wrong-bot, future, missing, expired/purged, and unsent candidates
  are rejected.
- Transient and persisted messages sent before a later anchor, including a second update already
  present in the same polling batch, cannot use that anchor; a later-poll next-second reply remains
  eligible.
- All four legal outputs parse; unknown kind, extra field, prose, invalid reason, and protocol
  injection fail closed.
- Prompt, schema, and parser operation sets are derived from one application-owned tuple.
- Context remains at most twenty current-group retained texts and preserves the exact persona
  snapshot.

### Commit intent

`feat: classify persona address and conversation continuity`

## 6. Slice 4 — Priority Coordinator and Runtime Integration

### Files

- `src/group_llm_agent/trigger.py`
- `src/group_llm_agent/runtime.py`
- `src/group_llm_agent/app.py`
- `tests/test_trigger.py`
- `tests/test_persona_runtime.py`
- `tests/test_conversation_trigger_runtime.py` (new)

### Changes

1. Pass the active immutable bundle to pre/post-ingest platform classification.
2. Apply priority exactly:
   group/self/control → Telegram explicit direct → persona-name direct → continuity → ordinary.
3. Use name-direct as a direct effect with no participation-model call.
4. For an eligible continuity anchor:
   - `continue` creates a contextual-failure-semantics effect categorized continuity;
   - `close` records terminal intentional silence;
   - `not_addressed`, `ambiguous`, and failures enter the unchanged ordinary cadence path.
5. Ordinary fallback calls the existing participation decider only if its hard cadence is ready.
6. Record one final trigger evaluation after fallback resolves, in addition to per-model-call
   `trigger_runs`.
7. Allow continuity in both `persona_direct` and `persona_full`; continue excluding only ordinary
   proactive participation from `persona_direct`.
8. On duplicate ingestion with no external-effect claim:
   - return duplicate for terminal close/ignore/silence;
   - recompute effect-requested or missing work;
   - retain current at-most-once claim behavior after a claim.
9. Keep Writer context, tool budgets, final validation, reply-to-current-message behavior, send
   uncertainty, and outbound recording order unchanged.

### Checks

- Explicit Telegram direct plus name produces one direct path and no Trigger model call.
- Control plus name remains control.
- Name direct bypasses cooldown/cadence in both persona modes.
- Continuity continue bypasses ordinary cadence; natural close sends nothing.
- Unrelated/ambiguous/failure follows ordinary cadence and does not masquerade as continuity.
- Sixth-message/expired anchor follows ordinary cadence.
- Two model calls occur only when continuity falls back and ordinary cadence is itself eligible.
- Self and other-group messages never call either classifier.
- Same inbound event never yields more than one external effect.

### Commit intent

`feat: integrate Lezhi responsive conversation triggers`

## 7. Slice 5 — Acceptance Matrix and Regression Proof

### Files

- `tests/test_conversation_trigger_runtime.py`
- targeted existing test files listed above
- `docs/feature/lezhi-conversation-triggers-v0-2/verification.md`

### Required AC proof

| AC | Deterministic proof |
| --- | --- |
| AC-001 | Three confirmed name-address examples are direct and bypass ordinary cadence |
| AC-002 | Three discussion/quote examples are not name-direct |
| AC-003 | Direct answer to the bot's question anchors the actual sent message and replies |
| AC-004 | Follow-up/reaction anchors and continues without explicit Telegram addressing |
| AC-005 | `收到`, `好哒`, and `哈哈行` are intentional close/silence |
| AC-006 | Time adjacency without semantic relation falls back, not continuity |
| AC-007 | Multiple plausible addressees return ambiguity and do not guess |
| AC-008 | Other-group, private-equivalent fixture, and unsent candidate cannot anchor |
| AC-009 | Every mixed signal follows the confirmed single priority path |
| AC-010 | Self-message and duplicate-signal/event cases produce zero/one effect |
| AC-011 | Alias/window/safety override text cannot mutate application contracts |
| AC-012 | Audit distinguishes all categories and records actual anchor/reason safely |
| AC-013 | Continuity failure is silent/fallback; explicit direct failure degrades once |
| AC-014 | Snapshot, memory, group, tools, facts, and safety contracts remain unchanged |
| AC-015 | Full critical fixture matrix has zero false-positive or duplicate-send cases |

### Full checks

Run from a clean exact snapshot:

```text
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
uvx ruff check src tests
uvx ruff format --check src tests
uv run mypy src
uv build
sh -n deploy/manage.sh
docker compose --env-file <redacted-test-env> config
```

Also verify:

- installed wheel entry point safe failure with missing Telegram token;
- wheel contains new modules and the production persona bundle;
- repository credential/private-key pattern scan returns no tracked matches;
- Docker build and one-shot bundle load when the daemon is available;
- no `.env`, provider body, raw prompt, local database, proof dump, or build output is tracked.

## 8. Slice 6 — Public Documentation and Release Record

### Files

- `README.md`
- `.env.example` only if wording is needed; no new setting is planned
- `deploy/README.md`
- `CHANGELOG.md`
- `docs/feature/lezhi-conversation-triggers-v0-2/verification.md`

### Changes

1. Document name-address and continuity behavior, natural-close silence, eligibility bounds, and
   ordinary fallback in operator/user language.
2. State that aliases are not learned and group messages cannot configure trigger policy.
3. Document no new inbound port/webhook/network exposure and no new environment variable.
4. Add an Unreleased changelog entry with behavior, safety/failure boundary, migration, and
   rollback note.
5. Record exact implementation and verification SHAs, commands, results, unavailable external
   proof, and known operational follow-ups.

### Commit intent

`docs: record Lezhi trigger v0.2 verification`

## 9. Rollout and Rollback Plan

### Rollout

1. Build and verify the exact candidate image.
2. Preserve the current database volume and external `.env`.
3. Start in the authorized target group with existing persona mode and credentials.
4. Confirm startup identity, bundle digest, migration version, polling, and no credential output.
5. Run operator-owned smoke messages for name direct, answer continuity, natural close, unrelated
   adjacency, and explicit mention regression.
6. Inspect safe trigger audit categories and anchor IDs without reading or exporting extra text.

### Rollback

1. Stop the candidate container.
2. Restore the prior reviewed image with the same external environment and database volume.
3. The prior binary ignores the additive table/column and resumes old platform-direct/ordinary
   behavior.
4. Do not delete the new audit records merely to roll back behavior.

## 10. Deferred External Proof

- Real Telegram group smoke requires the exact reviewed head, operator permission, target-group
  messages, Telegram credentials, and provider consumption authorization.
- Independent persona-quality scoring remains separate from deterministic trigger correctness.
- Provider compatibility is covered by the existing structured OpenAI-compatible client contract;
  real provider continuity probing is useful UAT evidence but not a replacement for schema/parser
  tests.
- Meal recommendation, learned aliases, media/private triggers, and longer memory remain deferred.

## 11. Completion Gate

Implementation may proceed after the repository maintainability gate confirms the planned narrow
module additions and targeted edits. F4 is not complete until every slice is committed, the branch
is clean, all intended commits are pushed, and the implementation is reconciled requirement by
requirement. F6 review dispatch is forbidden until an open non-draft PR matches the local full
40-character head SHA and all available checks are green or explicitly limited.
