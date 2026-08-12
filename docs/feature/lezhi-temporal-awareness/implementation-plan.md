# Implementation Plan: 乐枝当前时间与时效信息感知

- Phase: F3 Implementation Plan
- Status: Implemented And Verified — Awaiting Exact-Head Review
- Confirmed requirements: `12e200df19dc168f2c6d476359fceef9b0251bd6`
- Requirements handoff: `ef5321a8655cc8cc2d0232e673eb8ee78d755893e8fe07ae30da56e23a990964`
- Technical design: `b7f09f6bf021aa4e98bfaf7fa38b70f2d749cdbf`
- Forward baseline: `origin/main@71c7eb3b60b08f3dd0d2229dee9873a8a76cca93`
- Branch: `codex/lezhi-temporal-awareness`
- Plan date: 2026-08-11

## 1. Delivery Contract And Authorization Boundary

Implementation will add a fresh application-owned temporal context to every Writer
model call, expose one budget-free current-turn IANA timezone selection, attach actual
message timestamps to the Writer scene, bind declared current facts to current-turn Web
evidence, and persist bounded temporal audit metadata.

The completed feature must satisfy REQ-001–REQ-025 and AC-001–AC-014 without:

- using natural-language keyword/regex/synonym/parser gates for Web necessity;
- using Web, Telegram timestamps, or model knowledge as the current clock;
- increasing the five-call Web budget or sharing it with context-tool budget;
- creating a second persisted group-timezone source;
- regressing v0.4 automation/Web, v0.3.1 reply forms, migrations 1–6, trigger behavior,
  expression delivery, member memory, or effect idempotency.

The confirmed Requirements handoff first authorized F2 and F3. The later authorized
GoalRun continued this plan through implementation and deterministic verification.
Real model/Tavily calls, deployment, container replacement, production SQLite work,
and Telegram operations require their own later gates.

## 2. Delivery Order And Commit Strategy

Use narrow, independently testable commits in this order:

1. baseline/maintainability proof;
2. temporal core and group-timezone adapter;
3. migration 7 and dedicated temporal audit repository;
4. message/prompt/Writer structured temporal contract;
5. effector loop integration, timezone selection, and freshness finalization;
6. Tavily/Web evidence provenance;
7. scheduled/runtime composition and cross-feature regression;
8. exact-snapshot verification, documentation, and ReviewRequest carrier.

Do not squash implementation slices locally. Preserve phase and remediation history for
exact-head review. Every slice runs targeted tests and `git diff --check`; full checks
run before the ReviewRequest.

## 3. Slice 0 — Baseline And Maintainability Gate

### Inputs

- `src/group_llm_agent/effector.py` — currently 806 lines
- `src/group_llm_agent/runs.py` — currently 792 lines
- `src/group_llm_agent/database.py` — currently 845 lines, primarily migration SQL
- `src/group_llm_agent/writer_prompt.py`
- `src/group_llm_agent/web_tools.py`
- `src/group_llm_agent/tavily.py`
- exact `origin/main@71c7eb3b60b08f3dd0d2229dee9873a8a76cca93`

### Actions

1. Reconfirm the feature branch is a descendant of the exact baseline and the worktree
   contains no unrelated changes.
2. Run baseline compileall, full unit discovery, Ruff check/format, project Mypy,
   package build, shell syntax, and `git diff --check`.
3. Record existing failures separately; do not “fix” unrelated behavior in a temporal
   slice.
4. Keep temporal state/calculation in new `temporal.py` and persistence in new
   `temporal_audit.py`.
5. Do not add temporal repository methods to `RunRepository`; pass effect-run identity
   to the dedicated audit repository.
6. Limit `effector.py` changes to orchestration hooks and final decision routing. Move
   temporal/freshness validation and rendering helpers into `temporal.py`.
7. Do not introduce a generic date/time utility package or duplicate timezone source.

