# Verification: 乐枝默认头像部署与复合表情回复 v0.3.1

- Status: Implementation verified; independent review and production release pending
- Verified at: 2026-08-04
- Safe-forward baseline: `88c775c8ef0be7d1c63fd71b5924334b12492d75`
- Exact implementation snapshot: `2bbbb3824c856ed5fe199a36fc32c3e814828b33`
- Requirements commit: `86ace06b0704da458646747e3ca0468456235851`
- Requirements SHA-256: `66b82b3db77ffba968d26b651a2cccfc7a85e500b36a79a8aa41722a6b67593d`
- Fixed evaluation SHA-256: `6ea34402129e92e10c571dce77c8005c5bd0aa7d607641954e6da429a32a769b`

## Verification Boundary

The exact implementation snapshot descends from the confirmed safe-forward
baseline. `git merge-base` returned the exact baseline SHA. The previous
production snapshot `c1e820ae...` was not used as a build base, so the merged
v0.4 subscription, food-recommendation, schema-migration, command, scheduler,
Tavily, and runtime paths remain in the candidate.

The repository expression assets are byte-identical to the baseline:
`git diff --name-only 88c775c...2bbbb38 --
src/group_llm_agent/expression_assets` returned no files. The implementation
does not enable VISION or automatic avatar rotation and does not apply a mood
avatar.

## Implemented Contracts

### Composite persona replies

- Added the closed `reply_with_sticker` Writer/final-effect kind.
- Inbound persona replies may contain one text component, one sticker
  component, or text then sticker; scheduled food, controls, tools, and other
  external writes remain on their existing single-effect paths.
- Writer output selects only an application-owned semantic ID. Platform
  `file_id`, arbitrary URLs, and extra visible components are not accepted.
- The application-owned expression policy keeps necessary-text, medical,
  self-harm, safety, illegal, permission, serious relationship, relationship
  strength, and adjacent-repeat bounds above the frequency target.
- An invalid composite sticker safely degrades to the already validated text.

### Durable bundle delivery

- Additive migration 6 creates `effect_bundles` and
  `effect_bundle_components` after the v0.4 migration set.
- Bundle/component rows record immutable snapshots, order, semantic identity,
  claims, and outcomes without full message text or credentials.
- Text is sent before sticker. Text explicit failure prevents sticker send;
  sticker explicit failure after text becomes text-only degraded.
- Timeout, transport, invalid/unknown response, and claimed-before-crash
  boundaries are terminal uncertain and are never retried.
- Restart after text success never sends a late sticker. Duplicate processing
  cannot repeat a sent or uncertain component.

### Expression measurement

- Metrics are scoped to exact bot/persona/catalog identities, the latest seven
  days, and at most 100 qualifying bundles.
- Fewer than 30 samples returns `insufficient_data`; the report exposes only
  aggregate counts, time bounds, and a ratio.
- The denominator requires application-owned sticker eligibility and at least
  one sent visible component. Safety/relationship-ineligible, non-matching
  snapshots, all-failed, silence, and non-triggered turns do not count.
- Sticker-only and successfully delivered composite stickers both count in the
  numerator. A composite whose text succeeds and sticker explicitly fails is
  a qualifying text-only outcome.
- Regressions cover 29/30 and 100/101 boundaries, the exact seven-day edge,
  snapshot isolation, partial failure, and exclusions.
- The fixed schema-v2 set contains 48 cases: 40 eligible plus bounded
  necessary-text, hard-forbidden, and relationship guards. Computed passing
  bounds are 16 through 28 sticker-bearing eligible cases (0.40 through 0.70);
  self-reported pass cannot override computed failure.

### Default avatar apply

- The only authorized avatar is `lezhi-default` from deployment-approved
  catalog SHA-256
  `b871161e68c18115893d7aea932dabf1e9101d40278d6ce9168a6eb3735d405a`
  and image SHA-256
  `fd7ec0efafb9dc1e36856461228cecbf7467548c7628454fe2022f7ad607badf`.
