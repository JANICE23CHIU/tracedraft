"""Policy optimiser — choose, per field type, which route/configuration to use.

This is the optimisation layer: the policy file is the mutable surface it writes.

Decision variable
    x_f ∈ X  for every field type f (req_id, specification, n, acceptance, test_instruction).
    X is the set of measured configurations: (adapter/route, model, selector, prompt variant, verify mode,
    context length, dense ranker). Mixing models across fields is how the policy routes work between a
    main local model, smaller specialised models and plain rules.

Objectives (all minimised, task-weighted by n_f, so they add up over fields)
    E(x) = Σ_f n_f · e_f(x_f)        expected wrong field values           (1 − P̂ per field)
    L(x) = Σ_f n_f · l_f(x_f)        expected model wall time, seconds     (extract + verify calls)
    H(x) = Σ_f n_f · h_f(x_f)        expected human work items             (risk ≥ 2 in the queue, or blank)

Hard constraints
    U(x) = Σ_f n_f · u_f(x_f) ≤ ε     wrong non-blank values the verifier lets through (risk < 2) — safety
    packet + prompt + output ≤ context (2048 on Hailo-10H) — enforced upstream by the selector budget
    every cited segment ∈ eligible set — enforced upstream; a run that violates it is not admitted

Because the objectives are additive over fields and X is small, the exact Pareto set is obtained by
per-field non-dominated filtering and a Minkowski-sum merge. When X grows (continuous budget B, model
mixes, UGen300 measurements with noise), the same objective/constraint definitions are handed to a
multi-objective solver; QR-MOPBnB is the intended solver with NSGA-II as the comparator. Those are NOT
implemented here; this module provides the exact baseline the solvers must reproduce on small X.

Interface:
    table = field_objectives(runs_root, case, style, contract)        # measured e, l, h, u per (field, config)
    front = pareto_policies(table, epsilon)                           # list of {policy, E, L, H, U}
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

from .pipeline import open_case
from .runlog import read_ledger
from .verify import deterministic_check, risk

CASES = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "cases"


def _config_key(meta: dict) -> str:
    m = dict(meta)
    m.setdefault("num_ctx", 2048)
    m["dense"] = m.get("dense") or "none"
    return "|".join(str(m.get(k)) for k in ("adapter", "model", "selector", "prompt", "llm_mode", "num_ctx", "dense"))


def field_objectives(runs_root: str | Path, case: str, style: str, contract) -> dict:
    runs_root = Path(runs_root)
    ctx = open_case(CASES / case, style, contract)
    table: dict[str, dict[str, dict]] = {}
    for entry in read_ledger(runs_root):
        if entry.get("kind") or entry.get("case_id") != case or entry.get("style") != style:
            continue
        run = runs_root / entry["run_id"]
        meta = json.loads((run / "config.json").read_text(encoding="utf-8"))
        meta.setdefault("prompt", "v1")
        if meta.get("snapshot") != ctx.snapshot:
            continue  # different sources: not comparable
        key = _config_key(meta)
        lines = [l for l in (run / "records.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        dense_share = float(meta.get("dense_seconds") or 0.0) / max(1, len(lines))  # index cost spread over fields
        for line in lines:
            rec = json.loads(line)
            field = contract.field(rec["field"])
            det = deterministic_check(ctx.store, contract, rec, rec["field"], rec["claim"])  # current verifier
            r = risk(det, rec.get("llm"), field)
            wall = dense_share + float((rec["claim"].get("meta") or {}).get("wall_s") or 0.0) + \
                float(((rec.get("llm") or {}).get("meta") or {}).get("wall_s") or 0.0)
            wrong = not rec.get("eval", {}).get("correct")
            agg = table.setdefault(rec["field"], {}).setdefault(key, {"n": 0, "wrong": 0, "wall": 0.0, "review": 0,
                                                                        "through": 0, "run_id": entry["run_id"],
                                                                        "runs": set()})
            agg["runs"].add(entry["run_id"])
            agg["n"] += 1
            agg["wrong"] += int(wrong)
            agg["wall"] += wall
            missing = det["outcome"] == "MISSING"
            agg["review"] += int(r >= 2 or missing)            # a blank field is human work too
            agg["through"] += int(wrong and r < 2 and not missing)  # a blank is visible; a wrong value is not
    out: dict[str, dict[str, dict]] = {}
    for f, configs in table.items():
        for key, a in configs.items():
            n = a["n"]
            r = len(a["runs"])  # replications of the same configuration (R): rates are pooled, n is per run
            out.setdefault(f, {})[key] = {"n": n // r, "replications": r, "e": a["wrong"] / n, "l": a["wall"] / n,
                                          "h": a["review"] / n, "u": a["through"] / n, "run_id": a["run_id"]}
    return out


def _dominates(a: tuple, b: tuple) -> bool:
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def _front(points: list[tuple[tuple, object]]) -> list[tuple[tuple, object]]:
    return [p for p in points if not any(_dominates(q[0], p[0]) for q in points if q is not p)]


def pareto_policies(table: dict, epsilon: float = 0.0, limit: int = 50) -> list[dict]:
    fields = sorted(table)
    per_field = []
    for f in fields:
        pts = []
        for key, o in table[f].items():
            n = o["n"]
            pts.append(((n * o["e"], n * o["l"], n * o["h"], n * o["u"]), (f, key)))
        # keep U as an objective inside the per-field filter so the merge can still meet the global ε
        per_field.append(_front(pts))
    combos = []
    for choice in itertools.product(*per_field):
        E = sum(c[0][0] for c in choice)
        L = sum(c[0][1] for c in choice)
        H = sum(c[0][2] for c in choice)
        U = sum(c[0][3] for c in choice)
        if U <= epsilon + 1e-9:
            combos.append(((E, L, H), {"policy": {f: k for (_, (f, k)) in choice}, "E": round(E, 3),
                                       "L_seconds": round(L, 2), "H": round(H, 3), "U": round(U, 3)}))
    front = [c[1] for c in _front(combos)]
    front.sort(key=lambda d: (d["E"], d["L_seconds"], d["H"]))
    return front[:limit]
