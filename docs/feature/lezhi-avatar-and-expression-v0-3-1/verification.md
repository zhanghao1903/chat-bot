# Verification: 乐枝默认头像部署与复合表情回复 v0.3.1

- Status: LLM-owned reply-form implementation verified; exact-head review pending
- Verified at: 2026-08-05
- Safe-forward baseline: `85998708aa9a1d85b33a4477a818339498846868`
- Exact implementation snapshot: `f00b3eb683de2a124f78e675385476da1c54c2b4`
- Confirmed requirements commit: `596a754419bc971ac71436bbb85f408ecc7962f0`
- Confirmed requirements SHA-256: `71e6b25fc970a4a6aa78697369a1a194081102f943138e699ae0a5a642caacc9`
- Accepted handoff: `845408808dafe33c51255982fb5ffff0befa6accd98f803c6f62432bf1aab8dd`

## Revision Boundary

This snapshot implements the user's superseding architecture decision for PR
#8. The Writer LLM is the only semantic owner of `reply`,
`reply_with_sticker`, `sticker`, or `silence`. It receives the complete
bounded conversation, relationship, member-memory, vision, catalog, and tool
context. Application code no longer classifies natural-language content to
decide whether a sticker is appropriate.

The previous keyword-remediation review was cancelled before this
implementation. Its phrase-by-phrase FINDING-002 loop is obsolete under the
confirmed architecture and must not be resumed against an older head.

## Implemented Contracts

### LLM semantic ownership

- `writer_prompt.py` states that the Writer is the sole semantic reply-form
  decision maker.
- The prompt encourages stickers when they naturally add emotion or action to
  a light interaction and directs the model toward text or silence for serious,
  safety, medical, permission, relationship-repair, exclusivity, favoritism,
  or one-member-side content.
- The prompt explicitly forbids choosing a reply form to hit a rate, target,
  quota, or metric.
- The `0.4–0.7` sticker-bearing range remains an offline observation reference
  only.

### Non-semantic application boundary

- `expression_policy.py` contains no natural-language keywords, regular
  expressions, synonym registries, prefix tokenization, vision-label
  semantics, or handcrafted relationship grammar.
- Runtime sticker validation is limited to an enabled catalog and entry,
  structured minimum-relationship metadata, and the consecutive-repeat rule.
- Exact persona/catalog digest, version, semantic ID, Telegram mapping, and
  structured-output validation remain in the existing application boundary.
- An invalid `reply_with_sticker` selection degrades to its already validated
  text. An invalid sticker-only selection degrades to silence.
- Exhausted invalid or unknown Writer structured output degrades to silence on
  every trigger path. Provider transport/runtime failures retain the existing
  direct-failure/contextual-silence behavior.

### No online rate gate

- The `expression-metrics` operator command is removed.
- The seven-day/latest-100 effect-bundle metric and the legacy expression
  usage-rate API are removed.
- Existing database columns remain for additive schema compatibility, but no
  runtime rate, quota, minimum-sample gate, or corrective feedback loop reads
  them.
- Offline evaluation still reports observed counts and ratios. Report pass/fail
  depends only on deterministic catalog, relationship-metadata, and
  consecutive-repeat invariants; semantic case labels and the observed rate do
  not independently fail a report.

### Durable delivery and compatibility

- Text-first component ordering, component claims, sent/failed/uncertain
  outcomes, restart reconciliation, and at-most-once behavior are unchanged.
- The safe-forward merge base is exactly
  `85998708aa9a1d85b33a4477a818339498846868`.
- The implementation changes no expression/avatar asset and no v0.4
  automation, subscription, scheduled-food, Tavily, or migration source file.
- VISION and automatic avatar rotation remain outside this implementation and
  no production setting is changed.

## Deterministic Verification

All commands ran in the owned clean worktree. No external provider, Telegram,
Tavily, deployment, container, SQLite production database, sticker upload, or
avatar operation was invoked.

