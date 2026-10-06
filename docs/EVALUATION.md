# Evaluation protocol (fixed before any model run)

This protocol was written on 2026-10-04, before any language-model run. Every number reported in the
proposal must come from a sealed run folder, which contains `config.json`, `records.jsonl`, `metrics.json`
and `MANIFEST.sha256`, and must also appear as an entry in `runs/LEDGER.jsonl`.

## Primary metric

**P̂ — task correct completion rate.** A task is one field of one protocol row. It counts as correct only when
the value is correct **and** the cited segment is the gold source:

- same document and revision;
- names the same test.

A gold-MISSING task is correct only if the system also reports MISSING. Every planned task is in the
denominator, including errors, timeouts and pending relays.

## Diagnostics (never promoted to primary after the fact)

value accuracy, citation accuracy, per-field accuracy, rows with all fields correct, conflicts reported,
evidence tokens per field, status counts, wall time and Ollama `prompt_eval_count` / `eval_count`.

## Experiment 1 — evidence selection

The selector is the only change between arms. Both arms use the same eligible set, the same RRF ranking
(κ = 60), the same budget B = 2048 − 520 − 160 = 1368 estimated tokens, the same model, prompt, seed and
`temperature = 0`.

- Baseline: top-k in RRF order, filling B.
- Candidate: FCEA coverage selection.

Cases K1 and F2 are reported separately. Each case has prose and table sources.

## Experiment 2 — citation verifier

Injection set: `evaluate.mutations` (seed 20261004). It contains the correct claims plus these error
kinds:

- wrong row;
- superseded revision;
- informative section;
- digit change;
- comparator flip;
- unit swap;
- negation;
- other condition's n;
- invented value where the source says TBD.

Report recall and false-alarm rate for three verifiers:

- rules only;
- model only (`--llm-mode all`);
- combined (`--llm-mode review`).

## Keep / discard

A change is **kept** only if:

- its P̂ beats the current best on the development case,
- with no hard-constraint violation, i.e. no cited segment outside the eligible set.

Otherwise it is **discarded**. Both outcomes are appended to the ledger. Development uses K1. F2 is the
held-out case and is run once per locked configuration. Scores after repeated selection on K1 are
development scores, not unbiased estimates.

## Known limits

- n = 2 synthetic cases.
- Field tasks within a row are not independent, so treat any confidence interval as optimistic.
- The laptop GPU is not the accelerator. UGen300 measurements (latency per field, end-to-end time,
  host CPU) are Stage II.
