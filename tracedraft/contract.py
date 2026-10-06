"""FieldContract — human-maintained rules for every field. Models never edit it.

Interface:
    c = FieldContract.load(path)
    c.eligible(segment) -> (bool, reason)        # hard filter e_i: status + normative section
    c.plan(store) -> [row]                        # membership + n read deterministically from the plan table
    c.field(name) / c.fields
    c.column_for(field, role, condition_label)
    c.units(field) -> requirement units U for FCEA
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .textnorm import key


def condition_key(label: str) -> str:
    return re.sub(r"[^a-z]", "", label.split("(")[0].strip().split(" ")[0].lower())


@dataclass
class FieldContract:
    raw: dict

    @classmethod
    def load(cls, path: str | Path) -> "FieldContract":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    @property
    def contract_id(self) -> str:
        return self.raw["contract_id"]

    @property
    def fields(self) -> list[dict]:
        return self.raw["fields"]

    def field(self, name: str) -> dict:
        for f in self.fields:
            if f["name"] == name:
                return f
        raise KeyError(name)

    # -------------------------------------------------------------- eligibility e_i
    def eligible(self, seg: dict) -> tuple[bool, str]:
        el = self.raw["eligibility"]
        if seg["status"] not in el["document_status"]:
            return False, f"STATUS_{seg['status']}"
        pattern = el["sections"].get(seg["role"])
        if pattern is None:
            return False, "ROLE_NOT_ALLOWED"
        if not re.search(pattern, seg["section"] or ""):
            return False, "SECTION_NOT_NORMATIVE"
        return True, "OK"

    def eligible_ids(self, store) -> set[str]:
        return {s["evidence_id"] for s in store.all() if self.eligible(s)[0]}

    # -------------------------------------------------------------- membership (deterministic)
    def plan(self, store) -> list[dict]:
        m = self.raw["membership"]
        not_run = {key(x) for x in m["not_performed"]}
        rows_by_cond: dict[str, list[dict]] = {}
        order: list[str] = []
        for seg in store.all():
            if seg["role"] != m["role"] or seg["kind"] != "row" or not self.eligible(seg)[0]:
                continue
            for label, cell in seg["columns"].items():
                if label == "Test Name":
                    continue
                ck = condition_key(label)
                if ck not in rows_by_cond:
                    rows_by_cond[ck] = []
                    order.append((ck, label))
                if key(cell) in not_run:
                    continue
                rows_by_cond[ck].append({"condition": ck, "condition_label": label, "test_name": seg["row_key"],
                                         "plan_evidence_id": seg["evidence_id"], "row_index": seg["row_index"]})
        out = []
        for ck, _label in order:
            out.extend(sorted(rows_by_cond[ck], key=lambda r: r["row_index"]))
        return out

    # -------------------------------------------------------------- per-field helpers
    def units(self, field: dict) -> list[dict]:
        return field["units"]

    def column_for(self, field: dict, role: str, condition_label: str) -> str | None:
        col = field.get("column", {}).get(role)
        return col.replace("{condition_label}", condition_label) if col else None

    def clause(self, field: dict, text: str) -> str | None:
        return clause_for(self.raw, field, text)

    def covers(self, unit: dict, seg: dict, test_name: str) -> bool:
        """A_ui: fixed matching rule (role + normalised row key). Never uses answers."""
        return seg["role"] == unit["role"] and mentions(seg, test_name)

    def allowed_roles(self, field: dict) -> set[str]:
        return {u["role"] for u in field["units"]}

    def expected_from(self, field: dict, seg: dict, condition_label: str) -> tuple[str, object]:
        """Recompute a field from ONE table-row segment with the contract's column rules.
        Returns (status, value): ("SOURCED", v) | ("MISSING", None) | ("NOT_TABULAR", None)."""
        if seg["kind"] != "row":
            return "NOT_TABULAR", None
        col = self.column_for(field, seg["role"], condition_label)
        if not col or col not in seg["columns"]:
            return "NOT_TABULAR", None
        raw = seg["columns"][col]
        attr = field.get("attribute_rule")
        if attr and key(seg["columns"].get(attr["type_column"])) == key(attr["type_value"]):
            return "SOURCED", attr["prefix"] + seg["columns"].get(attr["statement_column"], "")
        markers = {key(m) for m in field.get("missing_markers", [])} | ({key(x) for x in self.raw["membership"]["not_performed"]} if field["name"] == "n" else set())
        if key(raw) in markers:
            return "MISSING", None
        if field["name"] == "n":
            try:
                return "SOURCED", int(raw.replace(",", ""))
            except ValueError:
                return "MISSING", None
        return "SOURCED", raw


_SENTENCE_END = re.compile(r"\.\s+(?=[A-Z])|\.\s*$|;\s+|,\s+and\s+")


def _cue_positions(text_low: str, cues: list[str]) -> list[tuple[int, int]]:
    out = []
    for cue in cues:
        for m in re.finditer(r"(?<![a-z])" + re.escape(cue.lower()) + r"(?![a-z])", text_low):
            out.append((m.start(), m.end()))
    return out


def clause_for(contract_raw: dict, field: dict, text: str) -> str | None:
    """The text that follows the field's own cue, up to the next cue of any OTHER field or the end of the
    sentence. Returns None when the field's cue does not occur. Cues are a label vocabulary in the contract,
    maintained by people; this function never looks at answers."""
    cues = field.get("cues") or []
    if not cues:
        return None
    low = text.lower()
    own = _cue_positions(low, cues)
    if not own:
        return None
    start, end = sorted(own, key=lambda p: (p[0], -(p[1] - p[0])))[0]
    other_cues = [c for f in contract_raw["fields"] if f["name"] != field["name"] for c in f.get("cues", [])]
    stops = [p[0] for p in _cue_positions(low, other_cues) if p[0] >= end]
    stop = min(stops) if stops else len(text)
    clause = text[end:stop]
    m = _SENTENCE_END.search(clause)
    if m:
        clause = clause[:m.start()]
    lead = contract_raw.get("clause_rules", {}).get("lead_words", [])
    changed = True
    while changed:
        changed = False
        stripped = clause.strip()
        for w in lead:
            if stripped.lower().startswith(w.lower()) and (not w.isalpha() or stripped[len(w):len(w) + 1] in (" ", ":", "")):
                clause = stripped[len(w):]
                changed = True
                break
    return clause.strip(" ,;.")


def mentions(seg: dict, test_name: str) -> bool:
    """Fixed matching rule: a table row whose key is the test name, or a paragraph that names the test."""
    k = key(test_name)
    if seg["kind"] == "row":
        return seg["row_norm"] == k
    return bool(k) and k in key(seg["text"])
