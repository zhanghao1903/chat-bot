# Technical Design: 乐枝当前时间与时效信息感知

- Status: Design Complete
- Feature branch: `codex/lezhi-temporal-awareness`
- Confirmed requirements commit: `12e200df19dc168f2c6d476359fceef9b0251bd6`
- Forward baseline: `origin/main@71c7eb3b60b08f3dd0d2229dee9873a8a76cca93`
- Requirements SHA-256: `74c063809f66513d9f3be72eecde2c5f4c586fd448ef08a20ba9c5a05d67c89e`
- Requirements handoff: `ef5321a8655cc8cc2d0232e673eb8ee78d755893e8fe07ae30da56e23a990964`
- Design date: 2026-08-11

## 1. Purpose And Responsibility Boundary

This feature gives every Writer model call an application-owned, freshly sampled,
timezone-aware view of “now”. It also makes message occurrence time and Web-source
freshness explicit so the Writer can distinguish the current instant, a message's
historical reference point, source retrieval time, publication time, and event time.

The responsibility split is deliberate:

- the application owns the clock, IANA timezone validation, per-call freshness,
  structured protocols, budgets, URL/source identity, audit, and fail-closed behavior;
- the Writer owns the semantic decisions: which timezone/location the member means,
  whether the question depends on changing external state, whether evidence is
  sufficient, and how to explain ambiguity or uncertainty;
- Tavily remains an untrusted, read-only source of external evidence and is never a
  clock source;
- Telegram message timestamps remain occurrence metadata and are never substituted for
  the current system time.

No application keyword list, regular expression, synonym enumeration, or handcrafted
natural-language parser decides whether Web verification is needed. This feature does
not change trigger eligibility, reply form, member memory, automation subscription,
expression selection, external-effect idempotency, or production capability flags.

The confirmed handoff authorizes F2 and F3 only. Real provider/Tavily calls,
deployment, container replacement, Telegram operations, and production SQLite changes
remain outside this design-stage authorization.

## 2. Current-State Gaps

The forward baseline already provides the hard parts that must be preserved:

- `AutomationRepository` owns the existing group IANA timezone and defaults to
  `Asia/Shanghai` when a group has no configuration;
- `WriterEffector` owns a bounded model/tool loop with independent context-tool and
  Web-tool counters;
- `WebToolSession` owns current-turn Tavily result IDs, public-URL validation, result
  size bounds, and Web audit rows;
- `ScheduledOccurrenceSource` preserves planned local date, slot, timezone, and UTC
  instant;
- group messages persist timezone-aware occurrence timestamps.

Four gaps cause the reported behavior:

1. `EffectContext` is assembled once and contains no authoritative time snapshot.
2. `build_writer_model_messages` emits no occurrence timestamp for the current inbound
   message and drops timestamps from the recent scene.
3. a long Writer/tool loop has no rule to resample time before the next model call.
4. an ordinary current-fact reply is not structurally bound to current-turn Web result
   IDs, retrieval time, or a declared freshness outcome.

## 3. Component Ownership

| Component | Ownership after this feature |
| --- | --- |
| `temporal.py` | Typed clock contract, IANA validation, immutable temporal snapshots, deterministic conversion, context IDs, and per-effect temporal session. |
| `context.py` | Bounded conversation/memory data plus the effective group-timezone lookup input; it does not cache current time. |
| `writer_prompt.py` | Samples no clock itself. It renders one trusted temporal snapshot supplied immediately before the model call and converts message timestamps into that snapshot's target timezone. |
| `writer_contract.py` | Closed Writer protocol for temporal-context binding and declared answer freshness/source IDs. |
| `model.py` | Parses exact temporal/freshness fields and the budget-free `select_answer_timezone` call. It does not interpret prose. |
| `effector.py` | Creates one temporal session per effect, samples immediately before every Writer call, executes target-timezone selection, validates freshness/source binding, and records terminal temporal audit. |
| `automation.py` | Remains the single persisted source for group timezone. A narrow read adapter exposes the configured timezone or the existing Shanghai default. |
| `tavily.py` | Preserves bounded provider publication/update metadata when present and assigns an application retrieval timestamp from the injected/system clock. |
| `web_tools.py` | Keeps source identity, URL, retrieval/publication/update metadata, budget, and audit; exposes only current-turn result IDs to final validation. |
| `temporal_audit.py` | Owns bounded temporal sample and answer-audit persistence, keeping `RunRepository` from accumulating another state machine. |
| `database.py` | Additive migration 7 for temporal audit only; migrations 1–6 and all existing data remain unchanged. |

