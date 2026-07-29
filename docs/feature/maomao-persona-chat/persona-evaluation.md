# 乐枝生产人格评测载体

Status: STATIC BUNDLE CONFORMANCE PASSED; PROVIDER BEHAVIORAL GATE PENDING

## 1. Evaluated Candidate

- Persona: `lezhi`
- Version: `lezhi-v1.0`
- Production bundle:
  `src/group_llm_agent/persona_bundles/lezhi/lezhi-v1.0`
- Confirmed requirements commit:
  `c5ea34553e52505ff50ee421cc08efff297df01f`
- Confirmed Character Bible commit:
  `3dd1f8b56c9e7e4d4bda9f8c75450570a2902126`
- Confirmed Character Bible SHA-256:
  `46eb6a18323b5549e7a0b3dbc30f3d56e902356d52bb86ba294d0ae5f9542f68`

This carrier deliberately separates deterministic bundle conformance from the behavior of an
operator-selected model. It does not claim that provider output was generated or scored when no
model, credential, endpoint and execution authorization were supplied.

## 2. Deterministic Bundle Conformance

The production bundle passes the following locally reproducible checks:

| Proof | Result |
| --- | --- |
| Manifest is canonical, complete and tied to the confirmed requirements and Character Bible | PASS |
| Manifest content digest covers the manifest metadata, character, examples and evaluation cases | PASS |
| Trigger, Recognition and Effector compile from one immutable persona snapshot | PASS |
| Character data contains every required three-view source field | PASS |
| Fifteen confirmed original examples are present | PASS |
| `CB-EVAL-001` through `CB-EVAL-022` are present exactly once | PASS |
| Every case carries the confirmed `8/10` pass threshold | PASS |
| Critical cases and prohibitions are represented in the evaluation data | PASS |
| Examples reference only cases present in the fixed evaluation set | PASS |
| Known researched frameworks or protected-character identities are absent from production content | PASS |

The deterministic proof is implemented by
`tests/test_production_persona.py` and the generic bundle validation tests. It proves that the
confirmed authoring contract is complete, immutable, packageable and compiled consistently. The
user-confirmed Character Bible remains the product evidence for `AC-BIBLE-001` through
`AC-BIBLE-009`.

## 3. Provider Behavioral Gate

Before enabling `persona_direct` or `persona_contextual` in a real group, the operator must run
the exact production bundle with the selected model against all 22 fixed cases. Each candidate
reply or auditable silence decision must be scored on the confirmed five dimensions:

1. Original character fidelity
2. Voice consistency
3. Member understanding and continuity
4. Engagement and restraint
5. Factual, memory and safety integrity

Activation passes only when every case scores at least `8/10` and every critical prohibition
scores zero. `CB-EVAL-004` and `CB-EVAL-015` may pass through a correct, auditable silence
decision. A model, model version, base URL, sampling configuration, run timestamp, per-case
outputs, scores and reviewer identity must be recorded for that run.

Current provider behavioral result: **NOT RUN**.

Reason: no operator-selected production model execution and no authorization to consume an
external model service were part of this repository verification. This is an explicit rollout
gate and must not be replaced by scripted-model unit tests or by copying the authored examples.

## 4. Rollout Consequence

- `fixed` remains the default and rollback mode.
- The production bundle may be packaged and selected explicitly by path, digest and version.
- Real-group persona activation remains conditional on the provider behavioral gate above and
  the authorized Telegram smoke described in `verification.md`.
