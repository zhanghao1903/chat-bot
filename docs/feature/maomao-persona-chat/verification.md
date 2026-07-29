# 原创人格、成员认识与作家上下文能力：验证记录

Status: IMPLEMENTATION VERIFIED; EXTERNAL PERSONA ACCEPTANCE PENDING

## 1. Verification Boundary

The original implementation, packaging assets and production Character Bundle were completed at:

```text
2576118f376c494e88772863762f7cc0bb9f356d
```

Review dispatch `bcfa31579c0af7da4e76d715fa0dee0498c1a9518b220952d1d8c1c8f00ecb4d`
reviewed head `9b5cc44f53dcb962f9192546daada7b645339b68` and requested four changes.
The first remediation implementation snapshot closed FINDING-001, FINDING-003 and FINDING-004
and attempted FINDING-002:

```text
7a03536766bfb5c8e5c699a0e4f2fd633c328114
```

Review dispatch `25f30db8aeabac6c7fb247e41765ab4d003794fc31d606be942219241e62a8e7`
reviewed documentation carrier `d637eafc4383275ce47023f109817fb9b3b6efbe`, confirmed
FINDING-001/003/004 fixed, and kept FINDING-002 open because the regex-based gate remained
bypassable and over-rejected benign relationship language. The final closed-semantic
remediation and its persistence-boundary regressions were completed in this immutable
implementation snapshot:

```text
1ab2ea3ce23c59bafbbb6a32a32de132fa6774c1
```

The automated evidence below was rerun from a clean `git archive` of that final remediation
snapshot.
It contained no untracked `uv.lock`, local `.env`, database, log, credential or build output.

Review dispatch `4656ae8bc70f2e93e15f09c6bf8c7196d822b8e092660f23b526caed4839fda1`
approved documentation carrier `8e5e58fc2a137dd841c5551724f585e0ffd4c5e1`. During the
explicitly authorized provider/deployment UAT that followed, the exact approved adapter was
found to ignore its `response_schema`: OpenAI-compatible `json_object` mode returned a valid
JSON alias such as `{"reply": ...}` that the application correctly rejected but could not use.
The compatibility remediation, explicit role contracts and regressions were completed in:

```text
754e0efa10a4c2bcb1df18c9c4799d853acfaee8
```

The current verification carrier is a documentation-only follow-up and is not presented as
the implementation snapshot.

Accepted upstream contracts:

| Contract | Immutable evidence |
| --- | --- |
| Requirements | `c5ea34553e52505ff50ee421cc08efff297df01f`, SHA-256 `4478b593c404971b24aadff6f755a8d545b544efa59c43e649d5d207e8f72a3c` |
| Requirements handoff | `9d436ac128ed195223045c72be7ac134dff5177d8d4de11f0ad077dc8e223c32` |
| Character Bible | `3dd1f8b56c9e7e4d4bda9f8c75450570a2902126`, SHA-256 `46eb6a18323b5549e7a0b3dbc30f3d56e902356d52bb86ba294d0ae5f9542f68` |
| Character Bible handoff | `def972836a4f35c10a3fe42e694ce5f1c375b111d195e676ec276e1e0e9165a3` |
| Production persona | `lezhi-v1.0`, bundle SHA-256 `25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a` |

## 2. Automated Evidence

Checks were run on 2026-07-29 against a clean `git archive` of provider-compatibility
remediation snapshot `754e0efa10a4c2bcb1df18c9c4799d853acfaee8`:

