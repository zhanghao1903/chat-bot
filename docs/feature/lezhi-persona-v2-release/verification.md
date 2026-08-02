# Verification: 乐枝人格 v2 发布与低频版本管理

- Status: Deployment active; Telegram smoke pending
- Requirements: `25eacf0c81fb903f131ffa5b113b1740d0cf4512`
- RequirementsHandoff: `48d7910e4afefc7854dcfaab227e3880bacac102f24ac23877df8c07856ef820`
- Implementation snapshot: `27ba98346df882dd397900a27d4d8c68ccfd5ca1`
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

The exact implementation snapshot passed:

- `python3 -m compileall -q src tests`;
- `PYTHONPATH=src python3 -m unittest discover -s tests -q`: 163 tests;
- Ruff check and format check: 53 source/test files;
- Mypy: 27 source files, no issues;
- `uv build`, shell syntax, Compose rendering and `git diff --check`;
- strict source/import, schema, content-digest, view coverage, memory transition, provider-report,
  release-state, database-path preservation and smoke-boundary regressions.

The built exact candidate image is
`sha256:d056aee6d5e0fb70854d67bad0d4ab379c049e88398c4c051848e288aa32e42f`.

## Real-provider gate

The configured OpenAI-compatible production client ran both Writer generation and structured
judge calls with model `gpt-5.6-sol`. The canonical report contains all 37 cases: 33 scored 10,
four scored 9, minimum score 9, and zero critical violations. Calls were bounded to two attempts
for retry-safe transport failures. The report excludes credentials, Base URL, full prompts and
provider envelopes.

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
still returns `ok`. The release state retains the exact v1 rollback pin. The final bounded Telegram
message check is pending one operator-owned direct group message.

## Acceptance matrix

| Acceptance | Result | Evidence |
| --- | --- | --- |
| AC-001–002 | Pass | Exact source hashes, immutable v1/v2 bundles, nineteen-field view coverage |
| AC-003 | Pass | 37-case real-provider report, minimum 9/10, zero critical violations |
| AC-004–006 | Pass | Strict startup pin, schema and exact-ID negative regressions |
| AC-007 | Pass | Canonical real-provider report and independent report verification |
| AC-008–009 | Pass | Fail-closed preflight, same named volume/database, Compose v1 then v2 startup |
| AC-010 | Pending | Requires one operator-owned Telegram direct message |
| AC-011 | Pass | Exact v1 state, automatic rollback path and retained stopped v1 container |
| AC-012–013 | Pass | Local Docker target only; exact selector persisted in external environment |
| AC-014 | Pass | v1→v2→v1 neutral/subjective memory transition regressions |
| AC-015–016 | Pass | Immutable overwrite rejection and documented release/rollback runbook |

## Operational limitations

- The bounded Telegram smoke remains pending the operator message recorded above.
- No remote host or inbound network listener was used; Telegram and model access remain outbound
  HTTPS connections.
- The stopped pre-Compose v1 container is intentionally retained until v2 smoke and review are
  complete. It is not running and does not poll Telegram.

