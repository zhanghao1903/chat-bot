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

### 1.1 Review remediation boundary

- First review dispatch: `d6755591928089c35bae1b2ea9bfa8ee11e02c9450b4df7767b8712a89db17b3`
- Accepted immutable ReviewResult SHA-256:
  `585708e88c0f2aa904247a16d0308c9e3d654429630148992321742b3117b3b6`
- First reviewed head: `4de7259e22a2dfb4ce7eafa5876961b2b5f3a74e`
- Exact remediation implementation commit: `2be0122454414c47173f8499222f50c01b150922`

The accepted ReviewResult requested four changes. The first remediation addressed them as follows;
the next exact-head review confirmed FINDING-003/004 closed and found induced gaps in
FINDING-001/002, recorded in section 1.2:

- **FINDING-001** — the model no longer authors displayed dish/merchant labels, descriptions,
  current facts, caution notes or safety prose. Generic choices resolve only through a closed
  application dish/reason registry. A sourced choice must bind each of three merchant choices to a
  distinct current-turn Web result, and the application derives the stable key, URL list and
  cautious wording. Extra free-form merchant, allergy, medical and paraphrased
  reassurance fields fail schema parsing independent of their vocabulary.
- **FINDING-002** — deterministic date/slot identity is retained, but a still-unleased `due` row is
  atomically refreshed to the active scheduled instant, grace deadline, config version and persona
  snapshot. Leased, prepared, claimed and terminal rows remain immutable. Restart and schedule-edit
  tests prove the changed slot runs once instead of failing on a stale row.
- **FINDING-003** — startup recovery joins each `sending` occurrence to its durable external effect.
  A durable `sent` acknowledgement reconciles to occurrence `sent` and enters recent-primary
  history; durable failure reconciles to definite failure; only ambiguous/missing/sending state
  becomes `uncertain`, with no resend.
- **FINDING-004** — subscribe and status acknowledgements now report the current group, IANA
  timezone, lunch/dinner wall times, next occurrence converted to group-local time, one group-level
  message per meal slot and `/food_unsubscribe`, all in one response. Exact tests cover
  `Asia/Shanghai` and `America/New_York` without exposing member identities.

Exact remediation commit `2be0122454414c47173f8499222f50c01b150922` passed:

- `python3 -m compileall -q src tests`
- `PYTHONPATH=src:tests .venv/bin/python -m unittest discover -s tests -q` — **275 tests**
- Ruff check — passed; Ruff format check — **96 source/test files already formatted**
- Mypy — no issues in **49 source files**
- `sh -n deploy/manage.sh`, `git diff --check` and package build — passed
- Remediation sdist SHA-256:
  `375f83d10794e57ea5bbdd76fdc729b3bb7e1003d4d1982a940c09422e0b0682`
- Remediation wheel SHA-256:
  `f2baa3452aef0da77742d658fe2a4a5c359420daa4d50790965d2b6a0bfe6849`
- Remediation candidate image:
  `sha256:94b9e7cc7ff54a20308653f575bc2e047baaac7873a8161224786818cee69fc7`,
  user `app`, command `group-llm-agent`; a no-credential run returned the expected safe exit code 2

No real Tavily call, Compose service replacement, automation enablement, subscription or Telegram
message was performed while closing these findings.

### 1.2 Induced-risk review and second remediation

- Second review dispatch: `d678fedd948334101d651ed7392a50f331623a432d6b00efe67f1df2a603b538`
- Accepted immutable ReviewResult SHA-256:
  `d07dcb98ef1c3528473df775e2b0e6374c6a6ab70666b4319064c5cca1b3c523`
- Second reviewed head: `5bf0af6c29ed638e33368ba3317fede3cc1466b8`
- Exact second-remediation implementation commit:
  `8f7743804e6116c2214057b3f695650ff6fef483`

The second review retained the original finding IDs. FINDING-003/004 remained fixed. The second
remediation changed the two open paths as follows; the subsequent exact-head review confirmed
FINDING-001 closed but found a later lease boundary still open under FINDING-002, recorded in
section 1.3:

- **FINDING-001** — `FoodCitation` now contains only the normalized current-turn URL. Provider
  titles remain visible to the Writer as explicitly untrusted tool data but cannot cross the final
  application boundary. Sourced output uses only application-owned neutral labels
  `来源商家候选一/二/三`, closed reason text and cautious wording. Exact tests inject
  `海底捞对坚果敏感者也完全适合` plus medical/body-condition paraphrases through normal Tavily search
  results and prove none appears in the final safe reply.
- **FINDING-002** — `create_occurrence` now starts `BEGIN IMMEDIATE`, reads the active group config
  version and returns no occurrence when the caller's snapshot is stale. The version comparison,
  insert and due-row refresh therefore form one serialized transaction. A deterministic
  v1 11:30 → v2 11:40 → stale-v1 interleaving proves the stale worker cannot revert, return or lease
  the refreshed row; the v2 scheduler processes the 11:40 occurrence exactly once.

Exact second-remediation commit `8f7743804e6116c2214057b3f695650ff6fef483` passed:

- `python3 -m compileall -q src tests`
- `PYTHONPATH=src:tests .venv/bin/python -m unittest discover -s tests -q` — **277 tests**
- Ruff check — passed; Ruff format check — **96 source/test files already formatted**
- Mypy — no issues in **49 source files**
- `sh -n deploy/manage.sh`, `git diff --check` and package build — passed
- Second-remediation sdist SHA-256:
  `065ab54da35fc05873a0eed7ad32dbf732164d71a2aad42addb19da07794f357`
