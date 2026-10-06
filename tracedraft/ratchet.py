"""Hypervolume ratchet — keep a configuration change only if it improves the Pareto archive.

A candidate configuration x is scored by a frozen evaluator on four objectives, all minimised and
normalised to [0, 1]:
    f1 = U / N    wrong non-blank values the verifier lets through (also a hard constraint U/N ≤ ε)
    f2 = H / N    items a person has to handle (review queue + blanks)
    f3 = E / N    wrong values = 1 − P̂
    f4 = L / (N · L_cap)  model seconds per field over a cap fixed in advance
Reference point r = (1, 1, 1, 1).

Decision rule (one change per round, author's method):
    INFEASIBLE           U/N > ε  (checked first; safety before efficiency)
    DUPLICATE_CANDIDATE  the same configuration was already decided under this evaluator
    DUPLICATE_OBJECTIVE  a different configuration with an identical objective vector is in the archive
    KEPT                 HV(archive ∪ {F(x)}) > (1 + min_gain) · HV(archive)
    DISCARDED            otherwise
Three non-KEPT decisions in a row hand the next step to error analysis instead of more greedy changes.

Interface:
    hv(points, ref) -> float
    decide(archive, candidate_key, candidate_vec, eps, u_rate=, epsilon=, min_gain=) -> {"decision", "hv_before", "hv_after"}
    evaluator_id(contract_path) -> str      (16 hex of SHA-256; archives never mix evaluators)
"""
from __future__ import annotations

KEPT, DISCARDED, DUP_CAND, DUP_OBJ = "KEPT", "DISCARDED", "DUPLICATE_CANDIDATE", "DUPLICATE_OBJECTIVE"
INFEASIBLE = "INFEASIBLE"  # TraceDraft addition: U ≤ ε is a hard safety constraint, checked before HV

_EVALUATOR_FILES = ("verify.py", "policy_opt.py", "ratchet.py")


def evaluator_id(contract_path) -> str:
    """Frozen evaluator: decisions are comparable only under the same evaluator. The id is the
    SHA-256 of the evaluator source files plus the field contract; change any of them and the ratchet
    starts a new archive instead of mixing verdicts from two different judges."""
    import hashlib
    from pathlib import Path
    h = hashlib.sha256()
    here = Path(__file__).resolve().parent
    for name in _EVALUATOR_FILES:
        h.update((here / name).read_bytes().replace(b"\r\n", b"\n"))
    h.update(Path(contract_path).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def _nondominated(points: list[tuple]) -> list[tuple]:
    out = []
    for p in points:
        if any(all(q[i] <= p[i] for i in range(len(p))) and q != p for q in points):
            continue
        if p not in out:
            out.append(p)
    return out


def hv(points: list[tuple], ref: tuple) -> float:
    """Exact hypervolume (minimisation) by slicing on the last objective. Fine for the small fronts here."""
    pts = [p for p in _nondominated([tuple(p) for p in points]) if all(p[i] < ref[i] for i in range(len(ref)))]
    if not pts:
        return 0.0
    d = len(ref)
    if d == 1:
        return ref[0] - min(p[0] for p in pts)
    pts.sort(key=lambda p: p[-1])
    total = 0.0
    for i, p in enumerate(pts):
        upper = pts[i + 1][-1] if i + 1 < len(pts) else ref[-1]
        height = upper - p[-1]
        if height <= 0:
            continue
        total += height * hv([q[:-1] for q in pts[: i + 1]], ref[:-1])
    return total


def decide(archive: list[dict], candidate_key: str, candidate_vec: tuple, eps: float = 1e-9,
           ref: tuple = (1.0, 1.0, 1.0, 1.0), u_rate: float = 0.0, epsilon: float | None = None,
           min_gain: float = 0.0) -> dict:
    """min_gain: relative HV improvement a candidate must exceed to be KEPT. Single measurements are noisy
    (run-to-run differences at temperature 0 are measured, not assumed), so a margin fixed in advance keeps
    noise out of the archive — the same rule as a calibrator that keeps a setting only when it beats the
    default by more than a fixed percentage."""
    keys = {a["key"] for a in archive}
    vecs = [tuple(a["vec"]) for a in archive]
    before = hv(vecs, ref)
    if epsilon is not None and u_rate > epsilon + 1e-12:
        return {"decision": INFEASIBLE, "hv_before": before, "hv_after": before}
    if candidate_key in keys:
        return {"decision": DUP_CAND, "hv_before": before, "hv_after": before}
    if any(all(abs(v[i] - candidate_vec[i]) <= 1e-12 for i in range(len(v))) for v in vecs):
        return {"decision": DUP_OBJ, "hv_before": before, "hv_after": before}
    after = hv(vecs + [tuple(candidate_vec)], ref)
    return {"decision": KEPT if after > before * (1.0 + min_gain) + eps else DISCARDED,
            "hv_before": before, "hv_after": after}
