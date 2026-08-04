# Implementation Plan: 乐枝订阅式自动触发与工作日美食推荐 v0.4

- Phase: F3 Implementation Plan
- Status: Complete
- Requirements handoff: `4124fb5444650fe73393a619796eee924d138dee3106cc48366f9bd2e69ce012`
- Design commit: `4f0bf6a`
- Branch: `codex/lezhi-scheduled-food-recommendations-v0-4`

## 1. Delivery Contract

本计划实施已确认的 REQ-001–050 和 AC-001–024。交付完成意味着：

- 群管理员能够启用、配置、暂停、恢复或关闭唯一允许类型
  `weekday_food_recommendation`；
- 成员只能为自己订阅、维护有限非敏感偏好和退订；
- 工作日午餐/晚餐各形成一个稳定、可恢复、最多一次群级效应；
- scheduled 场景具有真实类型，不伪造成员消息；
- Writer 可调用 Tavily Search/Extract 对应的 `web_search`/`web_fetch`；
- 上下文工具 3/5 与 Web 工具 5 次分别计数，并共享截止时间、11 次模型调用、成本与安全边界；
- 推荐稳定输出一份主推和两个备选，近期事实有来源，失败时通用降级或安全跳过；
- 重启、并发、过期和 Telegram uncertain 都不会重复发送；
- 自动化与 Tavily 默认关闭，普通 Telegram 聊天在任何故障下继续。

代码、本地假服务验证、包构建和候选镜像可以连续推进。真实 Tavily 凭据使用、Compose 重启、
群级启用、成员订阅及真实定时 Telegram 消息必须停在后续部署授权门限。

## 2. Planned Package Boundaries

| File/package | Planned responsibility |
| --- | --- |
| `events.py` / `context.py` | inbound/scheduled 排他来源、scheduled scene 和 final contract |
| `database.py` | additive migration 5 and indexes |
| `automation.py` | 类型注册、配置/订阅/occurrence repository、schedule、lease 与 worker |
| `automation_control.py` | 受限命令、bot target、admin/self authorization 和操作审计 |
| `tavily.py` | fixed provider transport, strict response and redacted errors |
| `tools.py` | composite registry, context/Web 独立预算、URL/来源授权和 audit |
| `model.py` / `effector.py` | food schema、11-call loop、scheduled prompt、validation/rendering |
| `runs.py` | 仅补充共用 effect/tool/external-effect audit；不承载 automation repository |
| `runtime.py` / `app.py` / `config.py` | worker lifecycle、delivery、feature gates 和 composition |
| deploy/docs/package metadata | disabled-by-default config, runbook, verification and release carrier |

新增生产模块目标不超过 500 行。`runs.py` 已超过 800 行，Slice 0 必须先执行
`maintainability-gate`；除共用 schema-compatible 小改动外，新持久化逻辑进入 `automation.py`，
必要时再抽取专用 repository 文件。

## 3. Slice 0 — Maintainability Gate and Baseline Proof

### Inputs

- `src/group_llm_agent/runs.py`
- `src/group_llm_agent/effector.py`
- `src/group_llm_agent/runtime.py`
- related tests and dependency graph

### Actions

- 运行项目 `maintainability-gate` 并记录文件规模、职责、修改面与拆分决定；
- 建立 exact baseline 的 compileall、full unittest、Ruff、Mypy 结果；
- 确认当前 migration 为 4、外部效果唯一键和普通聊天预算语义；
- 固定本特性后续每个切片只提交有意文件，保留共享工作区的无关改动。

### Exit checks

- gate 结论允许 narrow shared-contract edits；
- 自动化 repository 不加入 `runs.py`；
- baseline failure 必须先区分既有问题与本特性回归。

本切片不修改生产行为，可与 Slice 1 合并到首个实现提交。

## 4. Slice 1 — Typed Source, Migration and Automation Repository

### Files