| Command/proof | Result |
| --- | --- |
| `python3 -m compileall -q src tests` | PASS |
| `PYTHONPATH=src python3 -m unittest discover -s tests` | PASS, 114 tests |
| `uvx ruff check src tests` | PASS |
| `uvx ruff format --check src tests` | PASS, 43 files formatted |
| `uvx mypy src/group_llm_agent` | PASS, 23 source files |
| `uv build --out-dir <clean temp>` | PASS, sdist and wheel produced |
| Inspect wheel package data | PASS, all four `lezhi-v1.0` bundle files present |
| Install wheel into a clean venv | PASS |
| Run installed entry point without required token | PASS, expected safe exit code 2 |
| `sh -n deploy/manage.sh` | PASS |
| `docker compose ... config --quiet` with `.env.example` | PASS |
| Credential/private-key pattern scan | PASS, no match |
| `docker info --format '{{.ServerVersion}}'` | PASS, Docker 29.4.0 |
| `docker compose ... build` | PASS |
| Built image metadata | PASS, `app` user and `group-llm-agent` command |
| One-shot container load of exact bundle digest/version | PASS, `lezhi lezhi-v1.0 22` |
| Real configured DeepSeek endpoint through exact application client | PASS, full Writer context produced strict `kind=reply` |

The built local image identity was:

```text
sha256:21047c40798138f05868c9ea58af98f20bb10bcabc8884beaf7c24b2edbc2b9f
```

This is local build evidence, not a published release image or stable registry digest.

## 3. Review Finding Closure

| Finding | Remediation evidence | Status |
| --- | --- | --- |
| FINDING-001 | Application-owned final-effect validation now rechecks the persona snapshot and deadline, rejects protocol JSON and internal/tool/memory markers, and degrades to direct failure reply or contextual silence. Unit tests cover marker, JSON, late-result and post-model snapshot failures; the runtime test proves leaked content is never sent. | FIXED |
| FINDING-002 | The recognition model no longer authors persistent statements. It may return only an exact application-owned `(semantic_key, category)` pair; `memory_safety.py` resolves that pair from an immutable safe registry and the application renders the canonical stored statement. Unknown/mismatched keys and extra free-form statement fields fail closed before persistence. End-to-end worker tests reject registered-Democrat, DNC-donation, Sunni-practice, lithium-treatment and hiring-score proposals while persisting explicit benign member-support, group-plan and group-activity semantics. | FIXED |
| FINDING-003 | Telegram command entities retain their target; the adapter drops foreign-target commands before classification, and `MemoryControlService` independently validates the target against the authenticated username. Destructive and ordinary foreign-bot command tests prove no authorization, mutation, audit or send occurs. | FIXED |
| FINDING-004 | Durable ingestion deduplication is now distinct from terminal effect processing. A replay without an external-effect claim restarts the same unique effect/trigger run; an existing claim or intentional silence remains terminal. Restart tests cover ingestion-only, processing, completed-reply-before-claim, claimed, silence and already-sent boundaries. | FIXED |
| UAT-FINDING-001 | The adapter now canonically injects the bounded application schema into the leading system instruction; Trigger, Writer and Recognition also state exact accepted JSON shapes and reject observed aliases. Unit tests prove schema transmission and role prompts. A real configured DeepSeek call with the full production Writer context returned strict `kind=reply`. | FIXED; NEW EXACT-HEAD REVIEW REQUIRED |

## 4. Acceptance Matrix