- Second-remediation wheel SHA-256:
  `7c135805e267752154b1e86292f5dfc1a6566baa67f00acbfefb9d2aad33bbfa`
- Second-remediation candidate image:
  `sha256:b70df84e189012ecf95f78ef97ac38693acc6b632fb7ae2b0f1129b6b411799c`,
  user `app`, command `group-llm-agent`; a no-credential run returned the expected safe exit code 2

The operational boundaries remain unchanged: no real Tavily request, capability enablement,
subscription, Compose service replacement or Telegram message was performed.

### 1.3 Pre-lease configuration race and third remediation

- Third review dispatch: `b1c0d4c61b93de89ef3f0c0407bae92d56018278b43c979f539ff3b7d55eb8de`
- Accepted immutable ReviewResult SHA-256:
  `0060789c90d1be3a032c1e7e36f97cc80bf0dee5fdf10db48834d3322b6aee64`
- Third reviewed head: `631e73691fab44d622616fd8e5ee154251506bdb`
- Exact third-remediation implementation commit:
  `85696ba1ffe6dd09075fa0e431b2106851541a22`

The third review confirmed FINDING-001, FINDING-003 and FINDING-004 fixed and retained only
FINDING-002. The remaining refresh-commit/admin-update/pre-lease interleaving is closed as follows:

- **FINDING-002** — `lease` now requires the worker's expected config version. Its single
  `BEGIN IMMEDIATE` update verifies the occurrence version and an enabled active group-config row
  with that same version before changing `due`/expired-`leased` to `leased`. If an administrator
  commits config v2 after the v1 refresh but before this update, the v1 worker changes zero rows and
  does not terminalize the occurrence. A deterministic scheduler regression proves v1 at 11:30
  loses the lease, the row remains `due`, the v2 worker refreshes it to 11:40 and executes exactly
  once, and a duplicate worker processes zero work.

Exact third-remediation commit `85696ba1ffe6dd09075fa0e431b2106851541a22` passed:

- `python3 -m compileall -q src tests`
- `PYTHONPATH=src:tests uv run python -m unittest discover -s tests -q` — **278 tests** in
  **96.615 seconds**
- Ruff check — passed; Ruff format check — **96 source/test files already formatted**
- Mypy — no issues in **49 source files**
- `sh -n deploy/manage.sh`, `git diff --check` and package build — passed
- Third-remediation sdist SHA-256:
  `2ae966e44e13d43469ac00cacb177d20a435b06f07847cd926bd14976ae80e76`
- Third-remediation wheel SHA-256:
  `a0aadc11d7fcc59c1ad5674bbb730774de137e1db49676e6b065a43245659ba3`

The local candidate-image build was not executed because its permission review channel rejected the
command after an approval-service connection interruption. No workaround was attempted, no running
container was changed, and this remediation does not claim new image evidence. No real Tavily call,
capability enablement, subscription, Compose service replacement or Telegram message was performed.

### 1.4 Expired pre-prepare lease recovery and fourth remediation

- Fourth review dispatch: `8d5dbbcc54b6257b7df1fb8e4f374e83c1772f5b6b1bf733c4cdcae0663f2fe6`
- Accepted immutable ReviewResult SHA-256:
  `3a5628dd77500468b6daf5389acee9e5f04183e1609f1ca3e528c727a62dcd2e`
- Fourth reviewed head: `0dc99138b3fe422fe23fd161ea5954bdf5ce582c`
- Exact fourth-remediation implementation commit:
  `3fcb0ef0d615aa09b91f27d85551bd4abb7ef46b`

The fourth review confirmed FINDING-001 through FINDING-004 fixed and identified one induced
pre-prepare recovery gap. It is closed as follows:

- **FINDING-005** — first acquisition and expired recovery are now distinct arms of one transactional
  lease update. A `due` row still requires both its expected version and an enabled active config at
  that exact version. An expired `leased` row, whose send right was already acquired, is recovered
  against its immutable occurrence version without requiring the later active config to match. The
  scheduler passes the occurrence version; its existing pre-claim policy then makes a post-lease v2
  edit terminalize the recovered v1 occurrence once as `definite_failure`. The exact
  lease-v1/admin-config-v2/crash-before-prepare/restart regression proves the first recovery processes
  one row, a duplicate processes zero, the recommendation processor is never called, zero external
  effects exist and the row is not stranded in `leased`.

Exact fourth-remediation commit `3fcb0ef0d615aa09b91f27d85551bd4abb7ef46b` passed:

- `python3 -m compileall -q src tests`
- `PYTHONPATH=src:tests uv run python -m unittest discover -s tests -q` — **279 tests** in
  **94.614 seconds**
- Ruff check — passed; Ruff format check — **96 source/test files already formatted**
- Mypy — no issues in **49 source files**
- `sh -n deploy/manage.sh`, `git diff --check` and package build — passed
- Fourth-remediation sdist SHA-256:
  `beedebf0c14cf3d062e9639d308766d57df96285d44bc8ac26ba412f9ebcc1fd`
- Fourth-remediation wheel SHA-256:
  `b2a4cf66e29f03bb841e2795f834d11519af055cd4152ad40bec7d1eea5a3461`

The Docker, provider and deployment boundaries from section 1.3 remain unchanged: no candidate image
was rebuilt, no real Tavily call was made, capabilities stayed disabled, and no running service or
Telegram state changed.

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
