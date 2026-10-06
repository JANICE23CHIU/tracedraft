"""Evaluation — scoring against the by-construction gold, and the citation-error injection set.

Interface:
    scored  = score(ctx, records, gold)            -> per-record correctness + metrics
    muts    = mutations(ctx, gold, seed)           -> list of (claim, is_error, kind) for the verifier
    vmetrics= verifier_metrics(ctx, muts, port, llm_mode)

Primary metric (fixed before any run): task correct completion rate P̂ = share of field tasks
whose value AND citation are both correct; a gold-MISSING task is correct only if the
system also reports MISSING. Every planned task is in the denominator, including errors,
timeouts and pending relays. Everything else is diagnostic.
"""
from __future__ import annotations

import random
import re

from .contract import mentions
from .textnorm import key
from .verify import FLAG, PASS, canon, deterministic_check


def gold_index(gold: dict) -> dict:
    out = {}
    for row in gold["rows"]:
        for fname, g in row["fields"].items():
            out[(row["condition"], key(row["test_name"]), fname)] = g
    return out


def value_ok(field: str, claim: dict, g: dict) -> bool:
    if g.get("value") is None:
        return claim.get("status") == "MISSING" and claim.get("value") in (None, "")
    if claim.get("status") != "SOURCED" or claim.get("value") in (None, ""):
        return False
    if field == "n":
        try:
            return int(claim["value"]) == int(g["value"])
        except (TypeError, ValueError):
            return False
    return canon(claim["value"]) == canon(g["value"])


def citation_ok(store, claim: dict, g: dict, test_name: str) -> bool:
    if g.get("value") is None:
        return True
    seg = store.get(claim.get("evidence_id") or "")
    if not seg:
        return False
    src = g["source"]
    return seg["doc_id"] == src["doc_id"] and seg["rev"] == src["rev"] and mentions(seg, test_name)


def score(ctx, records: list[dict], gold: dict) -> dict:
    gi = gold_index(gold)
    planned = {(r["condition"], key(r["test_name"])) for r in gold["rows"]}
    got = {(r["condition"], key(r["test_name"])) for r in ctx.rows}
    per_field: dict[str, list[int]] = {}
    rows_ok: dict[tuple, bool] = {}
    conflict_rows = {key(c["test_name"]) for c in gold.get("conflicts", [])}
    conflicts_reported = 0
    tokens = []
    for rec in records:
        g = gi.get((rec["condition"], key(rec["test_name"]), rec["field"]))
        if g is None:
            rec["eval"] = {"in_gold": False, "correct": False}
            continue
        v = value_ok(rec["field"], rec["claim"], g)
        c = citation_ok(ctx.store, rec["claim"], g, rec["test_name"])
        rec["eval"] = {"in_gold": True, "value_ok": v, "citation_ok": c, "correct": v and c,
                       "gold_value": g.get("value")}
        per_field.setdefault(rec["field"], []).append(int(v and c))
        k = (rec["condition"], key(rec["test_name"]))
        rows_ok[k] = rows_ok.get(k, True) and v and c
        tokens.append(rec["packet"]["cost"])
        if rec["field"] == "specification" and key(rec["test_name"]) in conflict_rows and rec["claim"].get("conflict"):
            conflicts_reported += 1
    n_tasks = sum(len(r["fields"]) for r in gold["rows"])
    correct = sum(1 for r in records if r.get("eval", {}).get("correct"))
    return {
        "tasks_planned_gold": n_tasks, "tasks_run": len(records),
        "P_hat": round(correct / n_tasks, 4) if n_tasks else None,
        "value_accuracy": round(sum(1 for r in records if r.get("eval", {}).get("value_ok")) / n_tasks, 4),
        "citation_accuracy": round(sum(1 for r in records if r.get("eval", {}).get("citation_ok")) / n_tasks, 4),
        "row_all_fields_correct": round(sum(rows_ok.values()) / len(planned), 4) if planned else None,
        "by_field": {f: round(sum(v) / len(v), 4) for f, v in sorted(per_field.items())},
        "membership": {"gold_rows": len(planned), "planned_rows": len(got), "missing_rows": len(planned - got),
                       "extra_rows": len(got - planned)},
        "conflict_rows_in_run": sum(1 for r in records if r["field"] == "specification"
                                    and r["condition"] == "standard" and key(r["test_name"]) in conflict_rows),
        "conflicts_reported_any_condition": conflicts_reported,
        "packet_tokens_mean": round(sum(tokens) / len(tokens), 1) if tokens else None,
        "packet_tokens_max": max(tokens) if tokens else None,
        "status_counts": _counts(r["claim"].get("status") for r in records),
    }