- `src/group_llm_agent/events.py`
- `src/group_llm_agent/context.py`
- `src/group_llm_agent/database.py`
- `src/group_llm_agent/automation.py`
- `src/group_llm_agent/runs.py`
- `tests/test_database.py`
- `tests/test_automation.py`
- `tests/test_context.py`
- existing run/restart tests

### Changes

- introduce exclusive `InboundMessageSource | ScheduledOccurrenceSource` while preserving old
  inbound constructors/properties;
- add scheduled trigger path/category and nullable trigger message identity;
- migration 5 creates group config, subscription/preferences, occurrence and action-audit tables;
- extend effect/tool audit with source and budget metadata using safe defaults for existing rows;
- implement exact allowlisted registry and versioned stable occurrence key;
- implement group-isolated repository operations, atomic idempotent subscription and deletion;
- implement occurrence insertion, bounded lease, prepared payload/text, claim linkage and terminal outcomes;
- ensure plaintext prompt, Web body, secret and subscriber list are never stored.

### Checks

- v4 fixture upgrades once and reopens; existing messages/runs/effects remain readable;
- exactly one source arm; scheduled has no fake sender/message text;
- duplicate subscription and occurrence converge to one row;
- other chat cannot read config, preferences, history or occurrence;
- lease expiry only recovers pre-claim work; post-claim replay cannot resend;
- diff check, compileall, targeted unittest, Ruff and Mypy.

### Commit intent

`feat: add governed automation persistence`

## 5. Slice 2 — Schedule Worker and Telegram Controls

### Files

- `src/group_llm_agent/automation.py`
- `src/group_llm_agent/automation_control.py`
- `src/group_llm_agent/platforms/telegram.py`
- `src/group_llm_agent/runtime.py`
- `src/group_llm_agent/app.py`
- `src/group_llm_agent/config.py`
- `tests/test_automation.py`
- `tests/test_automation_control.py`
- `tests/test_runtime.py`

### Changes

- implement IANA timezone validation, weekday two-slot calculation and deterministic DST policy;
- implement current/previous-slot tick, 30-minute catch-up and no correctness-critical cursor;
- pre-work and pre-claim rechecks for enabled/paused/subscriber/config/persona/deadline state;
- run scheduler in an independent daemon lifecycle with its own SQLite connections;
- implement closed `/food_*` command grammar, authenticated bot target and admin/self authorization;
- aggregate preferences without member identity and load five successful primary keys;
- make status show own subscription, count, next slot, version and last outcome without member list;
- feature-gate scheduler default disabled and keep polling healthy when worker fails.

### Checks

- controlled clocks: Monday/Saturday, Shanghai defaults, two meal slots, timezone/DST edge;
- config change affects only unleased future occurrence;
- 0/1/20 subscribers still produces 0/1/1 occurrence effects;
- command addressed to foreign bot, non-admin mutation and cross-member operation are rejected;
- disable deletes active subscription preferences; pause does not stop ordinary replies;
- restarts at +20/+40 minutes execute once/skip late;
- two workers and same tick acquire one lease;
- scheduler exception leaves Telegram polling and recognition alive.

### Commit intent

`feat: schedule subscribed food occurrences`

## 6. Slice 3 — Tavily Search/Extract and URL Safety

### Files

- `src/group_llm_agent/tavily.py`
- `src/group_llm_agent/tools.py`
- `src/group_llm_agent/config.py`
- `src/group_llm_agent/runs.py`
- `tests/test_tavily.py`
- `tests/test_tools.py`
- config tests

### Changes

- implement fixed `https://api.tavily.com/search|extract` requests with Bearer auth;
- use basic search/extract, safe search, no answer/raw/image, bounded results/content and usage metadata;
- normalize 400/401/429/432/433/5xx/timeout/transport/protocol/oversize without causes/secrets;
- add `web_search` and `web_fetch` with opaque result IDs and current-turn URL allow set;
- validate scheme, credentials, ports, DNS/global IP, same normalized Extract URL and dedupe;
- scheduled fetch accepts only current-run search results; inbound fetch additionally accepts current-message URL;
- mark page material untrusted and persist only bounded source/audit metadata;
- key missing/invalid means Web unavailable, not application startup failure.

