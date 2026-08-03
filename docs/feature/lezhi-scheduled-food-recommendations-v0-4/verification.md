# 乐枝订阅式自动触发与工作日美食推荐 v0.4 — 验证记录

## 1. Immutable scope

- Requirements handoff: `4124fb5444650fe73393a619796eee924d138dee3106cc48366f9bd2e69ce012`
- Confirmed requirements commit: `9b4034ba57bb2c042acfd10b6d3c1843b7a65602`
- Confirmed requirements SHA-256: `8736d6e6cc6d9ee63056c05e0f76e46927d41a71acf6a906ba63050c9a4fe934`
- Baseline sticker-expression v0.3 squash commit: `c1e820ae167c1d65d3dd44371a1a40c018e0293d`
- F2 design commit: `4f0bf6a`
- F3 implementation-plan commit: `5a92b2c`
- Automation persistence commit: `f250a1d`
- Scheduler/control/runtime commit: `78ae054`
- Tavily read-tools commit: `c4be5ba`
- Scheduled Writer/budget commit: `8680fc2`
- At-most-once delivery/recovery commit: `34dc3e9`
- Exact verified implementation and operations commit: `b4809bce2595b87c439ff986f60e9650e2434023`

The exact merge base is `c1e820ae167c1d65d3dd44371a1a40c018e0293d`. The verified feature
surface contains 40 changed files, 6,938 insertions and 264 deletions. The original shared checkout
was not cleaned or rewritten; all work and proof used an isolated worktree.

## 2. Implemented contracts

- `weekday_food_recommendation` is an application-owned automation definition. Runtime capability,
  group enable and an active member subscription are three separate gates; all are inert by default.
- Only authenticated target-group administrators can enable, disable, pause, resume or configure the
  group schedule. Members can subscribe, update only their own bounded non-sensitive food preferences,
  unsubscribe and inspect status. Foreign-bot commands and other groups fail closed.
- Defaults are `Asia/Shanghai`, weekday lunch `11:30`, dinner `17:30`, with a 30-minute grace period.
  Occurrence identity is stable across restarts and derived from bot, group, local date and meal slot.
- Schedule, subscription, preference and action records are group-scoped. Aggregate Writer context
  contains subscriber count and bounded preference summaries, not a fabricated current member or
  message. Location is administrator-owned bounded configuration.
- A due occurrence is leased, written to a stable prepared payload/text, revalidated immediately
  before its external-effect claim and then sent at most once. Prepared work can resume byte-for-byte;
  a claimed send without acknowledgment becomes `uncertain` and is never automatically replayed.
- A group configuration/version change, last unsubscribe, pause, disable, wrong persona snapshot,
  weekend, late window or wrong group prevents the external effect. Only acknowledged `sent` results
  enter the recent-primary exclusion history.
- Scheduled Writer output is a strict application-owned `food_recommendation` object with one primary
  and two distinct alternatives. Validation rejects repeated recent primaries, duplicate choices,
  internal protocol text, unsupported current merchant claims and stale/foreign source IDs.
- `web_search` and `web_fetch` map only to fixed Tavily Search/Extract endpoints. They are read-only,
  never use Crawl/Map/Research, do not log in or execute page code, and admit only bounded untrusted
  results. Scheduled fetch can use only a safe normalized URL returned by search in the same turn.
- URL validation rejects credentials, non-HTTP(S), non-default ports, localhost, private/link-local/
  reserved targets, unsafe DNS resolution, cross-URL responses and redirects. Model text cannot widen
  scope or provide credentials.
- Context tools retain ordinary 3 / complex 5 accounting; Web has an independent 0–5 counter. Rejected,
  failed and timed-out attempts consume their requested counter. Both share a 16 KiB admitted-result
  ceiling, the scheduled 60-second deadline and a maximum of 11 model completions with a final slot.
- Tavily credentials are external runtime secrets. Invalid/missing credentials make Web unavailable;
  failures can produce a generic, non-current recommendation or silence without interrupting normal
  Telegram polling.

## 3. Deterministic verification

Exact commit `b4809bce2595b87c439ff986f60e9650e2434023` passed:

- `python3 -m compileall -q src tests`
- `PYTHONPATH=src:tests uv run python -m unittest discover -s tests -q` — **270 tests**
- `uvx ruff check .` — passed
- `uvx ruff format --check .` — **125 files already formatted**
- `uv run mypy src/group_llm_agent` — no issues in **49 source files**
- `sh -n deploy/manage.sh` — passed
- `git diff --check` — passed
- Compose rendering with a synthetic no-secret fixed-mode environment — passed; rendered
  `AUTOMATION_CAPABILITY=disabled` and `TAVILY_WEB_CAPABILITY=disabled`, read-only root,
  `no-new-privileges`, `/tmp` tmpfs and the named SQLite volume
- tracked-file private-key, Telegram-token, OpenAI-style and Tavily-style credential scan — no match

Controlled tests prove:

- weekday/weekend, both meal slots, timezone conversion, invalid/DST wall time, stable identity,
  grace-window, pause/disable/no-subscriber and concurrent lease behavior;
- administrator authorization, foreign-command rejection, closed config grammar, member self-service,
  destructive disable confirmation and redacted action audit;
- exact v4 database construction and additive migration 5 preserve an existing sent external effect
  and context-tool audit, add safe defaults and return `PRAGMA quick_check = ok`;