def _counts(items) -> dict:
    out: dict = {}
    for i in items:
        out[str(i)] = out.get(str(i), 0) + 1
    return dict(sorted(out.items()))


# --------------------------------------------------------------------------- citation-error injection
UNIT_SWAP = [(r"(?<=\d) s\b", " min"), (r"°C", "°F"), (r"(?<=\d) N\b", " kN"), (r"dB\(A\)", "dB"),
             (r"m³/min", "L/min"), (r"(?<=\d)°(?!C)", " rad"), (r"(?<=\d) cycles\b", " hours")]


def _source_segment(ctx, g: dict, test_name: str) -> dict | None:
    src = g["source"]
    for seg in ctx.store.all():
        if seg["doc_id"] == src["doc_id"] and seg["rev"] == src["rev"] and mentions(seg, test_name) \
                and ctx.contract.eligible(seg)[0]:
            return seg
    return None


def mutations(ctx, gold: dict, seed: int = 20261004) -> list[dict]:
    rng = random.Random(seed)
    items = []
    gi_rows = gold["rows"]
    segs = ctx.store.all()
    for row in gi_rows:
        for fname, g in row["fields"].items():
            base = {"condition": row["condition"], "test_name": row["test_name"], "field": fname,
                    "condition_label": next(c["label"] for c in gold["conditions"] if c["key"] == row["condition"]),
                    "task_id": f"{row['condition']}|{row['test_name']}|{fname}"}
            seg = _source_segment(ctx, g, row["test_name"])
            if seg is None:
                continue
            sibling = row["fields"]
            if g.get("value") is None:
                invented = dict(base, claim={"value": "All samples within limits", "evidence_id": seg["evidence_id"],
                                             "quote": seg["text"], "status": "SOURCED"}, is_error=True, kind="invented_value")
                items.append(invented)
                # observed on the laptop run: the model fills a TBD acceptance with the specification value
                spec_v = sibling.get("specification", {}).get("value")
                if fname == "acceptance" and spec_v and not str(spec_v).startswith("Pass/Fail"):
                    items.append(dict(base, claim={"value": spec_v, "evidence_id": seg["evidence_id"], "quote": seg["text"],
                                                   "status": "SOURCED"}, is_error=True, kind="tbd_filled_from_other_clause"))
                continue
            good = {"value": g["value"], "evidence_id": seg["evidence_id"], "quote": seg["text"], "status": "SOURCED"}
            items.append(dict(base, claim=good, is_error=False, kind="correct"))
            # wrong row: same document and section, different test
            others = [s for s in segs if s["doc_id"] == seg["doc_id"] and s["rev"] == seg["rev"]
                      and s["section"] == seg["section"] and s["evidence_id"] != seg["evidence_id"]
                      and not mentions(s, row["test_name"]) and s["kind"] == seg["kind"]]
            if others:
                o = rng.choice(others)
                items.append(dict(base, claim=dict(good, evidence_id=o["evidence_id"], quote=o["text"]),
                                  is_error=True, kind="wrong_row"))
            # superseded revision / informative appendix of the same test
            for s in segs:
                if s["doc_id"] == seg["doc_id"] and mentions(s, row["test_name"]) and not ctx.contract.eligible(s)[0]:
                    kind = "superseded_rev" if s["rev"] != seg["rev"] else "informative_section"
                    items.append(dict(base, claim=dict(good, evidence_id=s["evidence_id"], quote=s["text"]),
                                      is_error=True, kind=kind))
            val = str(g["value"])
            digits = [m.start() for m in re.finditer(r"\d", val)]
            if digits:
                p = rng.choice(digits)
                mutated = val[:p] + str((int(val[p]) + 1) % 10) + val[p + 1:]
                mv = int(mutated) if fname == "n" else mutated
                items.append(dict(base, claim=dict(good, value=mv), is_error=True, kind="digit_change"))
            if "≤" in val or "≥" in val:
                flipped = val.replace("≤", "\0").replace("≥", "≤").replace("\0", "≥")
                items.append(dict(base, claim=dict(good, value=flipped), is_error=True, kind="comparator_flip"))
            for pattern, repl in UNIT_SWAP:
                swapped, n_sub = re.subn(pattern, repl, val, count=1)
                if n_sub and canon(swapped) != canon(val):
                    items.append(dict(base, claim=dict(good, value=swapped), is_error=True, kind="unit_swap"))
                    break
            if fname == "specification" and val.startswith("Pass/Fail: "):
                # observed on the laptop run (RULE 7 analogue): the model copies the non-numeric limit "N/A"
                items.append(dict(base, claim=dict(good, value="N/A"), is_error=True, kind="attribute_rule_not_applied"))
            if val.startswith("Pass/Fail: ") and " shall " in val:
                items.append(dict(base, claim=dict(good, value=val.replace(" shall ", " shall not ", 1)),
                                  is_error=True, kind="negation"))
            # observed on the laptop run: the right passage, the wrong clause (spec copied as acceptance, or back)
            other_field = {"acceptance": "specification", "specification": "acceptance"}.get(fname)
            if other_field:
                ov = sibling.get(other_field, {}).get("value")
                if ov and canon(ov) != canon(val) and not str(ov).startswith("Pass/Fail"):
                    items.append(dict(base, claim=dict(good, value=ov), is_error=True, kind="wrong_clause"))
            # observed: a partial copy of the right clause (e.g. limits without "All samples within")
            if fname in ("acceptance", "specification") and not val.startswith("Pass/Fail"):
                words_ = val.split()
                if len(words_) >= 4:
                    items.append(dict(base, claim=dict(good, value=" ".join(words_[len(words_) // 2:])),
                                      is_error=True, kind="partial_copy"))
            if fname == "n":
                other_n = [r2["fields"]["n"]["value"] for r2 in gi_rows
                           if r2["test_name"] == row["test_name"] and r2["condition"] != row["condition"]
                           and r2["fields"]["n"]["value"] != g["value"]]
                if other_n:
                    items.append(dict(base, claim=dict(good, value=other_n[0]), is_error=True, kind="other_condition_n"))
    return items


def verifier_metrics(ctx, items: list[dict], port=None, llm_mode: str = "none", progress=None) -> dict:
    by_kind: dict[str, dict] = {}
    rows = []
    for i, it in enumerate(items, 1):
        det = deterministic_check(ctx.store, ctx.contract, it, it["field"], it["claim"])
        det_flag = det["outcome"] == FLAG
        llm = None
        if port is not None and llm_mode != "none" and (llm_mode == "all" or det["outcome"] not in (FLAG, PASS)):
            field = ctx.contract.field(it["field"])
            llm = port.verify({"task_id": it["task_id"], "test_name": it["test_name"],
                               "condition_label": it["condition_label"], "field": it["field"],
                               "field_label": field["label"]}, it["claim"])
        llm_flag = bool(llm) and llm.get("verdict") in ("NOT_SUPPORTED", "INSUFFICIENT")
        combined = det_flag or (det["outcome"] != PASS and llm_flag) if llm_mode == "review" else det_flag or llm_flag
        k = by_kind.setdefault(it["kind"], {"n": 0, "det": 0, "llm": 0, "combined": 0, "llm_asked": 0})
        k["n"] += 1
        k["det"] += int(det_flag)
        k["llm"] += int(llm_flag)
        k["llm_asked"] += int(llm is not None)
        k["combined"] += int(combined)
        rows.append({"kind": it["kind"], "is_error": it["is_error"], "det": det, "llm": llm, "task_id": it["task_id"]})
        if progress:
            progress(i, len(items), rows[-1])
    errors = [k for k in by_kind if k != "correct"]
    def rate(name, keys):
        n = sum(by_kind[k]["n"] for k in keys)
        return round(sum(by_kind[k][name] for k in keys) / n, 4) if n else None
    return {
        "items": len(items), "errors": sum(by_kind[k]["n"] for k in errors),
        "recall_det": rate("det", errors), "recall_llm": rate("llm", errors) if llm_mode != "none" else None,
        "recall_combined": rate("combined", errors),
        "false_alarm_det": rate("det", ["correct"]) if "correct" in by_kind else None,
        "false_alarm_llm": rate("llm", ["correct"]) if ("correct" in by_kind and llm_mode != "none") else None,
        "false_alarm_combined": rate("combined", ["correct"]) if "correct" in by_kind else None,
        "by_kind": dict(sorted(by_kind.items())), "llm_mode": llm_mode, "rows": rows,
    }