## 4. Authoritative Temporal Context

### 4.1 Clock port

Production uses a timezone-aware system clock through a narrow callable/protocol:

```python
class Clock(Protocol):
    def now(self) -> datetime: ...
```

The default implementation returns `datetime.now(UTC)`. Tests inject a controlled
clock. A clock result is invalid when it is naive, cannot convert to UTC, lies outside
the supported `datetime` range, or fails UTC/local round-trip consistency. The runtime
does not query Web, Telegram, SQLite's `now`, or the model to repair an invalid clock.

### 4.2 Snapshot schema

`TemporalContext` is immutable and contains only application-owned fields:

```text
version                  lezhi-temporal-v1
context_id               deterministic SHA-256-derived opaque ID
captured_at_utc           timezone-aware RFC3339 UTC instant
current_utc               same authoritative instant in UTC
current_local             same instant in answer_timezone
answer_timezone           validated IANA ZoneInfo key
utc_offset                ±HH:MM at that instant
local_date                YYYY-MM-DD
local_weekday             ISO 1–7 plus stable English name
source_class              system_clock
group_timezone            effective persisted/default group IANA timezone
timezone_selection        group_default | writer_explicit_override
```

`context_id` hashes the canonical version, UTC instant, target zone, offset, and
selection class. It is not a secret and cannot be supplied by a member or Web page.
All timestamps include timezone information; no field is inferred from another model
output.

The factory validates that:

- `answer_timezone` is an installed IANA `ZoneInfo` key, not a numeric fixed offset;
- `current_local.astimezone(UTC)` equals `current_utc`;
- the rendered offset equals `current_local.utcoffset()`;
- the local date/weekday equal the converted local instant; and
- `captured_at_utc` and `current_utc` describe the same sample.

Any violation raises a typed `TemporalContextError` and is recorded as a bounded
degradation. The invalid snapshot is never labelled authoritative or sent to a model.

### 4.3 Effective group timezone

The existing `automation_group_configs` row is the only persisted group-timezone
source. A `GroupTimezoneProvider` adapter reads its validated IANA key. When no row
exists, it returns `Asia/Shanghai`, matching v0.4. Capability disabled/paused state
does not create a second timezone: a configured row remains the group's timezone
reference, while absence uses the default.

An invalid persisted timezone is an integrity failure, not a reason to silently fall
back to Shanghai. It fails closed and records `invalid_group_timezone`.

## 5. Per-Model-Call Freshness And Target Timezone

### 5.1 Temporal session

`WriterEffector.execute` creates one `TemporalSession` after the effect run is claimed.
The session stores the immutable group timezone and an optional current-turn answer
timezone override; it never stores a time snapshot for reuse.

Immediately before every `StructuredModelPort.complete` call, the effector performs:

1. read `Clock.now()` exactly once;
2. build and validate a new snapshot for the active answer timezone;
3. record the bounded model-call sample by effect-run ID and ordinal;
4. build the Writer messages using that exact snapshot; and
5. call the model without another intervening tool/network operation.

The next call after a context tool, Web tool, protocol repair, midnight, or process
restart repeats all five steps. The final decision must echo the exact
`temporal_context_id` of its own model call. A stale, unknown, prior-call, or
cross-effect ID is a structural protocol error and follows the existing bounded repair
then silence/failure path.

### 5.2 Budget-free answer-timezone selection

Every call initially receives a fresh snapshot in the effective group timezone. The
Writer may select a different explicit target through one application-owned read-only
capability:

```json
{
  "kind": "call_tool",
  "reason_code": "explicit_new_york_time",
  "tool_name": "select_answer_timezone",
  "tool_arguments": {"timezone": "America/New_York"},
  "tool_purpose_code": "answer_timezone"
}
```

The model performs the semantic mapping from an unambiguous member phrase such as
“东京” to `Asia/Tokyo`. The application only validates the exact IANA key. Ambiguous
or unknown places are answered with a clarification; no city synonym table or location
parser is added.

The capability:

- changes only the in-memory current effect session;
- never edits group configuration or member memory;
- does not consume context-tool or Web-tool budget;
- is allowed at most once per effect and never after the final model-call slot;
- consumes one bounded model round, so `maximum_model_calls` becomes 12: at most one
  timezone-selection round, five context-tool rounds, five Web-tool rounds, and one
  final round;
