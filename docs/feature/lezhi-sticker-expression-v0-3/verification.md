# 乐枝图片理解、专属表情与动态头像 v0.3 — 验证记录

## 1. Immutable scope

- Requirements handoff: `42a2438556f8ae245d13c13b0452e1f5364ec3755cb950a1ba89c044f4821311`
- Confirmed requirements commit: `b97b5655248c1247cb8ab1b87c1dc5f45381f2f3`
- Confirmed requirements SHA-256: `a79efaeeadc8eac5f7ac88ed9f60daf00584979b5883aa40749c15cfc983cc0d`
- Baseline persona-v2 squash commit: `ffdcee9a7e410a9fcad226dca99e52d349cfe54e`
- Asset generation commit: `cb90237d9c9b03b475efef5ee5c9e3d8474aa4f7`
- Runtime implementation commit: `48d5e88d3c80ef9e1189a996525704bf5696c73c`
- First reviewed carrier: `5d07a566874579c041fb19a6b7dbf3b914deed80`
- Review dispatch: `b7f08ace016ce9c405d1ece3a5dec43beafce62650adcf422b0bb68e59699aff`
- Review remediation implementation: `434b400a8f4bc464ecf823b093744bea467c778c`

## 2. Candidate artifact identity

- Candidate manifest SHA-256: `1dd20aeca66a5f6cc0cc6ac5f952593abc418cd9b8fab60ce140239fb2224e5b`
- Candidate expression catalog SHA-256: `bd85f2a6ead7943d2504d3e5203ddb54e35aa3e91446b8f5743c9ba28372f3cd`
- Candidate avatar catalog SHA-256: `abd8aa18ab295cb261d7610daabf6650e82de8c5640855c51755de0d5c25f4ea`
- Fixed expression evaluation set SHA-256: `732a2be3863e588f783a3e7daf43d8e9218c0c5c2b6db27b28f1326080dd9016`
- Candidate count: 48 masters, 48 Telegram-ready WebP candidates, 48 light previews,
  48 dark previews, four contact sheets, five avatar crops.
- Every catalog entry remains `candidate`; the production runtime rejects this status.

## 3. Implemented contracts

- Telegram photo, supported static document and static sticker normalization preserves bounded
  media metadata without persisting Telegram download identities.
- Trigger eligibility is decided before media download or vision invocation; unaddressed media
  stays silent and costs no vision call.
- Known enabled Lezhi stickers resolve through the immutable catalog without download or vision.
- Unknown eligible media uses bounded download, Pillow verification/normalization and an
  OpenAI-compatible multimodal JSON contract. Pixels, OCR, caption and scene remain separate,
  untrusted evidence sources.
- Application-owned final validation rejects person identity, sensitive/hidden person attributes,
  medical inference, unsafe asset identity, stale persona/catalog snapshots, serious sticker-only
  choices in either text or validated visual evidence, relationship overreach and consecutive
  duplicate stickers.
- Writer supports exactly one final text reply, one allowlisted sticker or silence. Read-only tool
  attempts use the confirmed 0/3/5 accounting with a hard five-call stop.
- Telegram sticker delivery owns one external-effect claim. Confirmed failure permits at most one
  text fallback; uncertain delivery never produces a second visible effect.
- Operator-only publish, attach, enable and avatar commands are signal-safe, digest-bound and never
  exposed as Writer tools. Catalog approval, Telegram smoke, production enable, avatar approval and
  automatic rotation remain distinct gates.
- Avatar application requires the exact approved default-image baseline before any mood image,
  downloads the post-write Telegram profile photo and compares its SHA-256, and rejects stale,
  mismatched or unknown readback. Rotation requires consistent bot-wide scope plus at least two
  chats and two members; the current single-chat deployment is therefore fail-closed.
- `external_effects` supports aggregate-only expression observability: visible effect count,
  sticker request/success, consecutive repetition and degradation rate without message bodies.

## 4. Deterministic verification

Exact remediation implementation source at
`434b400a8f4bc464ecf823b093744bea467c778c` passed:

- `python3 -m compileall -q src tests`
- `PYTHONPATH=src:tests .venv/bin/python -m unittest discover -s tests -v` — 219 tests
- `uvx ruff format --check src tests` — 79 files already formatted
- `uvx ruff check src tests` — passed
- `mypy src/group_llm_agent --config-file pyproject.toml` — no issues in 40 source files
- `sh -n deploy/manage.sh` — passed
- `TELEGRAM_BOT_ENV_FILE=.env.example docker compose -f deploy/compose.yaml config` — passed
- `git diff --check` — passed
- tracked-file private-key, Telegram token and common model-key pattern scan — no match