### Checks

- exact outgoing JSON/headers/timeouts and no hidden retries;
- key/base URL absent from repr, errors, logs, prompts and audit;
- oversized/invalid JSON/wrong type/empty/multiple/mismatched URL matrices;
- localhost/private/link-local/reserved/DNS-rebind/credential/port/redirect negatives;
- fetch-before-search, previous-turn URL and model-supplied raw URL rejected;
- provider prompt injection remains data and causes no mutation;
- no network access in unit tests; fake opener captures exact contract.

### Commit intent

`feat: add bounded Tavily read tools`

## 7. Slice 4 — Independent Budgets and Food Writer Contract

### Files

- `src/group_llm_agent/model.py`
- `src/group_llm_agent/effector.py`
- `src/group_llm_agent/tools.py`
- `src/group_llm_agent/events.py`
- `src/group_llm_agent/context.py`
- `src/group_llm_agent/config.py`
- `tests/test_model_client.py`
- `tests/test_effector.py`
- `tests/test_tools.py`

### Changes

- add strict scheduled-only `food_recommendation` response shape;
- raise hard model completion ceiling to 11 while reserving one final completion;
- retain context ordinary 3/complex 5 and add independent Web 5 counter;
- count rejected, failed, invalid and timed-out attempts in their requested category;
- share deadline, cumulative 16 KiB admitted tool content, source/cost and safety stop conditions;
- retain context-call 4–5 novelty/extension rules and reject duplicate/unneeded Web attempts;
- compile typed scheduled persona prompt from aggregate preferences/location/history, never fake member text;
- validate one primary + two distinct alternatives through application-owned generic dish and
  reason registries, with recent-five exclusion and no model-authored recommendation prose;
- resolve one current-turn source per sourced merchant choice, derive displayed/source identities
  in the application and render exact stable text with cautious wording;
- scheduled failures degrade to generic or silence, never an unsolicited technical failure reply.

### Checks

- 0, 3, 5 context calls; 0, 5 Web calls; mixed 5+5+final theoretical path;
- attempted sixth context/Web call rejected before provider; counters do not consume each other;
- model attempt 11, deadline and cumulative result bound terminate correctly;
- direct/contextual existing paths and sticker/vision safety remain unchanged;
- primary repetition, duplicate alternative, no-location merchant, free-form allergy/medical
  reassurance, unsupported fact/source and leakage negatives;
- generic no-location/no-Web, sourced current merchant facts and conflict downgrade positives;
- Writer tool result cannot alter subscription, persona, memory or tool policy.

### Commit intent

`feat: write sourced scheduled food recommendations`

## 8. Slice 5 — Stable Delivery and Recovery Integration

### Files

- `src/group_llm_agent/automation.py`
- `src/group_llm_agent/runtime.py`
- `src/group_llm_agent/runs.py`
- `src/group_llm_agent/platforms/telegram.py`
- `src/group_llm_agent/app.py`
- `tests/test_automation_runtime.py`
- `tests/test_runtime.py`
- delivery/restart tests

### Changes

- persist validated payload and exact rendered text before the external-effect claim;
- reuse prepared content after restart and recheck config/subscription/persona before claim;
- send one text external effect with nullable trigger message and occurrence ID uniqueness;
- reconcile durable external `sent`/`failed` acknowledgements to occurrence history and map only
  ambiguous claimed-without-ack recovery to `uncertain`;
- never retry definite or uncertain scheduled effects automatically;
- advance recent-primary history only for acknowledged `sent` outcomes;
- expose status/outcome without leaking message text or subscriber data.

### Checks

- crash before prepare recomputes; after prepare reuses byte-identical text;
- crash before claim may resume; at/after claim sends zero additional effects;
- success/definite/timeout/invalid-response/restart-with-claim matrices;
- config disable, last unsubscribe and persona change racing before claim fail closed;
- concurrent inbound messages/polling are not blocked by scheduled model/Tavily work;
- one occurrence produces at most one visible Telegram message.

