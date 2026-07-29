# 原创人格、成员认识与作家上下文能力：验证记录

Status: IMPLEMENTATION VERIFIED; EXTERNAL PERSONA ACCEPTANCE PENDING

## 1. Verification Boundary

All code, tests, packaging metadata, deployment assets and the production Character Bundle were
exported from this immutable implementation snapshot before verification:

```text
2576118f376c494e88772863762f7cc0bb9f356d
```

The clean tree was created with `git archive`; it contained no untracked `uv.lock`, local `.env`,
database, log, credential or build output. The later F5 documentation commit changes only
documentation carriers and `CHANGELOG.md`; it is not presented as the implementation snapshot
above.

Accepted upstream contracts:

| Contract | Immutable evidence |
| --- | --- |
| Requirements | `c5ea34553e52505ff50ee421cc08efff297df01f`, SHA-256 `4478b593c404971b24aadff6f755a8d545b544efa59c43e649d5d207e8f72a3c` |
| Requirements handoff | `9d436ac128ed195223045c72be7ac134dff5177d8d4de11f0ad077dc8e223c32` |
| Character Bible | `3dd1f8b56c9e7e4d4bda9f8c75450570a2902126`, SHA-256 `46eb6a18323b5549e7a0b3dbc30f3d56e902356d52bb86ba294d0ae5f9542f68` |
| Character Bible handoff | `def972836a4f35c10a3fe42e694ce5f1c375b111d195e676ec276e1e0e9165a3` |
| Production persona | `lezhi-v1.0`, bundle SHA-256 `25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a` |

## 2. Automated Evidence

Checks were run on 2026-07-29 against the clean snapshot above:

| Command/proof | Result |
| --- | --- |
| `python3 -m compileall -q src tests` | PASS |
| `PYTHONPATH=src python3 -m unittest discover -s tests -v` | PASS, 103 tests |
| `uvx ruff check .` | PASS |
| `uvx ruff format --check .` | PASS, 54 files formatted |
| `/opt/anaconda3/bin/mypy src` | PASS, 22 source files |
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

The built local image identity was:

```text
sha256:71b3322c5d8bb82b951635a0d6afc1d0b65f186dad2593bfd207c48ae565b90e
```

This is local build evidence, not a published release image or stable registry digest.

## 3. Acceptance Matrix

| Acceptance criterion | Deterministic evidence | Status |
| --- | --- | --- |
| AC-001 | Accepted Character Bible bytes/digest, bundle confirmation references, `test_production_persona` | PASS |
| AC-002 | Original character fields, 15 examples, prohibited-identity scan, fixed cases 001/002/022 | PASS (static contract) |
| AC-003 | `test_trigger`, `test_effector`, `test_persona_runtime`; one immutable persona snapshot and one external effect | PASS |
| AC-004 | Direct/contextual model-failure degradation, unknown-member and timeout tests | PASS |
| AC-005 | `ContextAssembler`, `lookup_member_memory`, `search_recent_group_messages`, memory/recognition tests | PASS |
| AC-006 | Zero-tool writer path, empty/unavailable tool handling, contextual silence | PASS |
| AC-007 | Invalid/injected tool rejection, untrusted-result delimiters, factual/safety Character Bundle rules | PASS |
| AC-008 | Three-model/two-tool/deadline limits and audited tool-result tests | PASS |
| AC-009 | Effector cannot write memory; independent Recognition job/worker tests | PASS |
| AC-010 | Additive schema, group/member/category/source/time/confidence repository tests | PASS |
| AC-011 | Later-evidence revision/revoke, confidence decay and database-conflict tests | PASS |
| AC-012 | Unknown-member context is empty and Character Bundle forbids invented familiarity | PASS |
| AC-013 | Relationship states, fixed cases 006/007/019–021 and shared snapshot | PASS (static contract); provider comparison pending |
| AC-014 | Third-person disclosure prohibition, scoped tool inputs and reset/control tests | PASS (contract and enforcement) |
| AC-015 | Cross-group foreign-key, search, reset and memory-scope tests | PASS |
| AC-016 | Sensitive inference and risk-score rejection tests | PASS |
| AC-017 | Capability/notice/administrator checks; persistence begins only after successful notice | PASS |
| AC-018 | Self/member/group reset, reset generation and stale-job race tests | PASS |
| AC-019 | Twenty-message bound, raw-text expiry and restart-compatible derived memory tests | PASS |
| AC-020 | Read-only registry, injected scope, invalid tool and external-effect ownership tests | PASS |
| AC-021 | 22 fixed cases, `8/10` thresholds and critical flags are immutable and packaged | PARTIAL: provider scoring and real-group gate pending |
| AC-022 | First release provides immediate context plus durable recognition using two bounded read-only tools | PASS |

The matrix distinguishes system correctness from model quality. Scripted model tests prove
determinism, scope, idempotency and failure behavior; they do not claim that an operator-selected
model has passed the five-dimension persona rubric.

## 4. Production Persona Evidence

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

## 5. External Proof Not Executed

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

## 6. Rollout And Release Decision

- Default and rollback mode: `fixed`.
- Production persona activation: explicit path, exact digest and model configuration only.
- Recommended rollout: `fixed` → offline 22-case model scoring → `persona_direct` with memory
  disabled → authorized memory disclosure → `persona_full`.
- Release publication: not requested; no package version, tag, registry image or GitHub release
  was created.
- Current decision: repository implementation is reviewable; real-group persona rollout remains
  blocked by the external proof in section 5.
