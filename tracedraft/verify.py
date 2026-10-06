"""Citation verifier — turns "value present but citation wrong" into a ranked review queue.

Interface:
    check = deterministic_check(store, contract, row, field_name, claim) -> {"outcome", "codes"}
    rec   = verify_record(store, contract, port, record, llm_mode)       # adds checks + verdict + risk
    queue = review_queue(records)                                        # highest risk first

Two layers, by design:
  1. Deterministic (CPU, free): evidence exists, is eligible (current revision, normative
     section), comes from an allowed and authoritative role, names the right test, and —
     for table rows — the contract recomputes the value from the cited cell. Prose sources
     get a containment check; a value whose numbers are present but whose wording differs
     is PARAPHRASE: undecidable by rules.
  2. Model (on-device): asked whether the quote supports the claim. In `review` mode only
     PARAPHRASE / unresolved items go to the model; in `all` mode every item does
     (used to measure the model on its own).
The verifier only ORDERS human work. It never approves anything.
"""
from __future__ import annotations

import re

from .contract import mentions
from .textnorm import comparators, norm, numbers

FLAG, REVIEW, PASS, MISSING = "FLAG", "REVIEW", "PASS", "MISSING"


def canon(text) -> str:
    return norm(str(text)).rstrip(" .;:")


def deterministic_check(store, contract, row: dict, field_name: str, claim: dict, clause_mode: bool = True) -> dict:
    field = contract.field(field_name)
    codes: list[str] = []
    if claim.get("status") in {"MISSING", "PENDING_RELAY", "ERROR"} or claim.get("value") in (None, ""):
        # Honest blank: still needs a person, but it is not a citation error.
        if claim.get("status") == "ERROR":
            return {"outcome": FLAG, "codes": ["MODEL_ERROR"]}
        return {"outcome": MISSING, "codes": ["NO_VALUE_NEEDS_HUMAN"]}
    eid = claim.get("evidence_id")
    seg = store.get(eid) if eid else None
    if seg is None:
        return {"outcome": FLAG, "codes": ["EVIDENCE_UNKNOWN"]}
    ok, why = contract.eligible(seg)
    if not ok:
        codes.append("NOT_ELIGIBLE_" + why)
    if seg["role"] not in contract.allowed_roles(field):
        codes.append("ROLE_NOT_ALLOWED")
    authority = field.get("authority")
    if authority and seg["role"] != authority[0]:
        codes.append("NOT_AUTHORITATIVE_SOURCE")
    if not mentions(seg, row["test_name"]):
        codes.append("WRONG_TEST")
    if codes:
        return {"outcome": FLAG, "codes": codes}

    fmt = field.get("format")
    if fmt and field_name != "n" and not re.fullmatch(fmt, str(claim["value"]).strip()):
        return {"outcome": FLAG, "codes": ["FORMAT_MISMATCH"]}

    status, expected = contract.expected_from(field, seg, row["condition_label"])
    if status == "MISSING":
        return {"outcome": FLAG, "codes": ["VALUE_INVENTED_SOURCE_HAS_NONE"]}
    if status == "SOURCED":
        same = (expected == claim["value"]) if field_name == "n" else canon(expected) == canon(claim["value"])
        return {"outcome": PASS if same else FLAG, "codes": [] if same else ["VALUE_MISMATCH_RECOMPUTED"]}

    # Prose. 1) clause-anchored: the value must sit in the clause that follows this field's own cue.
    value = str(claim["value"])
    attr = field.get("attribute_rule")
    body = value[len(attr["prefix"]):] if attr and value.startswith(attr["prefix"]) else value
    text = canon(seg["text"])
    clause = contract.clause(field, seg["text"]) if clause_mode else None
    if clause_mode and attr and attr.get("prose_type_cue"):
        # RULE 7 analogue: an Attribute requirement's specification is prefix + the requirement sentence.
        is_attr = re.search(r"(?<![a-z])" + re.escape(attr["prose_type_cue"]) + r"(?![a-z])", seg["text"].lower())
        has_prefix = value.startswith(attr["prefix"])
        if is_attr and not has_prefix:
            return {"outcome": FLAG, "codes": ["ATTRIBUTE_RULE_NOT_APPLIED"]}
        if has_prefix and not is_attr:
            return {"outcome": FLAG, "codes": ["ATTRIBUTE_RULE_ON_VARIABLE"]}
        if is_attr:
            marker = attr.get("prose_statement_marker", "shall")
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", seg["text"])
            ok = any(marker in canon(sent) and canon(sent).endswith(canon(body)) and marker in canon(body)
                     for sent in sentences)
            return {"outcome": PASS, "codes": []} if ok else {"outcome": FLAG, "codes": ["ATTRIBUTE_STATEMENT_MISMATCH"]}
    if clause is not None:
        cl = canon(clause)
        missing_markers = {canon(m) for m in field.get("missing_markers", []) if m}
        if cl in missing_markers:
            return {"outcome": FLAG, "codes": ["VALUE_INVENTED_SOURCE_HAS_NONE"]}
        if canon(body) and canon(body) == cl:
            return {"outcome": PASS, "codes": []}
        if canon(body) and canon(body) in cl:
            if fmt and re.fullmatch(fmt, body.strip()):
                return {"outcome": PASS, "codes": []}   # an identifier inside its clause, e.g. "TM-1 (title)"
            return {"outcome": FLAG, "codes": ["PARTIAL_COPY"]}  # the contract asks for an exact copy
        if canon(body) and canon(body) in text:
            return {"outcome": FLAG, "codes": ["WRONG_CLAUSE"]}
        nums, cmps = numbers(body), comparators(body)
        if nums and all(n in numbers(clause) for n in nums) and all(c in comparators(clause) for c in cmps):
            return {"outcome": REVIEW, "codes": ["PARAPHRASE_NUMBERS_PRESENT"]}
        return {"outcome": FLAG, "codes": ["VALUE_NOT_IN_CLAUSE"]}

    # 2) no cue for this field in the passage: containment, then numbers/comparators.
    if clause_mode and field.get("high_risk") and canon(body) and canon(body) in text:
        # Anchored or escalated: without this field's cue the rules cannot tell WHICH clause the value came
        # from (held-out phrasing: "≤ 240 s" sits in both the specification and "Mean + 3σ ≤ 240 s").
        # On a high-risk field containment alone is not evidence, so the item goes to a person.
        return {"outcome": REVIEW, "codes": ["UNANCHORED_HIGH_RISK"]}
    if canon(body) and canon(body) in text:
        if attr and value.startswith(attr["prefix"]) and "attribute" not in text:
            return {"outcome": REVIEW, "codes": ["ATTRIBUTE_RULE_UNCONFIRMED"]}
        return {"outcome": PASS, "codes": []}
    nums, cmps = numbers(body), comparators(body)
    seg_nums, seg_cmps = numbers(seg["text"]), comparators(seg["text"])
    if nums and all(n in seg_nums for n in nums) and all(c in seg_cmps for c in cmps):
        return {"outcome": REVIEW, "codes": ["PARAPHRASE_NUMBERS_PRESENT"]}
    return {"outcome": FLAG, "codes": ["VALUE_NOT_IN_SOURCE"]}