The repository's older `product-workflow-gate` skill is absent from the current
checkout/session. The implementation uses the accepted Feature Lifecycle gate and the
explicit module-size/refactoring decision above; the missing local skill is recorded as
an environment limitation, not silently claimed as executed.

### Exit checks

- exact baseline proof is recorded;
- no unrelated workspace file is modified;
- new production modules have a single owner and target fewer than 500 lines;
- no new temporal persistence enters `runs.py`;
- no implementation begins if explicit post-F3 authorization is absent.

### Commit intent

No behavior commit; baseline results go into the later verification carrier.

## 4. Slice 1 — Temporal Core And Group Timezone

### Files

- add `src/group_llm_agent/temporal.py`
- update `src/group_llm_agent/automation.py` with a narrow read adapter only if needed
- add `tests/test_temporal.py`
- update `tests/test_automation.py`
- update `tests/helpers.py` with a deterministic sequence clock only if reused broadly

### Changes

1. Define immutable `TemporalContext`, `TemporalContextError`, `Clock` protocol,
   production UTC clock, and deterministic context-ID generation.
2. Implement exact IANA validation through `ZoneInfo`; reject fixed offsets, naive
   values, missing offsets, conversion failures, and UTC/local inconsistencies.
3. Render UTC/local RFC3339 values, `±HH:MM`, local date, ISO weekday number, stable
   weekday name, source class, group timezone, and selection class.
4. Add a `GroupTimezoneProvider` protocol plus an adapter over the existing
   `AutomationRepository.get_config`. Missing config returns `Asia/Shanghai`; invalid
   persisted data fails closed rather than falling back.
5. Implement `TemporalSession` with immutable group zone, optional one-turn override,
   model-call ordinal, and one-selection maximum. Never cache a time snapshot.
6. Implement exact `select_answer_timezone` argument validation and in-memory session
   transition. It accepts one IANA key only and performs no database/member-memory
   write.
7. Implement current/recent-message timestamp conversion helpers that retain the
   stored occurrence instant and expose UTC plus target-local forms.

### Checks

- frozen `2026-08-11T04:34:20Z` produces Shanghai `12:34:20+08:00`, correct date and
  weekday;
- New York winter/summer instants produce correct EST/EDT offsets;
- Shanghai midnight boundaries and New York DST gap/fold use `ZoneInfo` rules;
- naive clock, invalid IANA, numeric offset, inconsistent offset, and out-of-range
  conversion fail with safe typed codes;
- each snapshot call gets the next sequence-clock value and a distinct context ID;
- one session cannot select twice or leak a selected zone to another session;
- missing group config yields Shanghai; valid disabled/paused config still supplies its
  configured timezone; corrupted config fails closed;
- no Web/context budget object is touched.

### Commit intent

`feat: add authoritative temporal context`

## 5. Slice 2 — Migration 7 And Temporal Audit Repository

### Files

- update `src/group_llm_agent/database.py`
- add `src/group_llm_agent/temporal_audit.py`
- update `tests/test_database.py`
- add `tests/test_temporal_audit.py`

### Changes

1. Add migration 7 after composite-bundle migration 6 without editing migrations 1–6.
2. Create `temporal_context_samples` with unique `(effect_run_id,
   model_call_ordinal)`, bounded enums/counts, context identity, capture time, timezone,
   offset, selection, status, and safe error code.
3. Create `temporal_answer_audit` keyed by `effect_run_id` with final context,
   freshness mode, Web-request flag, same-effect audit IDs, latest retrieval time,
   terminal status, and degradation code.
4. Add indexes for effect lookup and bounded operations diagnostics; no prompt/message
   text, model body, URL, token, secret, member memory, or source content is stored.
5. Implement `TemporalAuditRepository` methods:
   - record valid/failed model-call sample exactly once;
   - finalize a completed/degraded/failed/silence answer exactly once;
   - validate ownership of Web audit IDs before storing them;
   - fetch bounded rows for tests/operator diagnostics.