| Check | Result |
| --- | --- |
| Focused policy/prompt/effector/evaluation/bundle/operator/database suite | Passed 37 tests in 1.205 seconds |
| Full unit discovery | Passed 301 tests in 110.795 seconds |
| `python3 -m compileall -q src tests` | Passed |
| `uvx ruff check src tests` | Passed |
| `uvx ruff format --check src tests` | Passed; 104 files already formatted |
| `uv run --offline mypy src/group_llm_agent` | Passed; no issues in 52 source files |
| `sh -n deploy/manage.sh` | Passed |
| `git diff --check` | Passed |
| `uv build --offline` | Produced wheel and sdist |

Build artifacts:

- sdist SHA-256:
  `e9d960a1563cec274d8c2ac483e9529d7a8261d37b1a5302b28fb085717b6d25`
- wheel SHA-256:
  `9a4909cfdf5ec315157c3d47af84f3fb2bf2d350e1476f1af03b47af05528c9a`

The package build includes the simplified `expression_policy.py`, revised
effector/evaluation/prompt modules, both immutable persona bundles, and all
expression/avatar assets.

## Regression Evidence

- Natural-language invariance tests feed serious, medical, exclusive,
  multilingual, benign, and long repeated text through the policy boundary and
  prove identical non-semantic validation outcomes.
- Policy tests cover disabled catalog/entry rejection, public/familiar/close
  structured relationship ranks, exact outbound sticker markers, and repeat
  rejection.
- End-to-end effector tests prove natural-language and vision strings do not
  override a valid model reply form.
- End-to-end degradation tests prove invalid composite stickers preserve text,
  invalid sticker-only results become silence, and exhausted invalid structured
  output becomes silence even on a direct trigger.
- Offline evaluation tests prove observed rates of `0.0`, `0.375`, `0.4`,
  `0.7`, `0.725`, and `1.0` do not decide pass/fail; semantic case labels are
  observational while relationship metadata and consecutive repeat remain
  deterministic failures.
- Operator and repository tests prove the online metrics command and both rate
  calculation APIs are absent while durable bundle behavior remains green.

## Provider Evidence And Limitations

The historical configured-provider report remains byte-identical at SHA-256
`cc89c4f22cbed02bffe1b510c60b22409aabbda5011b6145b6e77882747ff5d2`.
It is retained for traceability only and does not satisfy the revised
architecture's future provider-evidence gate because it was generated before
this prompt and responsibility-boundary change.

A new provider run requires separate authorization. This implementation and
verification did not consume credentials, transmit any fixed evaluation
content, or call the configured non-official OpenAI-compatible endpoint.

Production remains on the previously deployed snapshot. Deployment, container
replacement, Telegram smoke, expression upload/mapping, SQLite migration,
default-avatar apply, mood-avatar apply, VISION enablement, and automatic
avatar rotation are not authorized or claimed by this verification.

## Review And Merge State

Immutable ReviewResult dispatch
`c8a010d899ef3dc0a491b8c9ca68bbf8d8b85ea71ae90771bb79680566fe5dbb`
approved exact head `83ed3dfd415cc67fcb58cf2b52ecb980a5f55ee4` with no
findings. Its merge status was `NOT_AUTHORIZED` because the request retained
`mergeOnApprove=false`.

On 2026-08-05 the user explicitly requested the release workflow and feature
closure. This authorizes the guarded PR #8 merge and the bounded post-merge
production release described below. The global Feature Lifecycle policy may be
set to `mergeOnApprove=true` only for the new exact-head review and must be
restored to `false` immediately after the merge result is accepted.

This authorization covers:

- guarded squash merge of PR #8 without branch deletion or admin bypass;
- production SQLite backup and `quick_check`, migration 6 through normal
  application startup, immutable-image Compose replacement, and rollback if
  verification fails;
- read-only verification of all 48 enabled mappings, VISION disabled,
  automatic avatar rotation disabled, mood avatars unapplied, v0.4 state, bot
  identity, polling, database integrity, and delivery state;
- bounded Telegram reply-form release verification using operator-visible
  group evidence already supplied during this feature and new messages only if
  necessary to close the release gate.

It does not authorize another provider evaluation, sticker upload or publish,
another default-avatar write, mood-avatar application, automatic avatar
rotation, VISION enablement, destructive database reset, or unrelated
production changes. The already visible default avatar and existing 48
mappings must be preserved rather than re-applied.
