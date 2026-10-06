"""Evidence selection — the one surface the first experiment is allowed to change.

Interface:
    packet = select(kind, store, contract, field, row, eligible_ids, budget)   # kind: "fcea" | "topk"

Both arms see the same eligible set, the same RRF ranking and the same token budget B.
  * topk : walk the RRF order and add segments until the budget is full (baseline).
  * fcea : for each requirement unit u of the field, add the best-ranked eligible segment
           that covers u (fixed rule A_ui), cheapest-first on ties; stop when every unit is
           covered. Required units left uncovered make the field NEEDS_REVIEW — the budget
           is never silently enlarged.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dfield

from .textnorm import est_tokens

KAPPA = 60  # RRF constant (Cormack et al., SIGIR 2009); frozen before any measurement


@dataclass
class Budget:
    context: int = 2048          # Hailo-10H GenAI LLMs: 2048-token context (Hailo GenAI Model Zoo)
    prompt_overhead: int = 520   # longest extract prompt without evidence = 288 est. tokens (tests check it) + chat-template margin
    max_output: int = 160

    @property
    def evidence(self) -> int:
        return self.context - self.prompt_overhead - self.max_output


@dataclass
class Packet:
    selector: str
    field: str
    query: str
    evidence_ids: list[str]
    cost: int
    budget: int
    coverage: dict = dfield(default_factory=dict)
    needs_review: list[str] = dfield(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def seg_cost(seg: dict) -> int:
    return est_tokens(f"[{seg['evidence_id']}] {seg['text']}\n")


def rrf(rankings: dict[str, list[str]], kappa: int = KAPPA) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings.values():
        for rank, eid in enumerate(ranking, 1):
            scores[eid] = scores.get(eid, 0.0) + 1.0 / (kappa + rank)
    return scores


def query_for(field: dict, row: dict) -> str:
    parts = [row["test_name"], field["label"]]
    if field["name"] == "n":
        parts.append(row["condition_label"])
    return " ".join(parts)


def _ordered(store, eligible_ids: set[str], query: str) -> tuple[list[str], dict[str, float]]:
    scores = rrf(store.rank(query, eligible_ids))
    ordered = sorted(eligible_ids, key=lambda i: (-scores.get(i, 0.0), i))
    return ordered, scores


def select(kind: str, store, contract, field: dict, row: dict, eligible_ids: set[str], budget: Budget) -> Packet:
    query = query_for(field, row)
    ordered, scores = _ordered(store, eligible_ids, query)
    B = budget.evidence
    chosen: list[str] = []
    cost = 0
    if kind == "topk":
        for eid in ordered:
            if scores.get(eid, 0.0) <= 0:
                break
            c = seg_cost(store.get(eid))
            if cost + c > B:
                break
            chosen.append(eid)
            cost += c
        coverage = {}
        for unit in contract.units(field):
            hit = next((e for e in chosen if contract.covers(unit, store.get(e), row["test_name"])), None)
            coverage[unit["id"]] = hit
        needs = [u["id"] for u in contract.units(field) if not u.get("optional") and coverage[u["id"]] is None]
        return Packet("topk", field["name"], query, chosen, cost, B, coverage, needs)
    if kind != "fcea":
        raise ValueError(f"unknown selector {kind}")
    coverage = {}
    needs = []
    for unit in contract.units(field):
        covering = [e for e in ordered if contract.covers(unit, store.get(e), row["test_name"])]
        covering.sort(key=lambda e: (-scores.get(e, 0.0), seg_cost(store.get(e)), e))
        pick = None
        for eid in covering:
            if eid in chosen:
                pick = eid
                break
            c = seg_cost(store.get(eid))
            if cost + c <= B:
                pick = eid
                chosen.append(eid)
                cost += c
                break
        coverage[unit["id"]] = pick
        if pick is None and not unit.get("optional"):
            needs.append(unit["id"])
    return Packet("fcea", field["name"], query, chosen, cost, B, coverage, needs)