def _task_for(row: dict, field: dict, claim: dict) -> dict:
    return {"task_id": row["task_id"], "test_name": row["test_name"], "condition_label": row["condition_label"],
            "field": field["name"], "field_label": field["label"]}


def verify_record(store, contract, port, record: dict, llm_mode: str = "review") -> dict:
    field = contract.field(record["field"])
    claim = record["claim"]
    det = deterministic_check(store, contract, record, record["field"], claim)
    out = dict(record)
    out["det"] = det
    verdict = None
    wants_llm = (llm_mode == "all" and det["outcome"] in {PASS, REVIEW, FLAG}) or \
                (llm_mode == "review" and det["outcome"] == REVIEW)
    if port is not None and wants_llm and claim.get("value") not in (None, ""):
        seg = store.get(claim.get("evidence_id") or "")
        quote = claim.get("quote") or (seg["text"] if seg else "")
        verdict = port.verify(_task_for(record, field, claim), dict(claim, quote=quote))
    out["llm"] = verdict
    out["risk"] = risk(det, verdict, field)
    return out


def risk(det: dict, verdict: dict | None, field: dict) -> float:
    v = (verdict or {}).get("verdict")
    if det["outcome"] == FLAG or v == "NOT_SUPPORTED":
        score = 3.0
    elif det["outcome"] == REVIEW and (v != "SUPPORTED" or field.get("high_risk")):
        # the model layer may clear an undecidable item only on low-risk fields; on high-risk fields it can
        # escalate but not clear (round-2 finding: the model passed a paraphrase that dropped "Mean − 3σ")
        score = 2.0
    elif det["outcome"] == MISSING:
        score = 1.0
    elif v == "INSUFFICIENT":
        score = 1.5
    else:
        score = 0.0
    return score + (0.5 if field.get("high_risk") else 0.0)


def review_queue(records: list[dict]) -> list[dict]:
    return sorted(records, key=lambda r: (-r["risk"], r["condition"], r["test_name"], r["field"]))
