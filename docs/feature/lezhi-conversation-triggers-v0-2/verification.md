# Verification: 乐枝对话连续性触发 v0.2

- Status: Review remediation verification passed
- Verified at: 2026-07-31
- Requirements commit: `1e467fe7942ae057424e8600eb493759d4bc456c`
- Requirements SHA-256: `1fdd2e87e35c1cb4f1cd9e5794946daee2d4d879fbefc832c8f4bc8e92f76f2a`
- Initial implementation snapshot: `950d46a7e499a9423e5171bb3c5ba1a1fb4887b7`
- Initial verification snapshot: `1b3f2db7fe44735e3a9f38fbf2a7a7d7c8c67404`
- Review remediation snapshot: `4ccb29a7aed0c14272e7c1c2bfc4876fd050ab21`
- Branch: `codex/lezhi-conversation-triggers-v0-2`

## Evidence Boundary

The initial implementation snapshot contains the original source, schema, tests, and
acceptance-matrix changes. The initial verification snapshot adds only `README.md`,
`deploy/README.md`, and `CHANGELOG.md`. The review remediation snapshot contains the deterministic
fixes, regression tests, and corresponding design/operator-documentation corrections for
FINDING-001 and FINDING-002. All commands and Docker proof below were rerun against that exact
remediation snapshot before this carrier was added. This carrier changes only this verification
document and does not claim that an earlier SHA contained later fixes or tests.

Repository verification proves deterministic trigger contracts, persistence and replay behavior,
packaging, local deployment rendering, and a candidate image. It does not substitute for consuming a
real provider or sending operator-owned Telegram messages.

## Implemented Contract

- The immutable Character Bundle formal name is the only first-release natural-language address
  term; group text cannot teach aliases.
- High-precision application-owned matching accepts vocatives and explicit name requests while
  keeping discussion, quotes, historical references, block quotes, terminal lists, and
  whitespace-separated third-person statements out of name-direct.
- Continuity eligibility anchors only the current group's latest confirmed outbound bot message,
  with an inclusive ten-minute and five-subsequent-human-message bound inside the existing recent-20
  scene. The member message's Telegram whole-second timestamp must be strictly later than the anchor;
  earlier and same-second messages fail closed to ordinary cadence.
- A strict Trigger-role schema returns exactly `continue`, `close`, `not_addressed`, or `ambiguous`;
  time adjacency is explicitly not semantic evidence.
- Priority is group/self/control, Telegram explicit direct, persona-name direct, continuity, then
  unchanged ordinary cadence.
- `continue` requests one contextual-semantics effect, `close` is terminal intentional silence, and
  unrelated/ambiguous/provider failure falls back to ordinary cadence or silence.
- Both `persona_direct` and `persona_full` support name-direct and continuity; only unrelated
  proactive participation remains excluded from `persona_direct`.
- Additive migration 2 records minimal final trigger category, result, reason, model status,
  persona-name hit, and continuity anchor ID without prompt/model response/message text.
- Existing one-external-effect claims, replay recovery, Character Bundle snapshot, group isolation,
  recent context, memory, tool budgets, final validation, failure behavior, and outbound-record order
  remain in force.

## Deterministic Acceptance Matrix

| AC | Result | Evidence |
| --- | --- | --- |
| AC-001 | PASS | `test_addressing` accepts all three confirmed “乐枝” vocatives; `test_persona_runtime` proves name-direct bypasses ordinary cadence in `persona_direct` and sends once. |
| AC-002 | PASS | `test_addressing` rejects discussion, other-member addressing, quoted/block-quoted text, historical assertions, terminal list/enumeration occurrences, and whitespace-separated third-person statements as name-direct. |
| AC-003 | PASS | `test_persona_runtime.test_recent_direct_reply_can_continue_without_addressing_in_direct_mode` uses a later polling batch and a strictly later Telegram second, anchors the actual sent message, and executes Trigger then Writer without the ordinary gate. |
| AC-004 | PASS | `test_continuity` validates the four-way protocol; `test_trigger` proves `continue` produces a continuity-category effect tied to the confirmed outbound anchor. |
| AC-005 | PASS | `test_persona_runtime.test_natural_close_is_silent_and_not_recorded_as_failure` records completed `close` silence and sends no extra message. |
| AC-006 | PASS | The acceptance matrix scripts `not_addressed` for unrelated adjacency and proves ordinary fallback with no continuity effect. |
| AC-007 | PASS | `test_trigger.test_ambiguous_continuity_can_reach_existing_ordinary_participation` proves ambiguity does not guess and only reaches ordinary participation when its hard cadence is eligible. |
| AC-008 | PASS | `test_continuity` and the acceptance matrix reject other-group, wrong-bot, missing/unsent, future, expired, pre-anchor, and same-second anchors. `test_persona_runtime` rejects same-poll causal inversion with transient and persisted memory while preserving a genuine later-poll reply. Existing Telegram adapter/runtime tests continue to ignore private-equivalent and other-group input. |
| AC-009 | PASS | The acceptance matrix proves control wins over explicit/name/continuity signals and Telegram explicit direct wins over name/continuity; ordinary cadence remains last. |
| AC-010 | PASS | Existing runtime replay tests plus new mixed-signal end-to-end tests prove self messages produce no effect and an inbound event can claim at most one external effect. |
| AC-011 | PASS | Configured-term-only matcher and injection/window tests prove group text cannot add nicknames, expand ten minutes/five messages, or override prompt/schema/safety contracts. |
| AC-012 | PASS | Migration/repository and trigger/runtime tests distinguish direct platform, direct name, continuity, ordinary, control, and ignored outcomes with safe reasons and actual anchor IDs. |
| AC-013 | PASS | `test_continuity` maps provider failure to audited ambiguous fallback; runtime/effector regression preserves one neutral failure reply only for direct-path Writer failure. |
| AC-014 | PASS | The complete 141-test suite covers unchanged persona digest, recognition safety, group isolation, context, tools, final validation, transport, control, delivery, terminal-address, and causal-anchor contracts. |
| AC-015 | PASS | `test_conversation_trigger_runtime` centralizes the critical name, mention, four-way continuity, priority, scope, window, and injection matrix; the full suite has zero unexpected effects or duplicate sends. |