6. Use application timestamps from the same injected clock where semantics require it;
   database bookkeeping timestamps may use UTC but are never presented as answer time.
7. Make terminal rows immutable/idempotent for replay. Conflicting re-finalization is an
   integrity error.

### Checks

- migrations 1–7 initialize and reopen idempotently;
- a database at exact migration 6 upgrades with all messages, effects, bundles,
  automation, memory, avatar, and tool audit rows preserved;
- sample ordinal/context uniqueness has one winner under concurrent repositories;
- maximum model ordinal is enforced and negative/oversized/invalid fields fail;
- Web audit IDs must belong to the same effect and be `budget_kind='web'`;
- failed clock before model call still creates a bounded failed answer audit;
- terminal audit cannot regress or be rebound to another effect;
- `PRAGMA quick_check` returns `ok` on upgraded fixtures.

### Commit intent

`feat: audit temporal answer context`

## 6. Slice 3 — Writer Scene And Structured Temporal Contract

### Files

- update `src/group_llm_agent/context.py`
- update `src/group_llm_agent/writer_contract.py`
- update `src/group_llm_agent/model.py`
- update `src/group_llm_agent/writer_prompt.py`
- update `src/group_llm_agent/events.py` only for typed final metadata if required
- update `tests/test_context.py`
- add/update `tests/test_writer_contract.py`
- update `tests/test_model_client.py`
- update `tests/test_writer_prompt_policy.py`

### Changes

1. Keep `EffectContext` free of a reusable current-time snapshot; pass a
   `TemporalContext` separately to `build_writer_model_messages` for each call.
2. Add actual `occurred_at_utc`, `occurred_at_target_local`, and target timezone to the
   current inbound source and every recent-scene item. Keep sender/text bounds and order
   unchanged.
3. Render scheduled `planned` and `execution_now` blocks separately, retaining
   occurrence local date, slot, planned timezone, and planned UTC instant.
4. Add one trusted `AUTHORITATIVE_TEMPORAL_CONTEXT` system block outside all untrusted
   group/Web envelopes. State that message and Web timestamps cannot override it.
5. Add prompt rules for:
   - pure clock/timezone conversion uses `mode=clock` and zero Web;
   - stable/creative/group-only answers may use `mode=stable` and zero Web;
   - changing external state uses Web when available;
   - ambiguous target timezone is clarified, not guessed;
   - stale/conflicting evidence yields uncertainty;
   - retrieval/publication/update/event times are distinct;
   - current verified claims use 1–3 source result IDs;
   - Web queries contain only minimal public semantics.
6. Add `temporal_context_id` to every Writer schema branch and canonical prompt shape.
7. Add the closed freshness object to `reply`/`reply_with_sticker`, and context ID to
   sticker/silence/food/tool decisions.
8. Register `select_answer_timezone` only while another model round remains and the
   session has not already selected a zone.
9. Extend typed `WriterDecision` with context ID, freshness mode, and immutable source
   result IDs. Parser rejects unknown fields, duplicates, more than three IDs, malformed
   IDs, and illegal mode/source combinations.
10. Keep sticker, food, context-tool, and Web-tool shapes otherwise byte-for-byte
    compatible in meaning.

### Checks

- prompt/schema/parser decision kind and required-field sets agree;
- every decision without a context ID or with a stale/unknown ID is rejected;
- stable/clock require empty sources; verified requires 1–3 unique `web:N` IDs;
- unverified accepts only zero to three bounded IDs;
- current/recent scene exposes actual UTC and target-local timestamps;
- no scene timestamp is derived from list order or current time;
- scheduled prompt clearly contains both planned and execution timestamps;
- Web-necessity guidance contains no application keyword registry or parser;
- existing LLM-owned sticker-form boundary remains unchanged.

### Commit intent

`feat: bind Writer decisions to temporal context`

## 7. Slice 4 — Effector Integration And Freshness Finalization

### Files

