"""Generate the synthetic TraceDraft benchmark from spec.json — deterministic, no randomness needed.

Every planted difficulty is declared in spec.json and echoed into gold.json, so the
answer key exists by construction (no post-hoc labelling, no leakage from a model):

  * attribute tests: the limit column says N/A; the correct Specification is
    "Pass/Fail: <requirement statement>"
  * acceptance "TBD" in an approved spec  -> the honest answer is MISSING
  * the test-method matrix repeats a Specification with a different value -> conflict
  * a superseded revision of the requirements spec sits in the same corpus
  * an informative appendix lists the previous model's values for the same test names
  * one test-method id breaks the numbering pattern (guessing the pattern is wrong)

Two renderings of the same facts: `table` (clean Markdown tables) and `prose` (the same
requirements written as varied sentences, as after a lossy PDF/Word text extraction). The
sample-size plan stays a table in both, because membership is read deterministically.

Usage:  python data/synthetic/generate.py [--check]
--check regenerates in memory and fails if any committed file differs (reproducibility).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "cases"
DASH = "—"


def md_table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def title_block(case: dict, doc: dict, status: str) -> str:
    return "\n".join([
        f"# {doc['title']} — {case['product']}",
        "",
        f"- Document ID: {doc['doc_id']}",
        f"- Revision: {doc['rev']}",
        f"- Status: {status}",
        f"- Owner: {case['company']}",
        "",
        "> Fictional document created for the TraceDraft benchmark (CC BY 4.0).",
    ])


def prs(case: dict, rev: str, status: str, superseded: bool) -> str:
    doc = dict(case["docs"]["PRS"], rev=rev)
    rows = []
    for t in case["tests"]:
        spec, acc = t["spec"], t["acceptance"]
        if superseded and t.get("superseded"):
            spec = t["superseded"]["spec"]
            acc = t["superseded"]["acceptance"]
        rows.append([t["req_id"], t["name"], t["requirement"], t["type"].capitalize(), spec, acc])
    prev = case["previous_model"]
    prev_rows = [[name, value] for name, value in prev["values"].items()]
    return "\n".join([
        "<!-- page 1 -->",
        title_block(case, doc, status),
        "",
        "## 1 Scope",
        "",
        f"This specification defines the design inputs of the {case['product']}.",
        "",
        "<!-- page 2 -->",
        "## 4 Requirements",
        "",
        md_table(["Req ID", "Test Name", "Requirement", "Type", "Specification Limit", "DV Acceptance Criteria"], rows),
        "",
        "Note: For Attribute requirements the Specification Limit is not numeric.",
        "",
        "<!-- page 3 -->",
        f"## Appendix B Previous model results ({prev['name']}, informative)",
        "",
        md_table(["Test Name", "Previous Result"], prev_rows),
        "",
    ])


PROSE_PRS = [
    "{req_id} — {name} ({type} requirement). {requirement} Specification limit: {spec}. DV acceptance criteria: {acc}.",
    "Requirement {req_id} covers {name}. Type: {type}. {requirement} The specification limit is {spec}, and the DV acceptance criteria are: {acc}.",
    "For {name} ({req_id}, {type}): {requirement} Limit — {spec}. Acceptance — {acc}.",
]


PROSE_B_PRS = [
    "{name} [{req_id}] is {article} {type_low} requirement: {requirement} Spec limit = {spec}; pass criteria = {acc}.",
    "Under {req_id} ({name}, {type}) the requirement reads: {requirement} Its specification is {spec}. To pass, every sample must meet: {acc}.",
    "{req_id} | {name} | {type}. {requirement} Required limit: {spec}. Acceptance: {acc}.",
]
# Held-out phrasing, written 2026-10-04 BEFORE any model or verifier run on it. Template 1 uses an
# acceptance phrase that is deliberately NOT in the contract's cue list ("To pass, every sample must meet").

PROSE_C_PRS = [
    "{req_id} ({name}; {type_low}). {requirement} Samples are accepted when {acc}; the design limit itself is {spec}.",
    "{name} — {req_id}, {type} type. Verification succeeds if {acc}. {requirement} Target: {spec}.",
    "{req_id}: {requirement} ({name}, {type_low}). Limit {spec}. Acceptance criterion: {acc}.",
]
PROSE_C_MTX = "{name} is tested per {method} ({method_title}); spec reference {ref}; conditions: {conds}."
# Second held-out phrasing (proseC), written 2026-10-04 after the proseB results were seen and after the
# UNANCHORED_HIGH_RISK verifier rule was added, BEFORE any run on proseC. Its hash is pre-registered in
# docs/PREREGISTRATION_proseC.md. Acceptance is stated before the specification in two templates, and
# templates 1-2 carry no acceptance cue at all; template 2 carries no specification cue either.


def prs_prose_b(case: dict, rev: str, status: str, superseded: bool) -> str:
    doc = dict(case["docs"]["PRS"], rev=rev)
    paras = []
    for i, t in enumerate(case["tests"]):
        spec, acc = t["spec"], t["acceptance"]
        if superseded and t.get("superseded"):
            spec, acc = t["superseded"]["spec"], t["superseded"]["acceptance"]
        paras.append(PROSE_B_PRS[(i + 1) % 3].format(req_id=t["req_id"], name=t["name"], type=t["type"].capitalize(),
                                                   type_low=t["type"], article="an" if t["type"][0] in "aeiou" else "a", requirement=t["requirement"], spec=spec, acc=acc))
    prev = case["previous_model"]
    prev_p = " ".join(f"{name}: {value}." for name, value in prev["values"].items())
    return "\n".join([
        "<!-- page 1 -->", title_block(case, doc, status), "", "## 1 Scope", "",
        f"This specification defines the design inputs of the {case['product']}.", "",
        "<!-- page 2 -->", "## 4 Requirements", "", "\n\n".join(paras), "",
        "<!-- page 3 -->", f"## Appendix B Previous model results ({prev['name']}, informative)", "", prev_p, "",
    ])


def mtx_prose_b(case: dict) -> str:
    doc = case["docs"]["MTX"]
    labels = {c["key"]: c["label"].split(" (")[0] for c in case["conditions"]}
    paras = []
    for t in case["tests"]:
        conds = ", ".join(labels[k] for k, v in t["n"].items() if v)
        ref = t["mtx_spec"] if t.get("mtx_spec") else (t["spec"] if t["spec"] != "N/A" else "see PRS")
        paras.append(f"Test instruction for {t['name']}: {t['method']} — {t['method_title']}. "
                     f"Spec reference {ref}. Run under: {conds}.")
    return "\n".join(["<!-- page 1 -->", title_block(case, doc, "APPROVED"), "", "<!-- page 2 -->",
                      "## 3 Test methods", "", "\n\n".join(paras), ""])


def prs_prose_c(case: dict, rev: str, status: str, superseded: bool) -> str:
    doc = dict(case["docs"]["PRS"], rev=rev)
    paras = []
    for i, t in enumerate(case["tests"]):
        spec, acc = t["spec"], t["acceptance"]
        if superseded and t.get("superseded"):
            spec, acc = t["superseded"]["spec"], t["superseded"]["acceptance"]
        paras.append(PROSE_C_PRS[(i + 2) % 3].format(req_id=t["req_id"], name=t["name"], type=t["type"].capitalize(),
                                                   type_low=t["type"], requirement=t["requirement"], spec=spec, acc=acc))
    prev = case["previous_model"]
    prev_p = " ".join(f"{name}: {value}." for name, value in prev["values"].items())
    return "\n".join([
        "<!-- page 1 -->", title_block(case, doc, status), "", "## 1 Scope", "",
        f"This specification defines the design inputs of the {case['product']}.", "",
        "<!-- page 2 -->", "## 4 Requirements", "", "\n\n".join(paras), "",
        "<!-- page 3 -->", f"## Appendix B Previous model results ({prev['name']}, informative)", "", prev_p, "",
    ])


def mtx_prose_c(case: dict) -> str:
    doc = case["docs"]["MTX"]
    labels = {c["key"]: c["label"].split(" (")[0] for c in case["conditions"]}
    paras = []
    for t in case["tests"]:
        conds = ", ".join(labels[k] for k, v in t["n"].items() if v)
        ref = t["mtx_spec"] if t.get("mtx_spec") else (t["spec"] if t["spec"] != "N/A" else "see PRS")
        paras.append(PROSE_C_MTX.format(name=t["name"], method=t["method"], method_title=t["method_title"],
                                        ref=ref, conds=conds))
    return "\n".join(["<!-- page 1 -->", title_block(case, doc, "APPROVED"), "", "<!-- page 2 -->",
                      "## 3 Test methods", "", "\n\n".join(paras), ""])


def prs_prose(case: dict, rev: str, status: str, superseded: bool) -> str:
    doc = dict(case["docs"]["PRS"], rev=rev)
    paras = []
    for i, t in enumerate(case["tests"]):
        spec, acc = t["spec"], t["acceptance"]
        if superseded and t.get("superseded"):
            spec, acc = t["superseded"]["spec"], t["superseded"]["acceptance"]
        paras.append(PROSE_PRS[i % 3].format(req_id=t["req_id"], name=t["name"], type=t["type"].capitalize(),
                                             requirement=t["requirement"], spec=spec, acc=acc))
    prev = case["previous_model"]
    prev_p = " ".join(f"{name}: {value}." for name, value in prev["values"].items())
    return "\n".join([
        "<!-- page 1 -->", title_block(case, doc, status), "", "## 1 Scope", "",
        f"This specification defines the design inputs of the {case['product']}.", "",
        "<!-- page 2 -->", "## 4 Requirements", "", "\n\n".join(paras), "",
        "<!-- page 3 -->", f"## Appendix B Previous model results ({prev['name']}, informative)", "", prev_p, "",
    ])


def mtx_prose(case: dict) -> str:
    doc = case["docs"]["MTX"]
    labels = {c["key"]: c["label"].split(" (")[0] for c in case["conditions"]}
    paras = []
    for t in case["tests"]:
        conds = ", ".join(labels[k] for k, v in t["n"].items() if v)
        ref = t["mtx_spec"] if t.get("mtx_spec") else (t["spec"] if t["spec"] != "N/A" else "see PRS")
        paras.append(f"{t['name']}: performed per test instruction {t['method']} ({t['method_title']}). "
                     f"Reference specification: {ref}. Conditions: {conds}.")
    return "\n".join(["<!-- page 1 -->", title_block(case, doc, "APPROVED"), "", "<!-- page 2 -->",
                      "## 3 Test methods", "", "\n\n".join(paras), ""])


def mtx(case: dict) -> str:
    doc = case["docs"]["MTX"]
    labels = {c["key"]: c["label"].split(" (")[0] for c in case["conditions"]}
    rows = []
    for t in case["tests"]:
        conds = ", ".join(labels[k] for k, v in t["n"].items() if v)
        ref = t["mtx_spec"] if t.get("mtx_spec") else (t["spec"] if t["spec"] != "N/A" else "See PRS")
        rows.append([t["name"], t["method"], t["method_title"], ref, conds])
    return "\n".join([
        "<!-- page 1 -->",
        title_block(case, doc, "APPROVED"),
        "",
        "<!-- page 2 -->",
        "## 3 Test methods",
        "",
        md_table(["Test Name", "Test Instruction", "Method Title", "Specification (reference)", "Conditions"], rows),
        "",
    ])


def vp(case: dict) -> str:
    doc = case["docs"]["VP"]
    header = ["Test Name"] + [c["label"] for c in case["conditions"]]
    rows = []
    for t in case["tests"]:
        rows.append([t["name"]] + [str(t["n"][c["key"]]) if t["n"][c["key"]] else DASH for c in case["conditions"]])
    return "\n".join([
        "<!-- page 1 -->",
        title_block(case, doc, "APPROVED"),
        "",
        "<!-- page 2 -->",
        "## 7 Sample size",
        "",
        "Table 7-2 Sample size per test and condition",
        "",
        md_table(header, rows),
        "",
        f"Footnote: {DASH} = the test is not performed under this condition.",
        "",
    ])


def gold(case: dict) -> dict:
    docs = case["docs"]
    prs_loc = {"doc_id": docs["PRS"]["doc_id"], "rev": docs["PRS"]["rev"]}
    rows = []
    for c in case["conditions"]:
        for t in case["tests"]:
            n = t["n"][c["key"]]
            if not n:
                continue
            spec = t["spec"] if t["type"] == "variable" else "Pass/Fail: " + t["requirement"]
            acc = None if t["acceptance"] == "TBD" else t["acceptance"]
            rows.append({
                "condition": c["key"], "test_name": t["name"],
                "fields": {
                    "req_id": {"value": t["req_id"], "source": dict(prs_loc, row=t["name"])},
                    "specification": {"value": spec, "source": dict(prs_loc, row=t["name"])},
                    "n": {"value": n, "source": {"doc_id": docs["VP"]["doc_id"], "rev": docs["VP"]["rev"],
                                                 "row": t["name"], "column": c["label"]}},
                    "acceptance": {"value": acc, "status": "MISSING" if acc is None else "SOURCED",
                                   "source": dict(prs_loc, row=t["name"])},
                    "test_instruction": {"value": t["method"], "source": {"doc_id": docs["MTX"]["doc_id"],
                                                                           "rev": docs["MTX"]["rev"], "row": t["name"]}},
                },
            })
    conflicts = [{"test_name": t["name"], "field": "specification", "authoritative": t["spec"],
                  "other": t["mtx_spec"], "other_doc": docs["MTX"]["doc_id"]}
                 for t in case["tests"] if t.get("mtx_spec")]
    planted = {
        "attribute_tests": [t["name"] for t in case["tests"] if t["type"] == "attribute"],
        "missing_acceptance": [t["name"] for t in case["tests"] if t["acceptance"] == "TBD"],
        "superseded_differs": [t["name"] for t in case["tests"] if t.get("superseded")],
        "pattern_break_method": [t["name"] for t in case["tests"]
                                 if int(t["method"].rsplit("-", 1)[1]) > 100 or t["method"].endswith("087")],
        "previous_model_distractor": list(case["previous_model"]["values"]),
    }
    return {"case_id": case["case_id"], "product": case["product"],
            "conditions": case["conditions"], "rows": rows, "conflicts": conflicts, "planted": planted}


def manifest(case: dict, files: dict[str, str]) -> dict:
    docs = case["docs"]
    out = []
    for role in ("PRS", "MTX", "VP"):
        d = docs[role]
        out.append({"doc_id": d["doc_id"], "rev": d["rev"], "role": role, "status": "APPROVED",
                    "path": files[f"{role}@{d['rev']}"]})
    p = docs["PRS"]
    if p.get("superseded_rev"):
        out.append({"doc_id": p["doc_id"], "rev": p["superseded_rev"], "role": "PRS", "status": "SUPERSEDED",
                    "path": files[f"PRS@{p['superseded_rev']}"]})
    return {"case_id": case["case_id"], "product": case["product"], "documents": out}


def build() -> dict[str, bytes]:
    spec = json.loads((HERE / "spec.json").read_text(encoding="utf-8"))
    out: dict[str, bytes] = {}
    for case in spec["cases"]:
        base = f"cases/{case['case_id']}"
        d = case["docs"]
        for style in ("table", "prose", "proseB", "proseC"):
            prs_fn = {"table": prs, "prose": prs_prose, "proseB": prs_prose_b, "proseC": prs_prose_c}[style]
            mtx_fn = {"table": mtx, "prose": mtx_prose, "proseB": mtx_prose_b, "proseC": mtx_prose_c}[style]
            texts = {
                f"PRS@{d['PRS']['rev']}": prs_fn(case, d["PRS"]["rev"], "APPROVED", superseded=False),
                f"MTX@{d['MTX']['rev']}": mtx_fn(case),
                f"VP@{d['VP']['rev']}": vp(case),
            }
            if d["PRS"].get("superseded_rev"):
                texts[f"PRS@{d['PRS']['superseded_rev']}"] = prs_fn(case, d["PRS"]["superseded_rev"], "SUPERSEDED",
                                                                    superseded=True)
            files: dict[str, str] = {}
            for k, text in texts.items():
                role, rev = k.split("@")
                name = f"sources_{style}/{d[role]['doc_id']}_rev{rev}.md"
                files[k] = name
                out[f"{base}/{name}"] = (text.rstrip() + "\n").encode("utf-8")
            m = manifest(case, files)
            m["style"] = style
            out[f"{base}/manifest_{style}.json"] = (json.dumps(m, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        out[f"{base}/gold.json"] = (json.dumps(gold(case), ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    files = build()
    if args.check:
        bad = [p for p, data in files.items() if not (HERE / p).is_file() or (HERE / p).read_bytes() != data]
        print(json.dumps({"status": "MATCH" if not bad else "DIFFERS", "files": len(files), "differs": bad}))
        return 0 if not bad else 1
    for rel, data in files.items():
        path = HERE / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    lines = [f"{hashlib.sha256(d).hexdigest()}  {p}" for p, d in sorted(files.items())]
    (HERE / "cases" / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "WRITTEN", "files": len(files)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
