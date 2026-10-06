# TraceDraft

**A local-LLM harness for document data: every field cited, every citation checked, on the hardware you already have.**

TraceDraft turns a set of approved source documents into structured records. Each value carries the exact
source passage it came from, and a verifier checks that passage before anyone sees the value. The same records
are then written two ways: into a fixed Word template, or as a browsable image-text menu (one card per item).

The core idea is the **harness**, not the model. A small local model, specialised helper models and plain rules
are routed per field by an operations-research optimiser. The result is accurate enough on a low-spec laptop,
and the same harness runs unchanged on larger machines or an edge accelerator. Only the routing policy changes.

```
sources ─► hybrid index (SQLite) ─► field-contract evidence assembly ─► extract ─► verify ─► review queue
           BM25 + trigram            FCEA: only eligible evidence,       local       rules first;     │
           + small embedding model   fixed token budget                  LLM         model only for   ├─► .docx draft
           (RRF fusion)                                                              what rules can't  └─► image-text menu
                                    ▲                                                decide
                                    └── routing policy per field (rules / small model / larger model / embedding on-off)
                                        chosen by exact Pareto optimisation + a hypervolume ratchet over measured runs
```

> Status: Stage I entry for the ASUS UGen AI League (Battlefield Lightning × Creator AI).
> All model numbers below are measured on one low-spec laptop with Ollama. Numbers for other hardware,
> the ASUS UGen300 included, are **not measured** unless a run folder says otherwise.

## Why

The hardest error to catch in a generated document is not a blank field: blanks are easy to see. It is a
**filled field whose citation points to the wrong place**. The field looks complete and nobody is prompted to
check it. Confidential engineering documents often cannot be sent to a cloud model at all.

## How

* **Field contract** (`contracts/test_protocol_v1.json`): maintained by people, never edited by a model. For
  each field it names the source role, column, authority order, missing-value markers, cue words and fixed rules.
* **Eligibility is a hard filter**: superseded revisions and informative sections can never be cited.
* **Hybrid index**: three rankings fused with RRF (κ = 60). BM25 (FTS5) for exact terms, character trigrams for
  spelling and unit variants, and an optional small embedding model (`--dense nomic-embed-text`) for meaning.
* **FCEA (field-contract evidence assembly)**: for each field, take the best-ranked eligible segment covering
  each requirement unit, within a token budget derived from the context window.
* **Verifier**: the rules run first, and the model only sees what the rules cannot decide. On high-risk fields
  the model can escalate an item but never clear it. A value that cannot be anchored to its field's own clause
  goes to a person.
* **Routing optimiser** (`optimize`, `ratchet`): every run is a measured point. Objectives are wrong values,
  human work and model time; the hard constraint is zero wrong values let through. The optimiser picks the
  configuration per field. A change is kept only when it raises the hypervolume by more than the measured
  replicate noise, and only under the same SHA-256-locked evaluator.
* **Evidence discipline**: run folders are create-only, `runs/LEDGER.jsonl` is append-only, every run is sealed
  with a SHA-256 manifest, and held-out tests are pre-registered (`docs/PREREGISTRATION_proseC.md`).

## Quick start

```bash
python -m tracedraft demo                          # no model needed
python -m unittest discover -s tests -v            # stdlib only
# with Ollama:
python -m tracedraft run --case K1 --style prose --selector fcea --adapter ollama --model qwen2.5:1.5b --prompt v2
python -m tracedraft menu --run runs/<run folder>       # image-text menu (self-contained HTML)
python -m tracedraft build-docx --run runs/<run folder> # Word draft (needs python-docx)
python -m tracedraft optimize --case K1 --style prose   # per-field routing front
python -m tracedraft ratchet --case K1 --style prose --min-gain 0.10
```

Windows: `scripts/RUN_ROUND3.bat` (pre-registered held-out phrasing) and `scripts/RUN_LADDER.bat`. The ladder
runs the same harness with 0.5B / 1.5B / 7B models, an 8k context and the embedding ranker on your machine.
Every run records CPU, RAM, GPU and how much of the model sat in VRAM. Running the ladder on another machine
is how the hardware comparison is meant to grow.

## Results so far (measured, one laptop, qwen2.5:1.5b unless noted)

| What | Result |
|---|---|
| Evidence per field | FCEA ≈ 230 prompt tokens vs top-k ≈ 1,550 (Ollama counts) |
| P̂ (value and citation correct), prose, prompt v2, R = 3 | K1 0.76, F2 0.78 (top-k with prompt v1: 0.21 / 0.27) |
| Wrong values let through by the verifier | 0 on prose (R = 3); on the held-out phrasing proseB, 3 escaped before the anchoring rule existed |
| Planted-error test, rule layer, pre-registered phrasing proseC | 0 of 358 / 299 planted errors passed; but 9 / 8 correct values were wrongly flagged (reported, not tuned away) |

Details, including the failures, are in `docs/`.

## Limits (read before quoting anything)

* Synthetic data only: two fictional products, four phrasings. The held-out phrasings were written by the
  verifier's author, so they are a weaker test than text written by someone else.
* Ollama at temperature 0 with a fixed seed is not fully reproducible: two identical runs agreed on 62 of 70 fields.
* No numbers for other hardware or for the UGen300 unless a run folder from that machine exists.
* Markdown sources only; PDF and scan ingestion are not in this version.

## License

Code: MIT (`LICENSE`). Benchmark data and Word template: CC BY 4.0 (`DATA_LICENSE`).
Models are not distributed. Qwen2.5 0.5B / 1.5B / 7B / 14B Instruct and nomic-embed-text v1.5 are Apache-2.0.
Qwen2.5-3B is deliberately not used because it is under the Qwen Research License.