## Exact Verification Commands

Run from a clean `4ccb29a7aed0c14272e7c1c2bfc4876fd050ab21` checkout:

```text
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests
/private/tmp/uv-cache-claude-lifecycle/archive-v0/qm13iOgOFt4hUCt_AMJMb/bin/ruff check src tests
/private/tmp/uv-cache-claude-lifecycle/archive-v0/qm13iOgOFt4hUCt_AMJMb/bin/ruff format --check src tests
mypy src
UV_CACHE_DIR=/private/tmp/uv-cache-lezhi-trigger uv build
sh -n deploy/manage.sh
TELEGRAM_BOT_ENV_FILE=../.env.example docker compose -f deploy/compose.yaml config --quiet
```

Results:

- Compileall passed.
- Unit discovery passed 141 tests.
- Ruff check passed; Ruff format reported 48 files already formatted.
- Mypy reported no issues in 25 source files.
- Build produced `group_llm_agent-0.1.0.tar.gz` and
  `group_llm_agent-0.1.0-py3-none-any.whl`.
- The wheel contains `addressing.py`, `continuity.py`, and all four production `lezhi-v1.0`
  bundle files.
- An isolated installation of the wheel returned the expected safe exit code 2 with
  `TELEGRAM_BOT_TOKEN` absent.
- Shell syntax and Compose rendering passed using the tracked redacted example environment.
- A tracked-file private-key, Telegram-token, and common model-key pattern scan returned no files.
- Git status was clean; build output, local virtual environments, databases, `.env`, and proof
  dumps are ignored and untracked.

## Docker Proof

- Docker Engine server: 29.4.0.
- Exact remediation-snapshot image tag: `group-llm-agent:lezhi-trigger-v0-2-4ccb29a`.
- Image ID: `sha256:38e5644a2a9e7129ea7c3f27816c777b48195888fa2516eb0bc22e2d0face04e`.
- Read-only inspection: user `app`; command `group-llm-agent`.
- A one-shot no-credential container loaded persona `lezhi`, version `lezhi-v1.0`, all 22
  evaluation cases, and formal address term `乐枝`.
- Compose continues to expose no inbound port and uses the existing read-only root,
  `no-new-privileges`, tmpfs, and persistent data volume configuration.

## Review Remediation

- `FINDING-001` fixed: a terminal persona name is no longer promoted merely because whitespace or
  punctuation precedes it. The matcher requires positive address evidence and rejects the exact
  reviewed list/third-person examples while retaining `你觉得呢，乐枝？`.
- `FINDING-002` fixed: the continuity gate compares the member and anchor at Telegram whole-second
  precision and requires the member timestamp to be strictly later. Same-second ordering is
  intentionally fail-closed. Unit coverage proves before/same/next-second behavior; end-to-end
  coverage proves same-batch pre-anchor messages cannot continue in transient or persisted mode,
  while a genuine later-batch message can.

## Migration, Rollout, and Rollback

- Migration 2 is additive: one checked `effect_runs.trigger_category` column plus the minimal
  `trigger_evaluations` table and index. No raw-text retention or memory contract is expanded.
- No new environment variable, webhook, listener, public port, or router/NAT rule is required.
- Rollout uses the existing image replacement and database volume, then operator smoke for formal
  name, answer continuity, natural close, unrelated adjacency, explicit mention, and duplicate
  delivery.
- Rollback restores the prior image or `fixed` mode while preserving the database. The prior binary
  ignores additive audit schema; operators should not delete the volume merely to roll back behavior.

## Operational Follow-up Limitations

- Real Telegram group UAT remains pending the exact reviewed/merged image, operator-owned bot/model
  credentials, target-group messages, and permissions.
- A real provider continuity-role probe is pending. Scripted strict-schema tests prove application
  protocol behavior; they do not prove every configured provider follows the four-way role prompt.
- Independent 22-case persona-quality scoring remains a separate operational gate and is not missing
  feature code.
- Meal recommendation, learned aliases, media/private triggers, and longer memory remain deferred.