- no-capability and capability-with-no-enabled-group startup performs no model, Tavily or scheduled
  Telegram effect while normal fake Telegram polling starts and stops;
- exact Tavily payload, fixed endpoint, Bearer header, optional project ID, bounded parsing, 400/401/
  429/432/433/5xx, timeout, transport, invalid JSON, wrong shape, empty and oversized responses;
- URL credential/port/private address/DNS-rebind/mismatch/redirect rejection, current-turn result IDs,
  fetch-before-search and prior-turn URL rejection, and prompt injection remaining inert data;
- zero-tool generic recommendation, sourced current recommendation, source-conflict degradation,
  five context plus five independent Web attempts, sixth-attempt rejection before provider invocation,
  total-result/deadline/model limits and no counter borrowing;
- prepare/restart reuse, pre-claim revalidation, concurrent claim, sent/definite-failure/timeout/
  invalid-response/uncertain outcomes, cross-group rejection and restart-after-claim no-resend.

Test logs intentionally include scripted provider, Telegram, automation and transport failures; these
are asserted negative paths, and the final suite result is `OK`.

## 4. Package and candidate image proof

- Source distribution: `group_llm_agent-0.1.0.tar.gz`, SHA-256
  `7984a24e3f60e4532dc59c507daa7ee2d473d43dcc2c5f2a54416959deb337ed`
- Wheel: `group_llm_agent-0.1.0-py3-none-any.whl`, SHA-256
  `b25200dc030b5405983f7fdfd7aee44ac094b0a00684c105c6a972009332ed47`
- The wheel contains `automation.py`, `automation_control.py`, `automation_delivery.py`,
  `automation_runtime.py`, `food_recommendation.py`, `scheduled_food.py`, `tavily.py`,
  `web_tools.py` and `writer_prompt.py`; metadata retains Python `>=3.11` and Pillow `11.3.0`.
- An isolated wheel installation with its declared Pillow dependency reached the console entry point
  and returned the expected safe exit code 2 for missing `TELEGRAM_BOT_TOKEN`.
- Candidate image: `telegram-bot-food-v0-4-candidate:local`, image ID
  `sha256:4e9fde17c161f81b1593273cbdd726ee19f0d2882187a415ff4477b453467b12`.
- Image configuration uses user `app` and command `group-llm-agent`. SHA-256 for all nine new runtime
  modules is byte-identical between the exact commit worktree and `/app/src` in the image.
- A no-credential normal image run returned the expected safe configuration exit code 2; a separate
  no-network import probe loaded the new configuration/modules and observed both capabilities disabled.

Package archives embed build timestamps and are evidence for this build only; the Git commit and module
content digests are the immutable review identity.

## 5. Requirements and acceptance closure

| Area | Requirements / AC | Result |
| --- | --- | --- |
| Authorization, subscriptions and audit | REQ-001–012; AC-001–004, AC-019 | Pass — closed commands, admin/member boundaries, group scoping and audit are deterministic. |
| Scheduling and occurrence lifecycle | REQ-003–020, REQ-045–050; AC-005–008, AC-018, AC-020–021, AC-024 | Pass — controlled clocks, grace, restart/concurrency and fail-closed skip paths are covered. |
| Recommendation contract and persona | REQ-021–028, REQ-036–037, REQ-047; AC-009–010, AC-015, AC-022, AC-024 | Pass — typed scheduled context/output, stable render and source validation are covered. |
| Tavily and URL safety | REQ-029–035, REQ-038–044; AC-011–014, AC-016–017, AC-019, AC-022–024 | Pass with fake transport — provider protocol, safety, budgets, audit and degradation are covered without a real call. |
| At-most-once Telegram effect | REQ-016–024, REQ-047–049; AC-006–009, AC-018, AC-020, AC-024 | Pass with fake Telegram — prepare/claim/send/restart matrices prove no automatic duplicate. |

No unimplemented repository requirement remains. External provider compatibility and live group behavior
remain operational gates below rather than claims made by scripted tests.

## 6. Deliberately pending deployment gates

| Gate | State | Required next evidence |
| --- | --- | --- |
| Real Tavily Search/Extract probe | **NOT AUTHORIZED / NOT RUN** | Operator supplies protected key and explicitly authorizes bounded paid/external requests against the configured endpoint. |
| Automation runtime capability | **DISABLED** | After merge/review, set `AUTOMATION_CAPABILITY=available` in the protected Compose environment and restart under separate authorization. |
| Tavily Web capability | **DISABLED** | Enable only with the protected key after the real probe; otherwise keep generic recommendation degradation. |
| Group configuration | **NOT ENABLED** | Target-group administrator sends `/food_enable`, reviews status/config and may pause immediately. |
| Member subscription | **NONE CREATED** | At least one real member explicitly sends `/food_subscribe`; no operator-side synthetic subscription. |
| Real scheduled Telegram UAT | **NOT RUN** | Wait for an authorized near-term weekday occurrence; verify zero/one visible message and durable occurrence/effect audit without clock/database manipulation. |
| Running Compose service | **UNCHANGED** | Rebuild/restart only in the separate deployment/debug session after exact-head review/merge authorization. |

No real Tavily request, provider credit consumption, group enable, member subscription, Compose restart,
running-container replacement or Telegram message occurred during implementation and verification.
Rollback is to pause/disable the group, return both capabilities to `disabled`, remove the key without
printing it and restart the same Compose service while preserving SQLite. An `uncertain` occurrence must
never be edited or replayed manually.
