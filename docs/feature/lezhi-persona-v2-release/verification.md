# Verification: 乐枝人格 v2 发布与低频版本管理

- Status: Verified and deployed
- Requirements: `25eacf0c81fb903f131ffa5b113b1740d0cf4512`
- RequirementsHandoff: `48d7910e4afefc7854dcfaab227e3880bacac102f24ac23877df8c07856ef820`
- Implementation snapshot: `7c9f4cdacc6a993d2d45fb432f11f4035c270e5c`
- Verified: 2026-08-02

## Immutable artifacts

| Artifact | Verified identity |
| --- | --- |
| Source ZIP | `c78c3be1835d1ad5d25c1bb41ea9ccaa60f8d90a365f59e7cf563d10a6c2ac06` |
| Source character | `600fed847d362f272739d6613874aac857e339c02bc76c18619d104280dbbfcc` |
| Source evaluation cases | `676d03a5f2e5bf4b2c822ab507abe4516c133a4d6ad754dd265dbfdabb7cb08d` |
| Source examples | `7172725c8e1aed81470b8c9257b54ba8f93fa87fcf4e5d99e5df906f0382b420` |
| Production v2 bundle | `lezhi-v2.0` / `0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603` |
| Preserved v1 rollback | `lezhi-v1.0` / `25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a` |
| Provider report | `b8d83f99777d360fcfecff2cb3e585c5b6b5eb173d157544ae6ee02f8eb39fcb` |

The schema-v2 loader accepted exactly the nineteen normative character fields, the complete
four-file production bundle and one-to-one IDs `CB-EVAL-001` through `CB-EVAL-037`. Tests prove
every normative field reaches at least one application-owned Trigger, Recognition or Effector
view and all three views retain one immutable persona identity. The v1 files and bundle digest are
unchanged.

## Deterministic verification

The implementation and final smoke-fix snapshots passed:

- `python3 -m compileall -q src tests`;
- `PYTHONPATH=src python3 -m unittest discover -s tests -q`: 167 tests;
- Ruff check and format check: 54 source/test files;
- Mypy: 27 source files, no issues;
- `uv build`, shell syntax, Compose rendering and `git diff --check`;
- strict source/import, schema, content-digest, view coverage, memory transition, approved
  provider-report provenance, release-state, post-pin rollback boundary, database-path
  preservation and durable trigger-audit smoke regressions.

The built exact candidate image is
`sha256:304eb30086c99a5a949031ddc5b6c2424ece02290daba5ce6752e2cb02165659`.

## Real-provider gate

The configured OpenAI-compatible production client ran both Writer generation and structured
judge calls with model `gpt-5.6-sol`. The canonical report contains all 37 cases: 33 scored 10,
four scored 9, minimum score 9, and zero critical violations. Calls were bounded to two attempts
for retry-safe transport failures. The report excludes credentials, Base URL, full prompts and
provider envelopes.

Activation is bound to the exact report SHA-256
`b8d83f99777d360fcfecff2cb3e585c5b6b5eb173d157544ae6ee02f8eb39fcb`, provider label
`configured-openai-compatible` and reviewer `provider-model-judge:gpt-5.6-sol`. The verifier also
compares every case's dimension and critical flag with the immutable bundle. A canonical synthetic
replacement with fabricated identities, replies, rationales and consistently passing 10/10 scores
was rejected with `unapproved_evaluation_report` before activation.

## Deployment and rollback evidence

The discovered pre-release service was a manually created v1 container rather than Compose. It
used persistent volume `telegram-bot-persona-uat-data-v1` and database
`/app/data/telegram-bot.sqlite3`. The release therefore first performed a reversible migration to
the repository Compose service while leaving the old container stopped and recoverable.

Before activation:

- v1 and v2 exact pins and the passing provider report passed release preflight;
- SQLite `PRAGMA quick_check` returned `ok`;
- the current named volume identity and historical database filename were recorded;
- Compose started v1 against that same volume and emitted the exact v1 startup identity;
- no volume or database was deleted, recreated or renamed.

