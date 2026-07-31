# Verification: 乐枝对话连续性触发 v0.2

- Status: Repository verification passed
- Verified at: 2026-07-31
- Requirements commit: `1e467fe7942ae057424e8600eb493759d4bc456c`
- Requirements SHA-256: `1fdd2e87e35c1cb4f1cd9e5794946daee2d4d879fbefc832c8f4bc8e92f76f2a`
- Implementation snapshot: `950d46a7e499a9423e5171bb3c5ba1a1fb4887b7`
- Verification snapshot: `1b3f2db7fe44735e3a9f38fbf2a7a7d7c8c67404`
- Branch: `codex/lezhi-conversation-triggers-v0-2`

## Evidence Boundary

The implementation snapshot contains all source, schema, tests, and acceptance-matrix changes. The
verification snapshot adds only `README.md`, `deploy/README.md`, and `CHANGELOG.md`; source and tests
are byte-identical to the implementation snapshot. All commands below were run against the exact
verification snapshot before this carrier was added. The carrier commit therefore changes only this
verification document and does not claim that an earlier implementation SHA contained later tests.

Repository verification proves deterministic trigger contracts, persistence and replay behavior,
packaging, local deployment rendering, and a candidate image. It does not substitute for consuming a
real provider or sending operator-owned Telegram messages.

## Implemented Contract

- The immutable Character Bundle formal name is the only first-release natural-language address
  term; group text cannot teach aliases.
- High-precision application-owned matching accepts vocatives and explicit name requests while
  keeping discussion, quotes, historical references, block quotes, and lists out of name-direct.
- Continuity eligibility anchors only the current group's latest confirmed outbound bot message,
  with an inclusive ten-minute and five-subsequent-human-message bound inside the existing recent-20
  scene.
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
| AC-002 | PASS | `test_addressing` rejects discussion, other-member addressing, quoted/block-quoted text, historical assertions, and list occurrences as name-direct. |
| AC-003 | PASS | `test_persona_runtime.test_recent_direct_reply_can_continue_without_addressing_in_direct_mode` anchors the actual sent message and executes Trigger then Writer without the ordinary gate. |
| AC-004 | PASS | `test_continuity` validates the four-way protocol; `test_trigger` proves `continue` produces a continuity-category effect tied to the confirmed outbound anchor. |
| AC-005 | PASS | `test_persona_runtime.test_natural_close_is_silent_and_not_recorded_as_failure` records completed `close` silence and sends no extra message. |
| AC-006 | PASS | The acceptance matrix scripts `not_addressed` for unrelated adjacency and proves ordinary fallback with no continuity effect. |
| AC-007 | PASS | `test_trigger.test_ambiguous_continuity_can_reach_existing_ordinary_participation` proves ambiguity does not guess and only reaches ordinary participation when its hard cadence is eligible. |
| AC-008 | PASS | `test_continuity` and the acceptance matrix reject other-group, wrong-bot, missing/unsent, future, and expired anchors. Existing Telegram adapter/runtime tests continue to ignore private-equivalent and other-group input. |
| AC-009 | PASS | The acceptance matrix proves control wins over explicit/name/continuity signals and Telegram explicit direct wins over name/continuity; ordinary cadence remains last. |
| AC-010 | PASS | Existing runtime replay tests plus new mixed-signal end-to-end tests prove self messages produce no effect and an inbound event can claim at most one external effect. |
| AC-011 | PASS | Configured-term-only matcher and injection/window tests prove group text cannot add nicknames, expand ten minutes/five messages, or override prompt/schema/safety contracts. |
| AC-012 | PASS | Migration/repository and trigger/runtime tests distinguish direct platform, direct name, continuity, ordinary, control, and ignored outcomes with safe reasons and actual anchor IDs. |
| AC-013 | PASS | `test_continuity` maps provider failure to audited ambiguous fallback; runtime/effector regression preserves one neutral failure reply only for direct-path Writer failure. |
| AC-014 | PASS | The complete 138-test suite covers unchanged persona digest, recognition safety, group isolation, context, tools, final validation, transport, control, and delivery contracts. |
| AC-015 | PASS | `test_conversation_trigger_runtime` centralizes the critical name, mention, four-way continuity, priority, scope, window, and injection matrix; the full suite has zero unexpected effects or duplicate sends. |

## Exact Verification Commands

Run from a clean `1b3f2db7fe44735e3a9f38fbf2a7a7d7c8c67404` checkout:

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
- Unit discovery passed 138 tests.
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
- Exact verification-snapshot image tag: `group-llm-agent:lezhi-trigger-v0-2-1b3f2db`.
- Image ID: `sha256:8712ff9545b3d2053e743fa45985be1c09e107fc672d914c04fe192eca28aafc`.
- Read-only inspection: user `app`; command `group-llm-agent`.
- A one-shot no-credential container loaded persona `lezhi`, version `lezhi-v1.0`, all 22
  evaluation cases, and formal address term `乐枝`.
- Compose continues to expose no inbound port and uses the existing read-only root,
  `no-new-privileges`, tmpfs, and persistent data volume configuration.

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