- Apply requires an explicit `user-confirmed-avatar-apply:` reference and an
  authenticated `getMe` bot identity match before any write.
- The operator path records a unique operation ID, safe authorization/audit
  fields, and calls `setMyProfilePhoto` exactly once.
- Exact API `result=true` records `success`. Explicit 4xx rejection records
  `failed`; timeout, transport, HTTP/API 5xx, invalid JSON/response/result, or
  an unknown post-call outcome records `uncertain`.
- The apply path performs no profile-photo readback, `getFile`, download,
  remote digest, visual-provider call, rollback, or automatic retry.
- Wrong catalog, image, avatar, authorization, or bot identity stops before
  the Telegram write.

## Exact Snapshot Evidence

The following checks ran from a clean `git archive` of
`2bbbb3824c856ed5fe199a36fc32c3e814828b33`, not from the shared checkout:

| Check | Result |
| --- | --- |
| `python3 -m compileall -q src tests` | Passed |
| `PYTHONPATH=src:tests uv run python -m unittest discover -s tests -q` | Passed 297 tests in 102.203 seconds |
| `uvx ruff check src tests` | Passed |
| `uvx ruff format --check src tests` | Passed; 103 files already formatted |
| `uv run mypy src/group_llm_agent` | Passed; no issues in 52 source files |
| `sh -n deploy/manage.sh` | Passed |
| `uv build` | Produced wheel and sdist |
| Isolated wheel install | Installed package and Pillow 11.3.0 |
| Installed entry point without `TELEGRAM_BOT_TOKEN` | Safe expected exit code 2 with redacted configuration error |
| Docker Compose render using `.env.example` | Passed; read-only root, no-new-privileges, tmpfs, persistent data volume, VISION/automation/expression disabled by example defaults |
| Tracked snapshot credential/private-key scan | No matches |

Build artifacts from this verification run:

- sdist SHA-256:
  `b6699c6b4948e2e5ae9333ce43e9aed77a93d161dcf0c59741d3dee1d5949c5d`
- wheel SHA-256:
  `52c8f2c76450ce45fdd61216dea5a4e06ba099a542489b5cafaad1f1cfe9d3cc`

Wheel inspection confirmed `effect_bundle.py`, `effect_delivery.py`,
`expression_policy.py`, `writer_contract.py`, the expression catalog, and both
immutable Lezhi v1/v2 persona bundles.

Candidate image `telegram-bot:v031-candidate-2bbbb38` built successfully at
image ID
`sha256:734ba1523ee7a86cfc1f1e8e301a7d67dfc5431122521d9e00e2c4596d1719da`.
Read-only inspection confirmed user `app`, command `group-llm-agent`, Pillow
11.3.0, 48 expression entries, and imports for the new bundle/delivery/policy
modules. A read-only no-credential run returned the expected safe exit code 2.
No running service was replaced or restarted.

## Release Gates And Limitations

- Independent exact-head review and merge are still required. This document
  does not authorize merge.
- Production SQLite backup, immutable-copy `PRAGMA quick_check`, migration,
  Compose replacement, and post-start verification remain post-merge release
  steps; no production database or container was changed during verification.
- The 48 production Telegram mappings were not mutated or re-uploaded. The
  release must prove all 48 remain enabled before and after restart.
- No real Telegram message, sticker, profile-photo write, provider request,
  visual-provider request, or Tavily request was made during this verification.
- After merge and preflight, one user-authorized default-avatar apply is in
  scope. Telegram API success is the system success condition; visible client
  anomalies remain a manual-report path.
- Production must keep VISION disabled, automatic avatar rotation disabled,
  and mood-avatar apply count at zero.
- Real Telegram composite-reply UAT and the user's visual confirmation of the
  default avatar remain final operational acceptance steps.
