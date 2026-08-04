# Verification: 乐枝默认头像部署与复合表情回复 v0.3.1

- Status: Exact implementation approved; one-time guarded merge review pending
- Verified at: 2026-08-04
- Safe-forward baseline: `88c775c8ef0be7d1c63fd71b5924334b12492d75`
- Exact implementation snapshot: `2bbbb3824c856ed5fe199a36fc32c3e814828b33`
- Exact FINDING-001 remediation snapshot: `ace5be1713b31bbd956cb5af5d1f415578cc8819`
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

## FINDING-001 Remediation Evidence

The first independent review examined carrier
`3785b17d8d2d2e2c4f78d359f504778d32d47985` and found that explicit
Chinese and English safety-incident language could remain sticker-eligible.
Remediation snapshot `ace5be1713b31bbd956cb5af5d1f415578cc8819`
extends the application-owned serious-context classifier with bounded
safety-incident, safety-accident, workplace/industrial-accident, and Chinese
incident/accident terms. The Writer cannot override this classification.

Direct policy regressions prove `发生安全事故了`, `现场出现安全险情`,
`A safety incident happened.`, and `There was a workplace accident.` are all
ineligible for stickers, while a benign light interaction remains eligible.
End-to-end effector regressions prove that, for both the Chinese and English
literal cases:

- a Writer `sticker` result becomes a direct-path failure reply with no
  sticker; and
- a Writer `reply_with_sticker` result becomes the already-validated text-only
  reply with no sticker.

The following checks ran from a clean `git archive` of the exact remediation
snapshot:

| Check | Result |
| --- | --- |
| Focused policy and effector suite | Passed 16 tests in 0.767 seconds |
| Full unit discovery suite | Passed 300 tests in 98.836 seconds |
| `python3 -m compileall -q src tests` | Passed |

The byte-identical implementation tree also passed Ruff check and format
(`103` files), Mypy (`52` source files), `sh -n deploy/manage.sh`,
`git diff --check`, and offline wheel/sdist build. The remediation changed only
`expression_policy.py`, `test_expression_policy.py`, and `test_effector.py`;
v0.4 source paths, expression assets, avatar assets, mappings, deployment
configuration, and production state were not changed.

## Release Gates And Limitations

## Post-Merge Provider-Gate Remediation

Production release validation exposed two real-provider failures after PR #7:

- the first exact 48-case run produced 30/40 sticker-bearing eligible cases
  (`0.75`) and allowed a sticker for relationship guard `V031-048`; the
  minimal report SHA-256 was
  `b6847d375437764132f9e5013300af0204a949bb1eb01d31f320796800cb69ab`;
- the first prompt remediation closed every guard but overcorrected to 14/40
  (`0.35`); the minimal report SHA-256 was
  `c0d58f2590c415b5c7f0c05a956fbdc956aed22300ac807310d2ec0ab72409bd`.

The follow-up narrows the Writer instruction to a 60% midpoint without making
either output form the default. It also adds an application-owned relationship
boundary for exclusive affection, favoritism, and one-member-side requests.
The final user-authorized configured-provider run used `gpt-5.6-sol` and
produced 26/40 sticker-bearing eligible cases (`0.65`). All three
necessary-text cases and all five hard/relationship guard cases returned text
only. The canonical minimal report is
`provider-evaluation-gpt-5.6-sol.json`, SHA-256
`cc89c4f22cbed02bffe1b510c60b22409aabbda5011b6145b6e77882747ff5d2`.

Local verification for the follow-up passed 302 unit tests, 18 focused policy,
prompt, and effector tests, Ruff check/format, targeted Mypy for both changed
runtime modules, compileall, and git diff check. The full-tree Mypy invocation
continues to report the pre-existing Pillow `ImagingCore.__iter__` typing
incompatibility in unchanged `asset_pipeline.py`; neither runtime behavior nor
this follow-up touches that file.

Exact-head review dispatch
`c379534c93dd6d09d60b1cb62f062738dc17f13090b9fe4c0e82886ea5667fec`
found that the first relationship alternation treated bare `支持我` as an
exclusive relationship signal while missing common paraphrases such as
`你只能喜欢我`, `你只许偏爱我`, `只宠我一个`, and `你不许站别人那边`.
The first deterministic remediation replaces the substring match with bounded
Chinese and English exclusivity, favoritism, and side-taking structures. Bare
support, gratitude, `支持我们`, and English `supporting me` statements remain
ordinary sticker-eligible context. The immutable implementation snapshot is
`a9990d1dfee9b75c08a09c2fc23805f4bc859db1`.

