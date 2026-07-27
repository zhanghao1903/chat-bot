# Verification: Telegram 群聊基础骨架 0.1

- Lifecycle phase: F5 Verification, Examples, And Documentation
- Status: Complete with FINDING-001 remediated, FINDING-002 evidence corrected, and explicitly deferred external smoke
- Original implementation snapshot: `6e01fec288439cd672df12dcdcbb0ff7bd5efe65`
- Initial reviewed snapshot: `c5662b54d72769cc18157579f456f0ca7e8a3640`
- FINDING-001 remediation verification snapshot: `04f54adb338100e3775c9c527e04a742788f7c7c`
- Requirements snapshot: `dc620c1023a3cbadc5138036553ea8284f56ba70`
- Verified: 2026-07-27

## Verification Boundary

The original implementation snapshot
`6e01fec288439cd672df12dcdcbb0ff7bd5efe65` established the 0.1 runtime and its
initial 23-test suite. After independent review found FINDING-001, remediation
snapshot `04f54adb338100e3775c9c527e04a742788f7c7c` added the security fix and five
regression tests.

The remediation verification snapshot was exported with `git archive` into a
clean directory before the checks recorded below. It contained only the
confirmed requirements, design/plan, 0.1 runtime, 28 deterministic tests, and
deployment assets. Untracked legacy prototypes, research files,
repository-local skills, local virtual environments, and generated build
output were absent. Thus, every clean-snapshot result below—including the
28-test result and FINDING-001 closure—reproduces from
`04f54adb338100e3775c9c527e04a742788f7c7c`, not the original implementation
snapshot.

No Telegram bot token or target group credential was available. A real group
smoke therefore remains an operator-owned external proof. The deterministic
suite exercises the same configuration, Bot API request/response, update
normalization, processing, delivery-ledger, startup, and failure boundaries
without a real secret.

## Checks

| Check | Result | Evidence |
| --- | --- | --- |
| Python compilation | PASS | `python3 -m compileall -q src tests` |
| Clean scoped unit suite | PASS | `PYTHONPATH=src python3 -m unittest discover -s tests -v` — 28 tests |
| Shared-checkout regression suite | PASS | Same command — 41 tests including pre-existing tests |
| Ruff lint | PASS | `uv run --with ruff ruff check <scoped files>` |
| Ruff formatting | PASS | `uv run --with ruff ruff format --check <scoped files>` |
| Static typing | PASS | Mypy completed with no issues in nine source files |
| Package build | PASS | `uv build` produced the 0.1.0 sdist and wheel |
| Installed entry point | PASS | Installed console script returned expected exit `2` for missing token |
| Deployment script syntax | PASS | `sh -n deploy/manage.sh` |
| Compose render | PASS | Compose rendered service, external env, read-only root, and data volume |
| Secret-pattern scan | PASS | No Telegram-token, API-key, or private-key pattern found |
| Docker image build | NOT RUN | Docker CLI is present, but the local daemon is not running |
| Real Telegram group smoke | NOT RUN | Requires operator-owned token, group, and Telegram permissions |

The unavailable Docker and Telegram proofs are environmental limitations. They
do not conceal a failing automated check.

## Review Remediation

`FINDING-001` from review dispatch
`2e70ef2c1c9c85783c48e2d038fcc8d4ccc7cb888fbeb5424ab106551136cb1c`
was reproduced and remediated:

- startup rejects Bot API tokens containing whitespace, control characters, or
  other characters outside the validated BotFather token shape;
- configuration diagnostics name only `TELEGRAM_BOT_TOKEN` and a safe reason;
- request construction, `urlopen`, context-entry, and response-body transport
  failures become redacted `TelegramApiError` categories with suppressed
  exception context;
- `InvalidURL` and response-body `TimeoutError` have direct regression tests;
- captured startup output proves the complete unsafe test token is absent; and
- a real `TelegramBotApiClient` body-read timeout enters
  `TelegramPollingService`'s configured wait-and-retry path.

