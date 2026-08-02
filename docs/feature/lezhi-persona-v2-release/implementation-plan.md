# Implementation Plan: 乐枝人格 v2 发布与低频版本管理

- Status: Implemented and production-verified
- Requirements: `requirements.md` at `25eacf0c81fb903f131ffa5b113b1740d0cf4512`
- Design: `design.md` at `1e6912b611c8e5ae0cc0103b98aa47e222bf307f`
- Branch: `codex/lezhi-persona-v2-release`
- Written: 2026-08-02

## 1. Delivery Contract

Implementation must add and activate `lezhi-v2.0` without changing any byte in
`lezhi-v1.0`, widening Telegram/model/tool permissions, or deleting/rebuilding the persistent
database volume. The release remains fail-closed until deterministic verification, all 37 real
provider cases and deployment preflight pass. A failed startup or smoke restores the exact v1
path/digest recorded before the service is stopped.

The revised requirements handoff
`48d7910e4afefc7854dcfaab227e3880bacac102f24ac23877df8c07856ef820` corrects only the source
character-file digest. All slices, boundaries and stop conditions remain unchanged; importer and
tests use the corrected 64-character value.

## 2. Planned Boundaries

```text
src/group_llm_agent/
  persona.py                         # schema-aware load, validation and view compiler
  persona_evaluation.py              # bounded real-provider evaluator and report verifier
  persona_release.py                 # source import, preflight and safe environment pin helpers
  app.py                             # non-sensitive active persona startup audit
  persona_bundles/lezhi/
    lezhi-v1.0/                      # unchanged rollback artifact
    lezhi-v2.0/                      # new immutable four-file production bundle

tests/
  test_persona.py
  test_persona_v2.py
  test_persona_evaluation.py
  test_persona_release.py
  test_app.py
  test_memory.py

deploy/
  manage.sh                          # validate/release commands, existing lifecycle preserved
  README.md
  .env.example

docs/feature/lezhi-persona-v2-release/
  requirements.md
  design.md
  implementation-plan.md
  provider-evaluation.json           # redacted exact provider evidence
  verification.md
```

No database migration, Telegram API change, group command, public listener or new runtime tool is
planned.

## 3. Slice 1 — Schema v2 and Immutable Import

### Files

- `src/group_llm_agent/persona.py`
- `src/group_llm_agent/persona_release.py`
- `tests/test_persona.py`
- `tests/test_persona_v2.py`
- `tests/test_persona_release.py`

### Changes

1. Split manifest validation into schema-1 and schema-2 exact field contracts.
2. Add schema-2 source-artifact metadata and validate its exact names/digests.
3. Add the exact nineteen-field v2 character contract and bounded recursive JSON validation.
4. Require `persona_meta` identity/version/name to map exactly to the manifest snapshot.
5. Strengthen evaluation coverage from the schema-1 subset rule to an exact schema-2 one-to-one
   37-ID rule while preserving schema-1 behavior.
6. Add immutable field tuples for the three v2 views; expose their source-field sets for direct
   losslessness tests.
7. Add a ZIP importer that rejects unsafe/unexpected archive members, verifies the confirmed ZIP
   and member digests, preserves the three source bytes, creates a canonical manifest in a
   temporary sibling directory, validates it, then atomically renames it into a nonexistent
   version directory.
8. Reject overwrite, incomplete candidate, content/version reuse and mismatched source metadata.

### Checks

- Existing v1 digest and tests remain unchanged.
- Confirmed ZIP and all three member hashes match.
- v2 has exactly 37 cases/examples with IDs `CB-EVAL-001` through `CB-EVAL-037`.
- Every one of nineteen source fields appears in at least one compiled view; all three snapshots
  match.
- Missing/unknown fields, wrong IDs/versions, duplicates, path traversal, symlinks, stale digest
  and overwrite attempts fail closed.

### Commit intent

`feat: add immutable Lezhi persona v2 bundle`

## 4. Slice 2 — Memory and Startup Compatibility

### Files

- `src/group_llm_agent/app.py`
- `tests/test_app.py`
- `tests/test_memory.py`
- `tests/test_persona_runtime.py`

### Changes

1. Add one safe startup audit event with persona ID/version/digest after the exact bundle is loaded
   and before polling starts; never log policy content or endpoint/credentials.
2. Add explicit v1→v2→v1 memory transition tests:
   neutral facts/observations remain visible, subjective v1 items disappear under v2, unknown
   persona-bound items stay hidden, new v2 subjective items remain isolated, and v1 items become
   visible again after rollback.
3. Prove the group policy activation changes only the selected snapshot and does not reset memory,
   messages, audits or reset generation.
4. Prove startup bundle failure occurs before Telegram client construction or network calls.

### Checks

- Existing 142-test baseline and all added compatibility tests pass.
- Captured logs expose only allowed non-sensitive identity fields.
- Wrong v2 path/digest/version prevents any Telegram factory call.

### Commit intent

Included with Slice 1 because loader, startup and migration compatibility form one candidate.

## 5. Slice 3 — Real-Provider Evaluation Gate

### Files

- `src/group_llm_agent/persona_evaluation.py`
- `tests/test_persona_evaluation.py`
- `pyproject.toml` only if a console script/package-data rule is required

### Changes

1. Add a CLI that consumes the existing model environment variable names and exact persona
   path/digest, without accepting or printing a secret argument.