- update `src/group_llm_agent/effector.py`
- update `src/group_llm_agent/temporal.py`
- update `src/group_llm_agent/writer_contract.py` if contract helpers are needed
- update `tests/test_effector.py`
- update `tests/test_food_effector.py`
- update `tests/test_expression_policy.py` only for compatibility fixtures

### Changes

1. Inject `Clock`, `GroupTimezoneProvider`, and `TemporalAuditRepository` into
   `WriterEffector`; retain current defaults in application composition.
2. Create one temporal session after `start_effect_run` and before context assembly.
3. Sample/validate/audit immediately before each model call, then build messages and
   call the model with no intervening provider/tool operation.
4. Raise the bounded model-call ceiling from 11 to 12 and reserve at most one round for
   timezone selection plus ten existing context/Web rounds and one final round. The
   request deadline remains the absolute stop and no hidden retry is added.
5. Execute `select_answer_timezone` locally. Do not add it to tool results, context/Web
   counters, cumulative external-result characters, or `tool_call_audit`. Record only
   the session transition and next temporal sample.
6. Pass the current context ID to `parse_writer_decision`; treat any mismatch as a
   protocol error with existing bounded repair behavior.
7. Validate final freshness against the `WebToolSession` evidence registry:
   - stable/clock: no sources;
   - current verified: 1–3 same-turn safe sources with retrieval times;
   - current unverified: no verified footer;
   - no semantic prose scan.
8. Render verified/unverified application-owned footer/boundary in `temporal.py`, then
   pass the resulting text through existing length, leakage, persona-snapshot, and
   deadline validation. If the bounded footer would exceed 4096 characters, fail closed
   rather than truncating a source identity.
9. Populate `FinalEffect.source_urls` for ordinary verified replies, preserving
   scheduled food behavior.
10. Finalize temporal audit before completing the effect run. A temporal audit failure
    cannot yield a completed/sent response.
11. Ensure direct failure and contextual/scheduled silence behavior stays consistent
    with existing degradation contracts.

### Checks

- sequence clock changes before each scripted model call, including after context/Web
  tools and protocol repair;
- final decision accepts only its own latest context ID;
- restart/new effector does not reuse a prior snapshot;
- exact Shanghai current-time scripted response uses zero Web calls;
- one timezone selection changes the next call to New York with correct DST and no tool
  counter change;
- invalid/second selection never persists or calls a provider;
- model calls never exceed 12 and the existing shared deadline terminates long loops;
- `current_verified` foreign/missing/stale/unsafe/no-retrieval sources fail closed;
- verified footer has exact target timezone and 1–3 current-turn URLs;
- unverified path cannot receive a verified footer;
- existing reply/composite/sticker/silence/food/deadline/leakage/catalog tests pass.

### Commit intent

`feat: enforce fresh time in Writer loop`

## 8. Slice 5 — Tavily And Web Evidence Provenance

### Files

- update `src/group_llm_agent/tavily.py`
- update `src/group_llm_agent/web_tools.py`
- update `tests/test_tavily.py`
- update `tests/test_web_tools.py`
- update `tests/test_food_effector.py`

### Changes

1. Inject/use a timezone-aware clock for provider retrieval time; reject naive results.
2. Extend search/extract result types with optional strict `published_at`,
   `updated_at`, and bounded `provider_time_text`.
3. Parse provider publication/update values only when they are unambiguous
   timezone-aware instants. Preserve an otherwise bounded provider string as untrusted
   text or null; never fabricate an instant.
4. Include distinct retrieval/publication/update fields in untrusted prompt payloads.
5. Add bounded immutable `WebEvidence` records keyed by current-turn result ID, with
   normalized URL, timestamps, and search/fetch audit identities.
6. Expose a read-only evidence selection method used by the effector. It returns only
   successful, current-session, public-URL-validated records.
7. Continue counting every invalid/failed/rejected Web attempt against the shared five
   calls. Keep provider request ID/credits/domain/retrieval audit behavior.