Independent re-review of
`04f54adb338100e3775c9c527e04a742788f7c7c` confirmed FINDING-001 is closed.
That re-review reported `FINDING-002` because the prior version of this document
did not identify the immutable remediation snapshot behind its 28-test
evidence. This follow-up documentation change corrects that carrier mismatch;
the resulting PR head still requires exact-head re-review before merge.

## Requirement Evidence

| ID | Evidence | Status |
| --- | --- | --- |
| REQ-001 | Settings validation, `getMe` identity gate, startup exit-code tests, polling service | Implemented; real-group smoke deferred |
| REQ-002 | Adapter accepts ordinary `message.text` from group/supergroup updates | PASS |
| REQ-003 | Adapter tests assert text, group ID, sender ID, and message ID | PASS |
| REQ-004 | Runtime test asserts exact `1` sends reply `1` tied to message `10` | PASS |
| REQ-005 | Runtime test asserts ` 1` and other-group text are silent | PASS |
| REQ-006 | Self/bot filters plus same-process and reopened-ledger replay tests | PASS |
| REQ-007 | Unsafe-token rejection, captured redacted startup output, redacted request/open/read failures, non-bot identity rejection, and body-timeout polling retry | PASS |
| REQ-008 | Malformed update followed by valid update still sends the valid reply | PASS |
| REQ-009 | Clean snapshot has a top-level `deploy/` separate from `src/` | PASS |
| REQ-010 | All new service/deployment assets are under `deploy/` | PASS |
| REQ-011 | `deploy/README.md` documents every asset, prerequisite, entry point, verification, and recovery | PASS |
| REQ-012 | Env templates use empty placeholders; ignore rules and secret scan pass | PASS |

## Acceptance-Criteria Evidence

| ID | Evidence | Status |
| --- | --- | --- |
| AC-001 | Valid identity startup test reaches `telegram_polling_started`; package entry point builds | Deterministic PASS; live Telegram deferred |
| AC-002 | Adapter normalization test asserts exact text and all required identifiers | PASS |
| AC-003 | Exact-trigger runtime test asserts one `sendMessage` reply to the original message | PASS |
| AC-004 | Whitespace/unmatched-text test asserts no send | PASS |
| AC-005 | Bot-authored update and explicit authenticated-bot sender both remain silent | PASS |
| AC-006 | Unsafe/invalid token or identity exits non-zero; redacted body-read timeout waits then retries | PASS |
| AC-007 | Malformed update does not block the following valid update | PASS |
| AC-008 | Clean-snapshot file inventory and Compose render prove the deployment asset boundary | PASS |
| AC-009 | Deployment README provides purpose, external configuration, and management commands | PASS |
| AC-010 | Empty templates, `.gitignore`, minimal ledger schema, and secret scan prove the tracked boundary | PASS |

## Manual Telegram Smoke

An operator with authorized credentials can close the remaining external proof:

1. Copy `deploy/.env.example` to `deploy/.env`.
2. Set the real `TELEGRAM_BOT_TOKEN` and negative `TELEGRAM_CHAT_ID`.
3. Add the bot to that group and configure privacy mode/permissions so ordinary
   group text is delivered.
4. Run `deploy/manage.sh start` and `deploy/manage.sh logs`.
5. Confirm `telegram_identity_verified` appears before `telegram_polling_started`.
6. Send exact text `1`; confirm one reply `1` targets the original message.
7. Send ` 1`, `1 `, and another text; confirm silence.
8. Restart the service; confirm the old trigger is not replied to again.
9. Stop with `deploy/manage.sh stop`; retain the named data volume.

Do not paste the token into this document, PR, Issue, test output, or logs.

## Limitations And Release Readiness

- Live Telegram behavior remains unproven until an authorized operator performs
  the manual smoke above.
- The Dockerfile could not be built locally because Docker Desktop/daemon was
  stopped; its Compose model and package build both passed.
- 0.1 intentionally excludes LLM, moderation, media, private chat, multi-group
  configuration UI, message-content persistence, automated CI/CD, and release
  publishing.
- The code and deployment package are ready for independent review. Publishing
  a release was not requested.