| Acceptance criterion | Deterministic evidence | Status |
| --- | --- | --- |
| AC-001 | Accepted Character Bible bytes/digest, bundle confirmation references, `test_production_persona` | PASS |
| AC-002 | Original character fields, 15 examples, prohibited-identity scan, fixed cases 001/002/022 | PASS (static contract) |
| AC-003 | `test_trigger`, `test_effector`, `test_persona_runtime`; one immutable persona snapshot, resumable pre-claim run and one external effect | PASS |
| AC-004 | Direct/contextual model-failure degradation, unknown-member and timeout tests | PASS |
| AC-005 | `ContextAssembler`, `lookup_member_memory`, `search_recent_group_messages`, memory/recognition tests | PASS |
| AC-006 | Zero-tool writer path, empty/unavailable tool handling, contextual silence | PASS |
| AC-007 | Invalid/injected tool rejection, untrusted-result delimiters, factual/safety Character Bundle rules | PASS |
| AC-008 | Three-model/two-tool limits, audited tool results and post-model deadline rejection | PASS |
| AC-009 | Effector cannot write memory; independent Recognition job/worker tests | PASS |
| AC-010 | Additive schema, group/member/category/source/time/confidence repository tests | PASS |
| AC-011 | Later-evidence revision/revoke, confidence decay and database-conflict tests | PASS |
| AC-012 | Unknown-member context is empty and Character Bundle forbids invented familiarity | PASS |
| AC-013 | Relationship states, fixed cases 006/007/019–021 and shared snapshot | PASS (static contract); provider comparison pending |
| AC-014 | Third-person disclosure prohibition, scoped tool inputs, final leakage rejection and never-send runtime test | PASS (contract and enforcement) |
| AC-015 | Cross-group foreign-key, search, reset and memory-scope tests | PASS |
| AC-016 | Closed application-owned semantic registry, no model-authored persistent statement, and adversarial/benign persistence-boundary tests | PASS |
| AC-017 | Capability/notice/administrator checks; persistence begins only after successful notice | PASS |
| AC-018 | Self/member/group reset, reset generation and stale-job race tests | PASS |
| AC-019 | Twenty-message bound, raw-text expiry and restart-compatible derived memory tests | PASS |
| AC-020 | Read-only registry, injected scope, invalid tool and external-effect ownership tests | PASS |
| AC-021 | 22 fixed cases, `8/10` thresholds and critical flags are immutable and packaged | PARTIAL: provider scoring and real-group gate pending |
| AC-022 | First release provides immediate context plus durable recognition using two bounded read-only tools | PASS |

The matrix distinguishes system correctness from model quality. Scripted model tests prove
determinism, scope, idempotency and failure behavior; they do not claim that an operator-selected
model has passed the five-dimension persona rubric.

## 5. Production Persona Evidence

Static bundle conformance passed:

- exact confirmed Character Bible bytes and references;
- one digest/version across Trigger, Recognition and Effector;
- 15 original examples;
- `CB-EVAL-001` through `CB-EVAL-022` exactly once;
- every case records the confirmed `8/10` threshold;
- critical cases/prohibitions represented;
- no known researched framework or protected-character identity in production content;
- all four bundle files present in both wheel and Docker image.

The provider behavioral gate is recorded separately in
`docs/feature/maomao-persona-chat/persona-evaluation.md`.

## 6. Provider Compatibility Evidence

The operator-owned Code Agent `.env` was read only at runtime and was not copied into this
repository or image. Secret values and configured Base URLs were not printed. Compatibility
smokes established:

- the configured DeepSeek OpenAI-compatible endpoint supports the selected model and strict
  application Writer contract after `UAT-FINDING-001`;
- the configured OpenAI-compatible endpoint was reachable but its selected model did not pass
  the strict response probe;
- the configured Claude endpoint did not pass either the native or OpenAI-compatible probe.

DeepSeek is therefore the only provider selected for this `persona_direct` UAT. These smokes
prove transport/protocol compatibility only; they do not constitute the independent 22-case
persona score.

## 7. External Proof Not Executed

The following checks require operator-owned credentials, external service consumption and/or
real-group authorization and were not run:

1. Generate and independently score the selected production model on all 22 fixed cases.
2. Run `fixed`, `persona_direct`, and `persona_full` in the real target Telegram group.
3. Publish the memory disclosure via an actual administrator `/memory_enable`.
4. Prove recognition continuity across a real service restart.
5. Prove `/memory_forget_me`, member reset, group reset and cross-group isolation with real users.
6. Inspect production logs for absence of Telegram/model secrets, full prompts and provider bodies.

The earlier Telegram `1 → 1` user-side smoke belongs to the prior 0.1 feature and is not
misrepresented as persona-mode proof for this snapshot.

## 8. Rollout And Release Decision

- Default and rollback mode: `fixed`.
- Production persona activation: explicit path, exact digest and model configuration only.
- Recommended rollout: `fixed` → offline 22-case model scoring → `persona_direct` with memory
  disabled → authorized memory disclosure → `persona_full`.
- Release publication: not requested; no package version, tag, registry image or GitHub release
  was created.
- Current decision: provider compatibility is proven; real-group persona rollout waits for the
  exact-head review of `UAT-FINDING-001`, then proceeds in `persona_direct` with memory disabled.