8. Keep provider titles/content outside application-owned final provenance footer.
9. Preserve SSRF/DNS/public-routing, duplicate, result-size, deadline, and query privacy
   bounds.

### Checks

- exact fake responses preserve valid published/updated instants and retrieval time;
- missing/malformed/relative provider time is never promoted to an absolute timestamp;
- search/fetch payload labels retrieval versus publication/update distinctly;
- fetch inherits result identity and cannot drift URL or cross a session;
- evidence IDs from another effect/turn and raw model URLs are rejected;
- title/snippet prompt injection cannot modify temporal context, budgets, or footer URL;
- five attempts include timeout/invalid/empty/rejected; sixth reaches neither fake nor
  real provider;
- context-tool counts remain independent;
- existing scheduled food citations remain green.

### Commit intent

`feat: retain Web freshness provenance`

## 9. Slice 6 — Application And Scheduled Runtime Composition

### Files

- update `src/group_llm_agent/app.py`
- update `src/group_llm_agent/scheduled_food.py`
- update `src/group_llm_agent/runtime.py` only if constructor composition requires it
- update `tests/test_app.py`
- update `tests/test_scheduled_food.py`
- update `tests/test_persona_runtime.py`
- update `tests/test_automation_runtime.py`
- update `tests/test_conversation_trigger_runtime.py`

### Changes

1. Construct one production clock, automation-backed timezone provider, and temporal
   audit repository from the existing database/application graph.
2. Inject them into inbound and scheduled uses of the same `WriterEffector`.
3. Ensure scheduler occurrence creation/lease/claim remains unchanged; only Writer
   prompt time metadata expands.
4. Preserve planned occurrence local date/slot/timezone when execution is delayed.
5. Keep Web unavailable when the existing feature gate/key is absent while retaining
   clock-only answers.
6. Preserve process startup, polling, recognition, trigger, control, expression bundle,
   and automation worker lifecycle behavior.
7. Do not add a new environment variable for time or timezone; production uses system
   UTC plus the existing group config/default.

### Checks

- application starts with no Tavily key and can still assemble authoritative time;
- ordinary inbound and scheduled calls share identical temporal context schema;
- delayed scheduled call shows planned and execution timelines distinctly;
- automation disabled/paused does not remove an existing group timezone;
- no-config group uses Shanghai;
- two groups with different configured zones never share a snapshot/session;
- process restart samples a new time;
- Telegram polling/recognition/control/expression/food regressions remain green;
- no production state or external network is touched in tests.

### Commit intent

`feat: wire temporal awareness into runtime`

## 10. Slice 7 — Documentation, Verification, And Review Carrier

### Files

- add `docs/feature/lezhi-temporal-awareness/verification.md`
- update `README.md`
- update `CHANGELOG.md`
- update `deploy/README.md` only for operator clock-health/release checks
- avoid `.env.example` and Compose changes unless implementation proves an actual need

### Documentation

1. Explain the application-clock/Writer/Web responsibility boundary.
2. Document effective group timezone, explicit current-turn override, ambiguity
   behavior, source footer, and Web-unavailable behavior.
3. Document that the host must maintain system clock synchronization and that runtime
   rejects naive/inconsistent time.
4. Document migration 7 backup/upgrade/quick-check and rollback expectations without
   performing production migration.
5. Record exact tests, package contents, candidate-image status if later authorized,
   tracked-secret scan, and known limitations.
6. State that no provider/Tavily/Telegram/deployment proof exists unless separately
   authorized and actually run.

### Exact clean-snapshot verification

```text
python3 -m compileall -q src tests
PYTHONPATH=src:tests uv run python -m unittest discover -s tests -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src/group_llm_agent
uv build
sh -n deploy/manage.sh
docker compose --env-file <redacted-test-env> -f deploy/compose.yaml config
git diff --check <exact-base>..<exact-head>
tracked-file credential/private-key pattern scan
```

Compose rendering and Docker work occur only if allowed by the environment and current
phase. No secret value, provider body, configured non-official base URL, full prompt,
or Telegram content is printed in verification evidence.