2. Load all 37 evaluation/example pairs from the candidate bundle and use the exact compiled
   Effector policy/examples for candidate generation.
3. Require the application Writer reply/silence protocol; failures, timeouts and extra fields fail
   the run.
4. Run one structured judge call per candidate with a strict score/rationale/critical-violation
   schema and the confirmed case contract.
5. Record provider label, model ID, generation settings, timestamp, candidate output/silence,
   score, violation list and reviewer; omit Base URL, keys, full prompts and provider envelopes.
6. Write only a complete canonical report via atomic replacement. Return nonzero if the report is
   incomplete, any score is below 8, or any critical violation is present.
7. Add a report verifier reusable by release preflight. It requires exact bundle digest, all 37
   IDs, the intended model ID/settings and a passing result.

### Checks

- Scripted protocol tests cover pass, low score, critical violation, timeout, invalid provider
  result, wrong digest/model/config, interrupted write and secret redaction.
- A real configured provider run produces all 37 outputs and judge decisions.
- The verifier independently accepts the exact report and rejects any modified field.

### Commit intent

`feat: gate persona activation on provider evaluation`

## 6. Slice 4 — Controlled Release and Rollback

### Files

- `src/group_llm_agent/persona_release.py`
- `tests/test_persona_release.py`
- `deploy/manage.sh`
- `deploy/.env.example`
- `deploy/README.md`

### Changes

1. Add `deploy/manage.sh persona-preflight <report>` to validate the current external environment,
   exact selected bundle and report without stopping the service.
2. Add `deploy/manage.sh persona-release <candidate-path> <candidate-digest> <report>` which:
   acquires a lock; validates v1 rollback and v2 candidate; records only non-secret current pins;
   atomically changes the two persona pin lines while preserving every other byte/value; performs
   the existing Compose restart; then checks the service state and bounded startup logs.
3. Keep Telegram smoke as a second explicit `persona-smoke` step so the operator controls the one
   inbound message. It inspects only post-release SQLite audit counters/snapshot and never sends a
   synthetic group message itself.
4. Add automatic `persona-rollback` invocation when restart/startup/smoke validation fails.
5. Never use `down --volumes`, remove the named volume, expose secret env values, connect to another
   host, or infer a `latest` version.
6. Store redacted state/evidence under ignored `deploy/state/` with strict permissions.

### Checks

- Unit tests use a fake Compose runner and temporary environment to prove byte-preserving secret
  handling, exact pin changes, rollback, lock exclusion and no volume deletion.
- Shell syntax and Compose rendering pass.
- Real preflight records the current v1 path/digest/image/service/volume before activation.

### Commit intent

`feat: add controlled persona release and rollback`

## 7. Slice 5 — Verification, Docs and Release Record

### Files

- `README.md`
- `CHANGELOG.md`
- `deploy/README.md`
- `docs/feature/lezhi-persona-v2-release/provider-evaluation.json`
- `docs/feature/lezhi-persona-v2-release/verification.md`

### Required proof

| Acceptance | Proof |
| --- | --- |
| AC-001–002 | exact source hashes, immutable v1 tree, v2 load and nineteen-field mapping |
| AC-003 | real-provider outputs for reaction, humor, help, repair and embodiment cases |
| AC-004–006 | strict startup pin and exact 37-ID data tests |
| AC-007 | canonical passing 37-case provider report |
| AC-008 | preflight negative matrix leaves running v1 unchanged |
| AC-009 | Compose restart state plus unchanged volume identity |
| AC-010 | one operator message, one/zero external effect and exact v2 snapshot |
| AC-011 | rollback drill with exact v1 path/digest and service recovery |
| AC-012–013 | local Compose-only command and second-start persistence proof |
| AC-014 | v1/v2 memory transition regression |
| AC-015–016 | overwrite rejection and operator runbook walk-through |

### Full checks

Run from an exact clean snapshot:

```text
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
uvx ruff check src tests
uvx ruff format --check src tests
uv run mypy src
uv build
sh -n deploy/manage.sh
docker compose --env-file <external-env> config
docker build <exact-source-context>
```

Also verify installed-wheel startup failure with missing Telegram credentials, wheel inclusion of
both immutable bundles and release modules, no tracked secret/private artifact, exact image bundle
load, v1 rollback load, real-provider report, container startup audit and Telegram smoke.

### Commit intent

`docs: record Lezhi persona v2 release verification`

## 8. Execution Order and Stop Conditions

1. Commit and push this F3 plan.
2. Implement Slices 1–2 and create the exact v2 bundle from the confirmed source.
3. Implement and deterministically test the evaluation/release gates.
4. Commit/push a stable candidate and run all clean-snapshot checks.
5. Run the bounded real-provider 37-case evaluation using the intended deployment model.
6. If and only if it passes, finalize the redacted report and verification carrier, commit/push,
   build the exact image and run preflight.
7. Record the active v1 rollback point and volume identity before changing the environment.
8. Activate v2 through the current Compose target and verify startup.
9. Ask the operator to send one direct Telegram message, then verify bounded smoke evidence.
10. On any activation/smoke failure, restore v1 immediately; otherwise retain v2 and record the
    deployed state.
11. Prepare a PR and independent review request only after the committed candidate and operational
    evidence are stable.

Implementation stops without deployment when any source, deterministic, provider, preflight or
rollback gate cannot be proven.