- returns no Web or member data; the next model call receives a newly sampled trusted
  snapshot in the selected zone.

Repeated, invalid, fixed-offset, or unsupported selections are protocol errors. They
do not fall back to a guessed zone. The original group snapshot remains available for
the bounded repair/clarification round.

## 6. Message And Scheduled Time Semantics

### 6.1 Inbound and recent messages

For each model call, `writer_prompt.py` renders the current inbound source and each
bounded recent-scene item with:

```text
occurred_at_utc
occurred_at_target_local
occurred_timezone = answer timezone used for the conversion
telegram_precision = second
```

The stored occurrence instant remains authoritative. Conversion uses the active
snapshot's IANA zone and never mutates persistence. Scene ordering remains repository
ordering, but the Writer is told not to infer a date from order when timestamp metadata
is invalid or absent.

The current message includes its occurrence time in addition to sender/text/reply
metadata. This feature does not extend retention or expose one group's timestamps to
another group.

### 6.2 Scheduled occurrence

Scheduled Writer calls use the identical per-call temporal session. Their source block
keeps two explicitly named timelines:

- `planned`: existing local date, meal slot, configured IANA timezone, planned local
  wall time, and `scheduled_for` UTC instant;
- `execution_now`: the newly sampled temporal context for the current model call.

The prompt states that delay/retry must not rewrite the planned occurrence as if it
were an inbound message or a newly scheduled slot. The stable occurrence identity,
lease, claim, and delivery state machines remain unchanged.

## 7. Writer Protocol For Freshness And Sources

### 7.1 Structured declaration

Every Writer decision echoes `temporal_context_id`. Text-bearing ordinary decisions
(`reply` and `reply_with_sticker`) additionally contain exactly one closed
`freshness` object:

```json
{
  "mode": "stable|clock|current_verified|current_unverified",
  "source_result_ids": ["web:1", "web:2"]
}
```

The semantic meaning is:

- `stable`: no current external-state claim; source list must be empty;
- `clock`: answer derives only from the authoritative time context; source list must
  be empty and Web is unnecessary;
- `current_verified`: current external-state claims are supported by one to three
  current-turn Web result IDs;
- `current_unverified`: the current state could not be reliably verified; zero to
  three attempted current-turn source IDs may be retained for traceability.

Sticker-only and silence decisions still echo `temporal_context_id` but have no text
freshness object. Scheduled `food_recommendation` keeps its current closed food
contract and echoes the temporal context ID; its existing citation validation remains
in force.

The Writer, not an application prose classifier, chooses `mode`. The prompt requires
Web for materially changing current facts when available, zero Web for pure clock and
stable questions, an explicit uncertainty statement for `current_unverified`, and no
fabricated publication/event timestamps.

### 7.2 Deterministic final validation

The application validates facts that do not require interpreting natural language:

1. the echoed context ID equals the snapshot injected into that model call;
2. the freshness enum and exact field set are valid;
3. `stable`/`clock` have no source IDs;
4. `current_verified` has one to three distinct current-turn IDs;
5. every source ID belongs to a successful Web result from the same effect session,
   resolves to a validated public URL, and carries retrieval time;
6. `current_unverified` cannot be presented with an application-owned “verified”
   footer; and
7. all existing text leakage, deadline, persona snapshot, catalog, budget, delivery,
   and single-effect checks still pass.

The application does not scan final prose for “today”, news, weather, price, or any
other semantic category. Deterministic tests for an “unverified current assertion” use
the structured `current_verified` mode with absent/invalid source IDs; that result
fails closed without introducing a keyword gate.

### 7.3 User-visible provenance

For `current_verified`, the application appends a compact, application-owned footer to
the validated Writer text:

```text
截至 2026-08-11 15:42（Asia/Shanghai）
来源：https://example.com/a · https://example.org/b
```

The as-of instant is the latest retrieval time among the selected evidence, converted
with the final answer timezone. URLs come only from current-turn validated result IDs.
Telegram automatically makes the raw HTTPS URLs clickable; no provider title or HTML
is copied into the footer.

For `current_unverified`, the application adds a short fixed boundary before any
model-authored stable background: “当前状态尚未可靠核实。” It never adds a verified
footer. `stable` and `clock` receive no source footer.

This rendering guarantees the 1–3 URL and retrieval-time boundary while leaving the
semantic explanation and persona voice to the Writer.