The controlled release then updated only the two persona selector lines and restarted the same
Compose service. Startup emitted:

```text
persona_bundle_loaded persona_id=lezhi persona_version=lezhi-v2.0 persona_digest=0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603
telegram_identity_verified
telegram_polling_started
```

The v2 container is running against `telegram-bot-persona-uat-data-v1`; the database quick check
still returns `ok`. The release state retains the exact v1 rollback pin. A release-tool defect was
found before formal smoke: with member memory disabled, privacy-preserving inbound messages are
transient and therefore cannot be counted in `group_messages`. The smoke boundary was corrected to
use the always-durable, content-free `trigger_evaluations` audit. The regression suite proves this
works without enabling message persistence.

After the corrected trigger-evaluation baseline `31`, the operator sent one direct
`@YaoshiMaomaoBot` message in the configured group. Formal smoke recorded exactly one new
`direct_platform` trigger, decision `effect_requested`, one external effect with status `sent`, and
persona `lezhi-v2.0` at the exact production digest. `deploy/manage.sh persona-smoke` returned:

```text
persona_smoke_passed outcome=sent external_effects=1
```

## Review remediation

Independent review requested changes at snapshot
`371acef4440c8f98234391750b79923d42e34d7a`. FINDING-001 is closed by the immutable approved-report
binding and bundle-owned case-contract checks described above. FINDING-002 is closed by a single
post-pin rollback path covering eight activation boundaries and five smoke boundaries. Shell-level
fake-Compose regressions prove every boundary restores v1 and records `attempted` then `succeeded`;
a separate regression proves a failed restore is recorded as `failed` and never as success. A real
state-file regression proves the final redacted failure stage/result is persisted canonically.

The repaired path was also exercised against the local deployment. Reusing the completed old smoke
window correctly failed at `smoke_verify` with no new inbound; the script recorded the failure,
restored the exact v1 pin, restarted v1 and recorded rollback `succeeded`. The formal release command
then revalidated the exact approved report, rebuilt the candidate and activated v2 again on the same
named volume. Current startup reports the exact v2 identity, Telegram polling is active, SQLite
`PRAGMA quick_check` is `ok`, and a fresh optional operator-smoke baseline is recorded at trigger
evaluation `48`.

## Acceptance matrix

| Acceptance | Result | Evidence |
| --- | --- | --- |
| AC-001–002 | Pass | Exact source hashes, immutable v1/v2 bundles, nineteen-field view coverage |
| AC-003 | Pass | 37-case real-provider report, minimum 9/10, zero critical violations |
| AC-004–006 | Pass | Strict startup pin, schema and exact-ID negative regressions |
| AC-007 | Pass | Exact approved report SHA/provider/reviewer plus bundle-owned case contracts |
| AC-008–009 | Pass | Fail-closed preflight, same named volume/database, Compose v1 then v2 startup |
| AC-010 | Pass | One direct-platform trigger, one sent effect, exact v2 snapshot |
| AC-011 | Pass | Every post-pin boundary matrix plus successful real v2→v1 rollback drill |
| AC-012–013 | Pass | Local Docker target only; exact selector persisted in external environment |
| AC-014 | Pass | v1→v2→v1 neutral/subjective memory transition regressions |
| AC-015–016 | Pass | Immutable overwrite rejection and documented release/rollback runbook |

## Operational limitations

- No remote host or inbound network listener was used; Telegram and model access remain outbound
  HTTPS connections.
- The stopped pre-Compose v1 container is intentionally retained until v2 smoke and review are
  complete. It is not running and does not poll Telegram.
- The already completed operator smoke proves the unchanged Telegram/Writer runtime. Baseline `48`
  is retained for an optional fresh post-remediation message; it is not an unimplemented code gate.