Direct policy regressions cover every reviewer reproduction plus bounded
English variants. End-to-end effector regressions prove representative
exclusive contexts reject both sticker-only and text-plus-sticker output,
while benign support and gratitude still allow a validated sticker. The
focused policy, prompt, and effector suite passes 19 tests; the full discovery
suite passes 303 tests. Ruff check/format passes all 104 source/test files,
targeted Mypy passes the changed runtime module, and compileall, shell syntax,
and diff checks pass. No additional provider call was used or required for
this deterministic finding closure.

Re-review dispatch
`1a0dea2a011ab4281d1aada4db6393140b3e36a3b946e51fbea586e4826aebad`
retained FINDING-002 because the first remediation still matched the `我`
prefix inside possessives such as `我的设备`, and it did not distinguish an
exclusive request from a clause explicitly rejecting exclusivity. Final
implementation snapshot `c0f803eeaada81eab6aa354e59f1409e58f1e67e`
requires a complete relationship-object/utterance boundary and treats matched
anti-exclusivity spans as exemptions without hiding a separate exclusive
clause in the same message.

The final regression matrix includes all reviewer examples plus possessive
continuations, family-object continuations, Chinese and English negation,
inclusive corrections, punctuation, and messages that first reject one
exclusive phrase but later make a distinct exclusive request. Direct policy
and end-to-end sticker/composite coverage pass in the 19-test focused suite;
the full suite passes 303 tests in 101.787 seconds. Ruff check/format passes all
104 source/test files, targeted Mypy passes `expression_policy.py`, and
compileall, shell syntax, and diff checks pass. The canonical provider report
remains byte-identical; no external call was made for this deterministic
closure.

Third re-review dispatch
`410df9921f8f74ecc24334c4c0fd2f103291a8b86b4df3282ec44ac757445247`
retained FINDING-002 because implementation snapshot
`c0f803eeaada81eab6aa354e59f1409e58f1e67e` did not yet cover common
exclusive-affection action, negative-other, marker, request-ending, English
word-order, and rhetorical-demand forms. Exact reproductions included
`你只能爱我`, `你不许喜欢别人`, `你不能爱任何其他人`,
`你只可以喜欢我`, `你只能喜欢我好吗`, `你只喜欢我就可以了`,
`You must love only me.`, `You can't love anyone else.`,
`Don't love anyone else.`, `你不是说只能喜欢我吗？`, and
`难道你不应该只喜欢我吗？`.

Remediation snapshot `b949d1a5c92a4167838deade99cc29e238d722da`
completes the bounded application-owned relationship grammar. It adds the
missing `爱`/`love` and negative-other actions, natural Chinese exclusivity
markers and request endings, English action-only and negative-other word
orders, and rhetorical-demand handling. Exemptions cover complete
anti-exclusivity spans only; they do not hide an independent positive demand.
The same object boundary continues to reject possessive-prefix false matches
such as `我的设备`, while explicit inclusive corrections in Chinese and
English remain sticker-eligible.

Direct policy and end-to-end effector regressions cover all three prior review
matrices plus additional complete-object, imperative, modal, rhetorical,
anti-exclusivity, and multi-span cases. Both Writer `sticker` and
`reply_with_sticker` decisions are rejected for relationship contexts, while
validated stickers remain possible for benign support, gratitude, possessive,
and anti-exclusivity messages. The focused policy/prompt/effector suite passes
19 tests and the full suite passes 303 tests in 103.165 seconds. Ruff
check/format passes all 104 source/test files, targeted Mypy passes
`expression_policy.py`, and compileall, shell syntax, and diff checks pass.
The canonical configured-provider report remains byte-identical at SHA-256
`cc89c4f22cbed02bffe1b510c60b22409aabbda5011b6145b6e77882747ff5d2`;
no additional provider call, deployment, container replacement, Telegram,
Tavily, SQLite, sticker, or avatar operation occurred.

Fourth re-review dispatch
`7f85c1a242efb1889eb58029ddc6ebde7c29c697c2510744819fba93dc748f60`
retained FINDING-002 because the prior exact head still omitted the canonical
modal/prohibitor-before-addressee order and lacked an English direct-subject
boundary. Exact misses included `只许你喜欢我`, `不许你喜欢别人`,
allow/necessity variants, single-member interaction variants, and their
English equivalents; the neutral technical sentence
`This app can only support me.` was also incorrectly classified as a
relationship context. A nested anti-exclusivity quotation remained a false
positive.