## 8. Web Evidence Provenance

### 8.1 Provider model

`TavilySearchResult` and `TavilyExtractResult` gain optional bounded source-time
metadata:

```text
published_at     strict timezone-aware RFC3339 when provider data can be normalized
updated_at       strict timezone-aware RFC3339 when provider data can be normalized
provider_time_text  bounded untrusted text when a provider time exists but is not an
                    unambiguous absolute instant
```

Missing provider dates stay null. The application never turns “2 hours ago” into an
absolute event time. Retrieval time comes from the application clock immediately after
the provider response and is always distinguished from publication/update metadata.

Search and fetch prompt payloads include `retrieved_at`, `published_at`, `updated_at`,
and `provider_time_text` as separate fields. Web content and provider time text remain
inside the untrusted external-content envelope.

### 8.2 Session evidence registry

`WebToolSession` keeps a bounded `WebEvidence` record for each current-turn result ID:

```text
result_id, normalized_url, retrieved_at, published_at, updated_at,
provider_time_text, search_audit_id, optional_fetch_audit_id
```

The registry is in memory, scoped to one effect, and capped by the existing five-call,
five-result-per-search, and character limits. Final source selection cannot name a URL
that did not pass the session's SSRF/public-routing validation.

The independent budgets remain unchanged:

- context tools: ordinary three, justified complex maximum five;
- Web Search + Fetch: shared hard maximum five, including failed/rejected attempts;
- answer-timezone selection: zero tool-budget cost, maximum one session transition;
- no sixth context or Web call reaches a provider.

## 9. Persistence And Audit: Migration 7

Migration 7 is additive and transactional. It creates no new member preference and
does not rewrite messages, effects, automation rows, memories, assets, or migrations
1–6.

### 9.1 `temporal_context_samples`

One bounded row is recorded per Writer model call:

```text
id, effect_run_id, model_call_ordinal, context_version, context_id,
captured_at_utc, answer_timezone, utc_offset, timezone_selection,
source_class, status, error_code, created_at
UNIQUE(effect_run_id, model_call_ordinal)
```

`model_call_ordinal` is capped by the application maximum. The table stores no prompt,
message text, model output, key, token, URL, or member memory.

### 9.2 `temporal_answer_audit`

One row summarizes the terminal effect:

```text
effect_run_id PRIMARY KEY, chat_id, trigger_event_id, source_kind,
final_context_id, final_captured_at_utc, answer_timezone, utc_offset,
freshness_mode, web_requested, web_audit_ids_json,
latest_web_retrieved_at, status, degradation_reason, created_at, updated_at
```

`web_audit_ids_json` is a sorted bounded integer array containing only tool audit IDs
owned by the same effect. `freshness_mode` is nullable for sticker/silence or failures
before a valid final decision. `status` is `completed|degraded|failed|silence`.

The audit repository writes the failed row even when clock sampling fails before a
model call. Terminal recording occurs before `complete_effect_run`; a database failure
prevents the final text from being marked complete and follows the existing safe
degradation path.

## 10. Failure And Degradation Matrix

| Failure | Deterministic outcome |
| --- | --- |
| Naive/inconsistent clock | No model call with a claimed valid time; direct path uses bounded failure reply, contextual/scheduled path silences or fails; audit `invalid_clock`. |
| Missing/invalid group timezone | No silent Shanghai repair; audit `invalid_group_timezone`; safe degradation. |
| Invalid target timezone selection | Selection rejected, one bounded repair/clarification opportunity, no persistent change. |
| Stale/unknown temporal context ID | Protocol error; bounded repair, then silence/failure by existing trigger path. |
| Web disabled/missing credentials | Web tools absent from available set; prompt requires `current_unverified` rather than model-memory current claims. Clock-only answers remain available. |
| Web timeout/limit/empty/conflict | Attempt counts against Web budget; result metadata is exposed; Writer may continue within budget or return `current_unverified`. |
| Sixth Web request | Rejected before Tavily; audited; no counter sharing with context tools. |
| `current_verified` without 1–3 valid result IDs | Final result rejected as `freshness_sources_invalid`. |
| Selected source missing retrieval time/unsafe URL | Source cannot enter evidence registry; final validation rejects it. |
| Audit write fails | Final result is not completed or sent; existing idempotent effect-run recovery applies. |
| Deadline expires | Existing final deadline validator wins; no late reply or citation footer is sent. |

