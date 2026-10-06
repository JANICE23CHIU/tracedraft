# Result — proseC, rule-only verifier (pre-registered)

Pre-registration: `docs/PREREGISTRATION_proseC.md` (SHA-256 2bfeaf7e5b048d8b…), evaluator `212371d15bdcc22b`.
Runs (laptop ledger): `20261004T062814Z_verifier_K1_proseC_rule_none`, `20261004T062815Z_verifier_F2_proseC_rule_none`.
Planted-error set: the same mutation kinds as for table / prose / proseB (`tracedraft/evaluate.py`).

| Case | Planted errors | Passed (escaped) | Correct values | Correct → FLAG | Correct → REVIEW |
|---|---:|---:|---:|---:|---:|
| K1 | 358 | 0 | 83 | 9 | 29 |
| F2 | 299 | 0 | 68 | 8 | 21 |

- P1 (no planted error passes): **held**.
- P2 (correct values sent to review rise above prose's 0): held, and the price is large — 38/83 (K1) and 29/68 (F2) correct values are not passed.
- New on proseC, not seen on any earlier style: **false FLAGs** on correct values (9 and 8). Two causes, found after the run:
  1. `ATTRIBUTE_STATEMENT_MISMATCH` — the sentence splitter does not split before a parenthesis
     (`… boils. (Auto shut-off, attribute).`), so the requirement sentence never "ends with" the statement.
  2. `PARTIAL_COPY` — the specification cue `limit` matches "the design limit itself is …", and the clause keeps
     the words "itself is", so an exact copy of the limit looks like a partial copy.
- Per the pre-registration, neither cause is fixed and re-scored on proseC. Fixes go into the next evaluator and are
  tested on a phrasing written by someone other than the verifier author.
