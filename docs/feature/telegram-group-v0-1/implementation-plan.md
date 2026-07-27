# Implementation Plan: Telegram 群聊基础骨架 0.1

- Lifecycle phase: F3 Implementation Plan
- Status: Accepted for implementation
- Design: `docs/feature/telegram-group-v0-1/design.md`
- Updated: 2026-07-27

## Slice 1: Runtime Contract And Telegram Boundary

Files:

- `src/group_llm_agent/config.py`
- `src/group_llm_agent/models.py`
- `src/group_llm_agent/platforms/telegram.py`
- `tests/test_config.py`
- `tests/test_telegram_adapter.py`
- `tests/test_telegram_client.py`

Changes:

- Define validated runtime settings for token, one target group, database,
  polling timeout, retry delay, and log level.
- Define the normalized group-text and fixed-reply action types.
- Implement redacted `getMe`, `getUpdates`, and `sendMessage` calls.
- Normalize only ordinary group/supergroup text while preserving exact text.
- Ignore bot senders and unsupported/malformed updates without leaking secrets.

Proof:

- Missing/invalid configuration fails deterministically.
- Normalization preserves identifiers and exact text.
- Private, non-text, malformed, and bot-authored updates are ignored.
- Telegram failures expose a stable method/status without exposing the token.

## Slice 2: Fixed Reply And At-Most-Once Delivery

Files:

- `src/group_llm_agent/storage.py`
- `src/group_llm_agent/runtime.py`
- `tests/test_runtime.py`
- `tests/test_storage.py`

Changes:

- Create the minimal SQLite delivery ledger and unique delivery key.
- Enforce the configured group and authenticated bot identity.
- Remain silent for text other than exact `1`.
- Claim, send, and mark the fixed reply.
- Record redacted failures and continue after a malformed update or failed send.
- Advance the polling offset so poison updates do not block later messages.

Proof:

- Exact `1` sends one reply tied to the trigger.
- Whitespace variants and other text remain silent.
- Replayed updates never produce a second reply, including after reopening the database.
- A failed send is recorded and does not prevent later valid messages.
- A malformed update does not stop the following valid update.

## Slice 3: Executable Service And Operator Experience

Files:

- `src/group_llm_agent/app.py`
- `src/group_llm_agent/__main__.py`
- `src/group_llm_agent/__init__.py`
- `.env.example`
- `.gitignore`
- `pyproject.toml`
- `README.md`

Changes:

- Build the service from validated settings and initialize the ledger.
- Prove bot identity with `getMe` before logging successful startup.
- Run polling with bounded retry and graceful keyboard interruption.
- Return non-zero exit codes for configuration and startup failures.
- Replace prototype-focused instructions with the accepted 0.1 quick start,
  configuration, behavior, privacy, and recovery contract.

Proof:

- Module and installed console entry points share the same exit behavior.
- Startup tests cannot report success before identity validation.
- Python compilation and the full deterministic suite pass.

## Slice 4: Deployment And Service Assets

Files:

- `deploy/Dockerfile`
- `deploy/compose.yaml`
- `deploy/.env.example`
- `deploy/manage.sh`
- `deploy/README.md`

Changes:

- Build and run the service as a non-root user.
- Keep the token and target group in an external `.env`.
- Persist only the SQLite delivery ledger.
- Provide build/start/stop/restart/status/log commands.
- Document BotFather, group permissions/privacy mode, verification, recovery,
  rollback, and secret boundaries.

Proof:

- `deploy/` is the single entry point for all new service/deployment assets.
- Shell syntax passes.
- Tracked deployment files contain placeholders but no token.
- Compose references the external environment and persistent data volume.

## Slice 5: Verification Carrier And PR Readiness

Files:

- `docs/feature/telegram-group-v0-1/verification.md`
- `CHANGELOG.md`

Changes:

- Map every requirement and acceptance criterion to test or inspection evidence.
- Record exact commands, results, unavailable external proof, and limitations.
- Add the 0.1 user-facing release record.
- Verify a clean committed snapshot, not only the dirty shared checkout.

Checks:

```text
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
sh -n deploy/manage.sh
python3 -m build
```

If `build` is not installed, verify package installation from the clean
snapshot with `python3 -m pip install --no-deps` into a temporary target and
record the unavailable build frontend explicitly.

## Commit And Review Plan

1. Commit F2 design.
2. Commit F3 implementation plan.
3. Commit only in-scope runtime, tests, deployment assets, and stable docs.
4. Leave staged repository-local skills, research documents, legacy prototype
   modules, and legacy tests untouched unless an exact file is deliberately
   replaced by this feature.
5. Push the dedicated branch.
6. Open a non-draft PR with problem, behavior/API impact, tests, proof,
   documentation, changelog, limitations, and rollback.
7. Fix exact base/head SHAs, prepare one immutable review request, and dispatch
   it to the configured independent reviewer.

## External Proof Boundary

A real Telegram group smoke requires an administrator-provided bot token,
target group, and Telegram-side permissions. No credential is present in the
repository. The implementation and deterministic transport tests can complete
without it; the PR must state whether the real smoke remains an operator step.