Targeted proofs include:

- two clean asset builds are byte-identical and match all four locked sources;
- all candidates reopen as transparent 512×512 PNG/WebP and preserve distinct duplicate-label
  semantics;
- unsupported, oversized, damaged, MIME-mismatched and excessive-pixel media fail closed;
- image prompt injection remains untrusted data;
- political, religious, medication and generic person inferences fail closed while direct visible
  person observations remain available;
- model/raw Telegram IDs, unknown or disabled semantic IDs, stale catalog/persona identity,
  insufficient relationship and immediate sticker repetition never send;
- fixed evaluation has 10 eligible light cases and 10 must-text cases; only 50%–70% sticker-only,
  100% must-text replies, no consecutive repeated sticker and approved catalog identities pass;
- all success, confirmed failure, uncertain failure and replay boundaries preserve one external
  effect;
- signal interruption retains the operator lock until a non-success terminal state.

Review finding closure proofs:

- **FINDING-001 fixed:** after profile write, the controller resolves the returned Telegram
  `file_id`, downloads the readback under the 8 MB bound and compares its SHA-256 with the approved
  candidate. Exact stale/unchanged and mismatched readbacks record `failed`, attempt rollback and
  never record `verified`.
- **FINDING-002 fixed:** an empty audit state rejects direct operator application of
  `lezhi-joyful` before any upload. The exact default content digest must first have a verified audit
  under the catalog version; only then can a mood candidate proceed. Rotation uses the same guard.
- **FINDING-003 fixed:** migration 4 stores chat and member provenance plus the required explicit
  bot scope count. Single-member, single-group and scope-count-one matrices all return ineligible;
  only consistent evidence spanning two chats and two members can become a candidate.
- **FINDING-004 fixed:** benign caption plus visual evidence describing a bleeding wound,
  medication and `injury`/`medical` flags degrades the scripted sticker decision to a textual direct
  failure (`sticker_necessary_text_required`); no sticker identity reaches the final effect.

## 5. Build and container proof

- Wheel: `group_llm_agent-0.1.0-py3-none-any.whl`, SHA-256
  `98c0f48bf8b3e68da23956875c41c5b571e2a521621eb795b2079e7cee5e93ca`
- Source distribution: `group_llm_agent-0.1.0.tar.gz`, SHA-256
  `dbb0ac3e49d44221ff5b6385b8f5c5eec9408dfda409d7096ba6ce2056516d6f`
- Candidate image: `group-llm-agent:lezhi-sticker-v0.3-remediation`, image ID
  `sha256:fa33248c26e12110c4629bc8e41aaa45a3e8896958774e612c36a5f15babd2e0`
- Image configuration uses user `app` and command `group-llm-agent`.
- A read-only one-shot image run loaded exactly 48 candidate catalog entries and 20 fixed
  evaluation cases at the digests in section 2.

## 6. Deliberately pending gates

| Gate | State | Required next evidence |
| --- | --- | --- |
| 48 split previews and full semantic catalog | **PENDING USER CONFIRMATION** | User approves all entries or names rejected semantic IDs after reviewing `candidate-review.md`. |
| Production subset and Telegram mapping | **BLOCKED BY PREVIEW GATE** | Upload only approved entries, perform real static-sticker display/readback smoke, then confirm the production subset. |
| Expression runtime enable | **DISABLED** | Exact `telegram_ready` catalog digest plus explicit `user-confirmed-enable:` reference. |
| Avatar crops and mood mapping | **PENDING USER CONFIRMATION** | User approves default crop and optional mood crops/mappings. |
| Default avatar write | **NOT ATTEMPTED** | Separate approved-avatar command plus Telegram readback. |
| Automatic avatar rotation | **OFF** | Separate confirmation after an approved mood set; 72-hour and rolling-seven-day limits remain enforced. |
| Real visual-provider image probe | **NOT RUN** | Local safety review requires explicit authorization to transmit a project candidate image to the configured non-official compatible endpoint. |
| Real Telegram group UAT | **NOT RUN** | Requires the approved assets/mapping and operator-owned group messages. |

No production Telegram upload, sticker-set creation, catalog enable, profile-photo write, automatic
rotation, Compose restart or running-container replacement was performed in this implementation
phase. These omissions are confirmation and operational gates, not claims of completed external
verification.
