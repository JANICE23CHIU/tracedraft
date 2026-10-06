# Pre-registration — held-out phrasing proseC

Written 2026-10-04T06:26:56Z, BEFORE any verifier or model run on proseC.

## Why a second held-out set
proseB was the held-out phrasing for prompt v1–v3. After its results were seen, a verifier rule was added
(UNANCHORED_HIGH_RISK: on a high-risk field, a value that is merely contained in a segment without that field's
cue goes to review instead of passing). proseB can no longer test that rule. proseC was written after the rule and
before any run on it.

## Frozen inputs
Evaluator id at registration: `212371d15bdcc22b` (SHA-256 of verify.py, policy_opt.py, ratchet.py, contract; first 16 hex).

```
998dd3ba719027a87f60d0cfae978e9d4ef5d4b6a83a14fe289772e187a77517  data/synthetic/cases/F2/sources_proseC/PRS-OF2-001_revB.md
b2e6a957edab585994a34b206d17e6d17735eec4b7628d7463875e799f8194c5  data/synthetic/cases/F2/sources_proseC/PRS-OF2-001_revC.md
c59f2ed0ab2acd27f9a889510adc00e180b1b09bb8b45a63820b9348ced21839  data/synthetic/cases/F2/sources_proseC/TMX-OF2-002_revA.md
1a0a2fa042cabb9398ae0ac3f136cb8d7d8633c7e4d5ac23c9fecb8d3aacb94a  data/synthetic/cases/F2/sources_proseC/VP-OF2-003_revB.md
fb95a83b2ac901cb4772b9a12d1332e6240c4ffba4e0091a789c959d94dc25d8  data/synthetic/cases/K1/sources_proseC/PRS-NK1-001_revA.md
e48a935f8a05e626dac4b61aa43e46597821b79acb2bdbaa488180839c7f1556  data/synthetic/cases/K1/sources_proseC/PRS-NK1-001_revB.md
6540a2ae97a8682316d9ab8379cb176824ecf1d2b7312c1f97363e72630bc199  data/synthetic/cases/K1/sources_proseC/TMX-NK1-002_revA.md
046f9845fdb250ba3e30b62057968ebb6dc21a403d28f434f0416e26cc07fc3d  data/synthetic/cases/K1/sources_proseC/VP-NK1-003_revA.md
052d1fd1f8051e2296a5d3b952ac8e678882f324b981ba0de5837186f75eb806  data/synthetic/cases/F2/manifest_proseC.json
65ad634c607bddc74acdc262a05b2c877e26610ec3b8bc144cd48d2ed02ac855  data/synthetic/cases/K1/manifest_proseC.json
39f52b7c6fe495bf1e91c4ef687990f6144ff375892d45c3cf589c2392a1b912  data/synthetic/generate.py
0f0b4f137d5c0bb3f5037c7b2efa8f44ed502eabe91171bb1b9c5a153d628c39  tracedraft/verify.py
58cd481338baaf7cca438fa78ebca09da0b070b1a0f02a573163271ead5c9d0b  tracedraft/ratchet.py
c418312eafddf3d956a256b43ae69ab5d55502f138e302defe57bc1a2af8e11c  tracedraft/policy_opt.py
7dd9704f8481dedf2e69e8b41d56d9c88cfc0ff5cef34a0fe691925dff8b29fe  contracts/test_protocol_v1.json
```

## Predictions (stated before running)
P1. Rule-only verifier (`verifier-eval --adapter rule --llm-mode none`): planted errors that PASS = 0 on K1 and F2.
P2. Correct values sent to review (not PASS) on proseC: more than on prose (0) — the price of the rule; recorded, not tuned.
P3. Model runs (qwen2.5:1.5b, prompt v2, FCEA): U/N = 0 under ε = 0 on both cases.
P4. E/N on proseC is within ±0.10 of E/N on prose for prompt v2 (K1 0.24, F2 0.22, R = 3 means).

## Rules
- No change to the contract cues, verifier, or prompts may be motivated by proseC results and then re-scored on proseC.
- Whatever the outcome, the first proseC numbers are reported as the held-out result.
- A third phrasing written by someone other than the verifier author would be a stronger test; recommended before any external claim of generalisation.

## Addendum 1 (2026-10-04, written after the proseC model runs)
The proseC model runs (`20261004T063448Z` … `20261004T064130Z`) and their ratchet decisions were made with the
registered code, evaluator `212371d15bdcc22b`. P3 and P4 are therefore scored under the registered evaluator.
Afterwards the evaluator id changed to `7b1a4cfef752429b` for reasons outside verification:
`tracedraft/verify.py` and `contracts/test_protocol_v1.json` keep the hashes listed above. The changes are in
`policy_opt.py` (configuration key now includes context length and dense ranker; embedding time is spread over
fields) and `ratchet.py` (docstring only).

## Outcome (scored under 212371d15bdcc22b)
| Prediction | Result | Verdict |
|---|---|---|
| P1 rule layer lets 0 planted errors pass | K1 0 / 358, F2 0 / 299 | held |
| P2 correct values not passed > prose's 0 | K1 38 / 83 (9 FLAG, 29 REVIEW), F2 29 / 68 (8 FLAG, 21 REVIEW) | held; the cost is large |
| P3 U/N = 0 for prompt v2 | K1 0, F2 0 (R = 3) | held |
| P4 E/N within ±0.10 of prose (K1 0.24, F2 0.22) | K1 0.306 (26/85 in all 3 runs), F2 0.243 (17/70 in all 3 runs) | held |

Not predicted, reported: human work H/N on proseC is 0.59 (K1) and 0.56 (F2), against 0.26 and 0.25 on prose.
The 1.5B model used as a second-layer verifier wrongly objects to about 30 % of the correct items it is shown
(`verifier_*_proseC_ollama_review`), so the rule layer stays first.