No failure response exposes a provider body, prompt, configured base URL, API key,
internal identifier, or SQLite exception text.

## 11. Security, Privacy, And Trust Boundaries

- Temporal context is a trusted system block separated from untrusted group and Web
  blocks. Untrusted content cannot declare or overwrite its fields.
- `select_answer_timezone` accepts only an exact installed IANA key and has no write
  side effect.
- Web queries retain current length/control/URL restrictions. Prompt policy requires
  the smallest public query and forbids internal IDs, member memory, secrets, and
  unrelated group text.
- Web result text, titles, source time text, and page instructions remain untrusted and
  cannot change persona, tool budgets, permissions, persistence, or delivery.
- Source footers use application-held normalized URLs rather than model-authored URLs
  or provider titles.
- Time/audit tables contain bounded operational metadata only and preserve group/effect
  scoping.

## 12. Verification Strategy

### 12.1 Unit and contract tests

- frozen clock snapshots for Shanghai, Tokyo, New York standard/DST instants, UTC
  offsets, weekday/date, and RFC3339 output;
- naive clock, invalid IANA key, fixed offset, inconsistent snapshot, and UTC/local
  round-trip failures;
- fresh context IDs across calls, ten-minute jumps, midnight, tool rounds, and a new
  process/session;
- timezone selection accepts exact IANA, changes only current turn, is budget-free and
  bounded to one transition;
- current/recent message UTC and target-local occurrence timestamps;
- scheduled planned/execution timelines remain distinct;
- Writer schema/parser/prompt agreement for context ID and freshness modes;
- stable/clock zero-source success, verified 1–3 source success, invalid/foreign/stale
  source rejection, and unverified deterministic boundary rendering;
- provider retrieval/publication/update metadata remains distinct and absent values are
  never fabricated;
- temporal audit row bounds, ownership, failure rows, and migration 6→7 compatibility.

### 12.2 End-to-end controlled scenarios

- `2026-08-11T12:34:20+08:00` current-time question yields minute-correct Shanghai
  context with zero Web calls;
- New York target uses IANA DST while an ambiguous place yields clarification;
- a quoted yesterday “今晚” scene exposes both historical and current absolute dates;
- a delayed scheduled occurrence retains its original slot/local date and fresh
  execution time;
- stable knowledge uses zero Web calls; current weather uses Web when available;
- five context plus five Web attempts remain independent, and the sixth Web call never
  reaches the fake provider;
- source success produces an application footer; stale/conflicting/empty/timeout/no-Web
  cases produce uncertainty without a verified footer;
- prompt-injection Web content cannot change timezone, source IDs, budgets, or effects;
- existing reply/reply-with-sticker/sticker/silence, automation, database, and delivery
  regression suites remain green.

All release evidence uses fake/injected clocks and fake transports unless a later phase
receives explicit provider/deployment authorization.

## 13. Traceability

| Design element | Requirements / acceptance criteria |
| --- | --- |
| Per-call temporal session and echoed context ID | REQ-001, REQ-002, REQ-006, REQ-014, REQ-022; AC-001, AC-002, AC-011, AC-012 |
| Group timezone provider and budget-free explicit override | REQ-003, REQ-004, REQ-005, REQ-014; AC-003 |
| Message occurrence metadata | REQ-007, REQ-008; AC-004 |
| Planned versus execution scheduled timelines | REQ-009; AC-005 |
| Writer-owned semantic Web decision | REQ-010 through REQ-012; AC-006, AC-013 |
| Independent counters and bounded model loop | REQ-013, REQ-014, REQ-018; AC-008, AC-009 |
| Structured freshness and evidence registry | REQ-015 through REQ-018, REQ-023; AC-007, AC-009, AC-013 |
| Query/result trust boundaries | REQ-019, REQ-020, REQ-023; AC-010, AC-013 |
| Temporal sample and terminal audit | REQ-021, REQ-022; AC-002, AC-011 |
| Controlled clock/provider verification matrix | REQ-024, REQ-025; AC-012, AC-014 |

## 14. F2 Gate Outcome

The design is complete and introduces no unresolved product decision. It selects the
injection-plus-budget-free-timezone-capability option allowed by DEC-003, preserves all
accepted assumptions and decisions, and is ready for an implementation plan.

Implementation remains gated on F3 completion. Provider, deployment, container,
Telegram, and production data operations remain unauthorized.