Implementation snapshot `6adef03fa8766058bc6a74e33a7698d97408fa79`
represents both Chinese subject placements, extends bounded allow/necessity,
interaction, and negative-other forms, and requires each positive English
match to have an application-owned direct relationship subject. A complete
Chinese object boundary and scoped anti-exclusivity overlap remain mandatory.
This closes the exact reviewer cases without treating app, device, family, or
other non-person technical subjects as relationship demands.

The expanded direct and end-to-end matrix covers `sticker` and
`reply_with_sticker` outcomes for every prior review example plus
modal-before-addressee, allow/necessity, rhetorical, nested quotation,
technical-subject, possessive, anti-exclusivity, and multi-span cases. The
focused policy/prompt/effector suite passes 19 tests; the full discovery suite
passes 303 tests in 97.230 seconds. Ruff check/format passes all 104
source/test files, targeted Mypy passes `expression_policy.py`, and compileall,
shell syntax, and diff checks pass. The provider report remains byte-identical
at SHA-256
`cc89c4f22cbed02bffe1b510c60b22409aabbda5011b6145b6e77882747ff5d2`.
No provider, deployment, container, Telegram, Tavily, SQLite, sticker, or
avatar operation occurred.

Fifth re-review dispatch
`791c204683e0a4bd40655c9cb59167a8f74445696bdba5fa9e4440454066a104`
retained FINDING-002 because direct modal-before-addressee questions,
Chinese ability/permission/intent questions, persona-name addressees between
the modal and action, and explicit-speaker rhetorical demands still bypassed
the previous exact head. The exact matrix also showed these forms cross both
the sticker-only and composite final-effect boundary.

Implementation snapshot `52a14feba1ba3056a402336e61af044211f8aed3`
adds bounded question-subject structures for English modal + `you`/`Lezhi`,
Chinese ability/permission/intent + `你`/`乐枝`, persona-name placement after
the Chinese modal/prohibitor, and explicit-speaker rhetorical demands. The
same direct-subject check rejects technical modal questions whose subject is
an app, device, or other non-person object. Nested anti-exclusivity quotation,
possessive, inclusive-correction, and multi-span exemptions remain scoped.

Direct and end-to-end regressions cover every exact reviewer reproduction,
both final Writer sticker forms, previous matrices, and extra wh-question and
technical-question variants. The focused policy/prompt/effector suite passes
19 tests; the full discovery suite passes 303 tests in 99.686 seconds. Ruff
check/format passes all 104 source/test files, targeted Mypy passes
`expression_policy.py`, and compileall, shell syntax, and diff checks pass.
The configured-provider report is unchanged at SHA-256
`cc89c4f22cbed02bffe1b510c60b22409aabbda5011b6145b6e77882747ff5d2`.
No provider call or production/external operation occurred.

Sixth re-review dispatch
`0eec11650c05d29ba47656dde4f10f671419d02e47f823df861b920e76c4e7ca`
retained FINDING-002 because otherwise-direct relationship requests with
bounded temporal, degree, or politeness modifiers were excluded by exact
prefix matching. The exact reproductions covered Chinese `只会`,
`以后`/`今后`/`永远`, and English `always`/`forever`/`please`/`really`
forms for both the direct persona and formal name.

Implementation snapshot `db50acbe4252b93ec6abda80826f81fb80e5a3e2`
models bounded modifier sequences inside the direct-subject grammar rather
than enumerating whole utterances. Modifiers are accepted only after an
application-owned `你`/`乐枝` or `you`/`Lezhi` direct subject, a recognized
question structure, or a bounded explicit request. Technical and third-party
subjects remain ineligible for relationship classification. Chinese `只会`
and English post-`only` modifiers are handled in the exclusivity grammar.

The regression matrix covers every exact reproduction through direct policy,
Writer `sticker`, and Writer `reply_with_sticker` validation, plus technical
subjects carrying the same modifiers. The focused suite passes 19 tests; the
full discovery suite passes 303 tests in 98.945 seconds. Ruff check/format
passes all 104 source/test files, targeted Mypy passes
`expression_policy.py`, and compileall, shell syntax, and diff checks pass.
The provider report remains byte-identical at SHA-256
`cc89c4f22cbed02bffe1b510c60b22409aabbda5011b6145b6e77882747ff5d2`;
no provider or production/external operation occurred.