### Required controlled matrix

- Shanghai `2026-08-11 12:34:20+08:00`, minute display, zero Web;
- fresh ten-minute second turn and restart;
- New York standard/DST and ambiguous location clarification;
- Shanghai midnight and New York DST boundary;
- historical “今晚” message timestamps and absolute-date disambiguation;
- delayed scheduled planned/execution split;
- stable zero-Web versus current-weather Web decision using scripted model;
- Web success with 1–3 sources and correct retrieval-time footer;
- timeout, limit, empty, stale, conflicting, unavailable, and malformed evidence;
- five context + five Web + optional timezone selection within separate counters;
- unknown tool/invalid args/stale context ID/invalid source IDs fail closed;
- prompt injection and minimal-query/privacy bounds;
- complete existing 1–6 migration, v0.4, v0.3.1, trigger, memory, expression, delivery,
  package, and startup regressions.

### Review preparation

1. Freeze a clean exact-head archive and rerun every declared check there.
2. Ensure `verification.md` distinguishes supplied evidence from independently run
   evidence and records all limitations.
3. Commit the implementation evidence, then a documentation-only carrier if needed.
4. Push the exact branch head.
5. Create/update a PR against current `main`, requiring exact base/head proof.
6. Dispatch a new immutable ReviewRequest with `mergeOnApprove=false` unless the user
   separately changes merge policy.
7. Do not merge, deploy, migrate production data, call providers, or send Telegram
   messages from Main while review is pending.

### Commit intent

`docs: verify temporal awareness`

## 11. Acceptance Traceability By Slice

| Acceptance criteria | Primary slices |
| --- | --- |
| AC-001 current Shanghai time and zero Web | 1, 3, 4, 6, 7 |
| AC-002 fresh turns/restart/audit | 1, 2, 4, 6, 7 |
| AC-003 explicit/ambiguous target timezone | 1, 3, 4, 7 |
| AC-004 historical relative message time | 1, 3, 7 |
| AC-005 scheduled planned/execution time | 3, 4, 6, 7 |
| AC-006 semantic stable/current Web choice | 3, 4, 5, 7 |
| AC-007 as-of time and 1–3 sources | 3, 4, 5, 7 |
| AC-008 independent 5+5 budgets | 3, 4, 5, 7 |
| AC-009 Web failure/stale/conflict degradation | 3, 4, 5, 7 |
| AC-010 privacy and untrusted Web content | 3, 5, 7 |
| AC-011 invalid time/source fail-closed audit | 1, 2, 4, 7 |
| AC-012 midnight/DST | 1, 3, 7 |
| AC-013 structural final validation without prose gate | 3, 4, 5, 7 |
| AC-014 full forward-regression gate | 0, 6, 7 |

## 12. Stop And Rollback Conditions

Stop implementation or review preparation when any of these occurs:

- the exact baseline/requirements branch identity no longer matches;
- a change would require a second persisted timezone source;
- an application semantic keyword/parser gate appears necessary;
- independent Web/context budgets cannot remain exact;
- migration 7 cannot upgrade exact migration 6 without rewriting existing rows;
- final source binding would accept model-authored raw URLs;
- a clock failure can still reach the model as authoritative time;
- full existing v0.4/v0.3.1 tests regress;
- real provider, deployment, Telegram, or production data access becomes necessary
  without explicit authorization.

Before merge, rollback means reverting the feature commits while preserving the
confirmed requirements/design/plan history. After a future production migration,
rollback is application rollback to the prior image using the pre-release SQLite
backup/runbook; migration 7 tables are additive and need not be destructively dropped.

## 13. F3 Gate Outcome

The implementation plan is complete, ordered, testable, and traceable to every accepted
requirement and acceptance criterion. It introduces no new unresolved product choice.

The authorized implementation completed every local slice and is ready for exact-head
independent review. External provider, deployment, container, Telegram, and production
database gates remain separately closed.