### Commit intent

`feat: deliver scheduled food effects once`

## 9. Slice 6 — Integration, Documentation and Release Carrier

### Files

- `deploy/.env.example`
- `deploy/compose.yaml`
- `deploy/README.md`
- `README.md`
- `CHANGELOG.md`
- `docs/feature/lezhi-scheduled-food-recommendations-v0-4/verification.md`
- package metadata and full test suite

### Required proof

- exact controlled-clock end-to-end matrix for REQ-050/AC-024;
- compileall and full unittest discovery;
- Ruff check/format and Mypy;
- migration from exact v4 fixture and SQLite quick check;
- wheel/sdist contents and isolated entry point;
- sh syntax, Compose rendering and candidate Docker build/run;
- credential/private-key/query/Web-body leakage scan;
- disabled-by-default startup with normal Telegram polling;
- candidate status shows no enabled group and no Tavily call;
- fake-provider Tavily success/failure/injection/URL/budget evidence;
- exact external effect and occurrence audit evidence.

### Verification carrier

`verification.md` records exact implementation SHA, commands, test counts, image identity,
requirement/AC closure and explicit limitations. It must state that no real Tavily call, group enable,
Compose restart or real scheduled Telegram message occurred unless a later explicit deployment gate
actually authorizes and proves it. Secrets, full queries, page bodies, prompts and chat text are omitted.

### Commit intent

`docs: verify scheduled food recommendations`

## 10. F4 Execution and Commit Sequence

Planned implementation commits are intentionally reviewable:

1. `feat: add governed automation persistence`
2. `feat: schedule subscribed food occurrences`
3. `feat: add bounded Tavily read tools`
4. `feat: write sourced scheduled food recommendations`
5. `feat: deliver scheduled food effects once`
6. `docs: verify scheduled food recommendations`

Tests may be committed with the slice they prove. A mechanical refactor required by the maintainability
gate is either included with its behavior-neutral tests before Slice 1 or committed separately as
`refactor: isolate effect run persistence`.

## 11. Review, Merge and Deployment Gates

After deterministic verification:

1. push the exact feature head and create a PR to the exact current `main`;
2. dispatch an immutable exact-head review request with merge disabled unless policy/user later authorizes it;
3. remediate every finding in a new commit and request exact-head re-review;
4. merge only through lifecycle authorization and record squash SHA/URL/time;
5. treat Tavily credentials/provider probe, Compose restart, group enable/subscription and real scheduled
   Telegram messages as separate deployment/debug work requiring explicit authorization;
6. preserve automation disabled and ordinary chat operational if any deployment gate fails.

The implementation may not silently enable automation, consume external provider credits or send a
test meal recommendation merely because code review passes.

## 12. Requirements Traceability by Slice

| Slice | Requirements / acceptance criteria |
| --- | --- |
| 1 typed source and repository | REQ-001–002, REQ-011–012, REQ-016–020, REQ-024, REQ-045–049; AC-006–008, AC-019–021 |
| 2 scheduler and controls | REQ-003–020, REQ-045–050; AC-001–008, AC-018, AC-020–021, AC-024 |
| 3 Tavily and URL safety | REQ-029–035, REQ-038–044; AC-011–014, AC-016–017, AC-019, AC-022–023 |
| 4 budgets and food Writer | REQ-021–044, REQ-047; AC-009–017, AC-022–024 |
| 5 delivery/recovery | REQ-016–024, REQ-047–049; AC-006–009, AC-018, AC-020, AC-024 |
| 6 integration/release proof | REQ-001–050; AC-001–024 |

## 13. F3 Exit Decision

The design has been decomposed into bounded, dependency-ordered implementation slices with tests and
commit boundaries. No unresolved product decision remains. F3 is complete and F4 may begin with the
mandatory maintainability gate and baseline proof. External provider, deployment and Telegram-write
permissions remain outside F4 authorization.