Seventh re-review dispatch
`1de1562b4c65cb2c4c3e67bb3dcd8eada20ef27baa8eb16780db88ec48a5a7f3`
retained FINDING-002 because temporal, politeness, and degree modifiers placed
before the direct subject or implicit imperative still bypassed the exact
prefix allowlists. The reproduced forms included Chinese `以后你`,
`请永远`, `拜托你`, and English `Please always`, `From now on you`,
`kindly`, `maybe`, and `just` orders; both Writer sticker forms retained the
selected sticker on the prior exact head.

Implementation snapshot `3442e72c8e43f98f25aa7a9ff031db8f5c557fde`
replaces those positional allowlists with bounded application-owned prefix
grammars. Only recognized temporal, request, degree, modal, question, and
direct `你`/`乐枝` or `you`/`Lezhi` tokens can surround the relationship
action; any unknown app, device, service, third-party, or other technical
subject makes the direct-subject check fail. Bounded modifier-only prefixes
remain valid implicit requests, so fronted natural imperatives are covered
without accepting arbitrary provider-authored semantics.

Direct policy regressions cover every exact seventh-review reproduction and
technical/third-party counterexamples. End-to-end effector regressions prove
representative Chinese and English messages reject both Writer `sticker` and
`reply_with_sticker`, while the same modifier orders attached to app/device
subjects remain sticker-eligible. The focused policy/prompt/effector suite
passes 19 tests in 5.726 seconds; full discovery passes 303 tests in 104.367
seconds. Ruff check/format passes all 104 source/test files, targeted Mypy
passes `expression_policy.py`, and compileall, shell syntax, and diff checks
pass. The configured-provider report remains byte-identical at SHA-256
`cc89c4f22cbed02bffe1b510c60b22409aabbda5011b6145b6e77882747ff5d2`;
no provider, deployment, container, Telegram, Tavily, SQLite, sticker, or
avatar operation occurred.

Eighth re-review dispatch
`c321f37af41e76680f85e531667f08d13b637284a86b8181bbff82e71eaf36c1`
retained FINDING-002 for Chinese exclusivity modals separated from `只` by a
temporal modifier and English `possibly`/`at least` variants. It also opened
FINDING-003 because the previous English prefix regex allowed overlapping
`need to` versus `need` + `to` parses inside nested repetitions, causing
exponential backtracking on short member-controlled input.

Implementation snapshot `2b7131dadd142bb957348ffc39faad6e794984fe`
adds the exact bounded Chinese and English modifier families while replacing
the ambiguous direct-prefix regex with deterministic longest-token
consumption. The parser advances monotonically through a closed token
registry and stops immediately on an unknown technical or third-party token;
it has no recursive or alternative backtracking path. The same deterministic
parser is used for Chinese prefix recognition to avoid an equivalent induced
risk there.

Direct policy and end-to-end regressions cover all eighth-review semantic
reproductions for Writer `sticker` and `reply_with_sticker`, while equivalent
app/service subjects remain eligible. An adversarial regression classifies 64
repeated `need to` prefixes plus an unknown token under 0.25 seconds; an
independent 2,062-character/256-repeat probe completed in about 0.004 seconds.
The focused suite passes 20 tests in 7.166 seconds and final full discovery
passes 304 tests in 106.060 seconds. Ruff check/format passes all 104
source/test files, targeted Mypy passes `expression_policy.py`, and
compileall, shell syntax, and diff checks pass. The provider report remains
byte-identical at SHA-256
`cc89c4f22cbed02bffe1b510c60b22409aabbda5011b6145b6e77882747ff5d2`;
no provider or production/external operation occurred.

- Independent exact-head merge review is still required.
- On 2026-08-04, the user explicitly authorized the Feature Lifecycle global
  `mergeOnApprove` policy to be set to `true` temporarily, only to re-review
  and squash merge PR #7. The merge review must require the exact head, use no
  admin or auto merge, preserve the feature branch, and return immutable merge
  traceability.
- Main must restore the global `mergeOnApprove` policy to `false` immediately
  after accepting the merged ReviewResult. The temporary authorization does
  not permit deployment, Compose/container changes, SQLite migration,
  expression or avatar operations, Telegram messages, or provider/Tavily
  calls.
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
