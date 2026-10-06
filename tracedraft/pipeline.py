"""Pipeline — one case, end to end, as plain function calls (no hidden state).

    ctx     = open_case(case_dir, style, contract)                 # ingest + freeze + plan
    records = extract_all(ctx, selector, port, budget)             # one record per (row, field)
    records = verify_all(ctx, records, verify_port, llm_mode)      # deterministic + optional model
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .contract import FieldContract
from .select import Budget, select
from .store import EvidenceStore
from .verify import verify_record

EVIDENCE_KEYS = ("evidence_id", "doc_id", "rev", "role", "kind", "page", "section", "row_key", "row_norm",
                 "columns", "text")


@dataclass
class CaseContext:
    case_dir: Path
    style: str
    contract: FieldContract
    store: EvidenceStore
    snapshot: str
    eligible: set
    rows: list


def open_case(case_dir: str | Path, style: str, contract: FieldContract) -> CaseContext:
    case_dir = Path(case_dir)
    store = EvidenceStore(":memory:")
    store.ingest(case_dir / f"manifest_{style}.json")
    snapshot = store.freeze()
    eligible = contract.eligible_ids(store)
    rows = contract.plan(store)
    return CaseContext(case_dir, style, contract, store, snapshot, eligible, rows)


def make_task(ctx: CaseContext, row: dict, field: dict, packet) -> dict:
    return {
        "task_id": f"{row['condition']}|{row['test_name']}|{field['name']}",
        "test_name": row["test_name"], "condition": row["condition"], "condition_label": row["condition_label"],
        "field": field["name"], "field_label": field["label"], "rules": field.get("rules", []),
        "cues": field.get("cues", []),
        "evidence": [{k: ctx.store.get(e)[k] for k in EVIDENCE_KEYS} for e in packet.evidence_ids],
    }


def extract_all(ctx: CaseContext, selector: str, port, budget: Budget | None = None, progress=None) -> list[dict]:
    budget = budget or Budget()
    records = []
    total = len(ctx.rows) * len(ctx.contract.fields)
    for row in ctx.rows:
        for field in ctx.contract.fields:
            packet = select(selector, ctx.store, ctx.contract, field, row, ctx.eligible, budget)
            task = make_task(ctx, row, field, packet)
            claim = port.extract(task)
            records.append({
                "task_id": task["task_id"], "condition": row["condition"], "condition_label": row["condition_label"],
                "test_name": row["test_name"], "field": field["name"], "high_risk": field.get("high_risk", False),
                "packet": packet.to_dict(), "claim": claim,
            })
            if progress:
                progress(len(records), total, records[-1])
    return records


def verify_all(ctx: CaseContext, records: list[dict], port=None, llm_mode: str = "review", progress=None) -> list[dict]:
    out = []
    for i, rec in enumerate(records, 1):
        out.append(verify_record(ctx.store, ctx.contract, port, rec, llm_mode))
        if progress:
            progress(i, len(records), out[-1])
    return out
