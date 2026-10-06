"""Image-text menu (圖文選單) — the second output of the same extracted records.

The .docx adapter fills a fixed document; this adapter turns the same records into a browsable card menu:
one card per test item, a generated pictogram, the extracted fields with their verification status, and the
source clause behind every value. Nothing is re-extracted; the menu is a view over records.jsonl.

Interface:
    html = build_menu(meta, records) -> str        (self-contained HTML, no external assets)

Rules carried over from the verifier:
  - status per field = the highest risk over the conditions it was extracted under
  - a per-test field whose value differs between conditions is shown as INCONSISTENT (needs a person)
  - every value and quote is HTML-escaped; pictograms are generated SVG, never fetched
"""
from __future__ import annotations

import hashlib
import html
import json

PER_TEST = ("req_id", "specification", "acceptance", "test_instruction")
LABEL = {"req_id": "Requirement ID", "specification": "Specification", "acceptance": "Acceptance",
         "test_instruction": "Test instruction", "n": "Sample size"}


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def _status(rec: dict) -> str:
    det = (rec.get("det") or {}).get("outcome")
    r = rec.get("risk", 0) or 0
    if det == "MISSING":
        return "missing"
    if r >= 3:
        return "flag"
    if r >= 2:
        return "review"
    return "ok"


_RANK = {"ok": 0, "missing": 1, "review": 2, "flag": 3, "inconsistent": 2}
_TEXT = {"ok": "verified by rules", "missing": "blank — fill in", "review": "needs review",
         "flag": "flagged", "inconsistent": "differs between conditions"}


def _glyph(name: str, kind: str) -> str:
    """Deterministic pictogram: hue from the test name, shape from the requirement type."""
    h = int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:6], 16) % 360
    initials = "".join(w[0] for w in name.split()[:2]).upper()
    if kind == "attribute":
        mark = "<path d='M18 33 l7 7 l14 -16' fill='none' stroke='#fff' stroke-width='5' stroke-linecap='round' stroke-linejoin='round'/>"
    elif kind == "unknown":
        mark = "<text x='30' y='38' font-size='24' text-anchor='middle' fill='#fff' font-family='system-ui'>?</text>"
    else:
        mark = ("<path d='M14 40 A18 18 0 0 1 46 40' fill='none' stroke='#fff' stroke-width='4' stroke-linecap='round'/>"
                "<path d='M30 40 L40 26' stroke='#fff' stroke-width='4' stroke-linecap='round'/>")
    return (f"<svg viewBox='0 0 60 60' width='60' height='60' role='img' aria-label='{_e(kind)} test'>"
            f"<rect width='60' height='60' rx='12' fill='hsl({h} 45% 42%)'/>{mark}"
            f"<text x='30' y='56' font-size='9' text-anchor='middle' fill='#fff' font-family='system-ui'>{_e(initials)}</text></svg>")


def _cards(records: list[dict]) -> list[dict]:
    tests: dict[str, dict] = {}
    order: list[str] = []
    for r in records:
        t = r["test_name"]
        if t not in tests:
            tests[t] = {"name": t, "fields": {}, "n": [], "conditions": []}
            order.append(t)
        card = tests[t]
        if r["field"] == "n":
            card["n"].append(r)
            continue
        card["fields"].setdefault(r["field"], []).append(r)
    out = []
    for t in order:
        c = tests[t]
        fields = {}
        for f in PER_TEST:
            recs = c["fields"].get(f, [])
            if not recs:
                continue
            values = {str(x["claim"].get("value") or "") for x in recs}
            st = max((_status(x) for x in recs), key=_RANK.get)
            if len(values) > 1:
                st = max(st, "inconsistent", key=_RANK.get)
            best = min(recs, key=lambda x: _RANK[_status(x)])
            worst_n = sum(1 for x in recs if _status(x) == st) if st != "inconsistent" else len(recs)
            fields[f] = {"status": st, "of": f"{worst_n}/{len(recs)}" if len(recs) > 1 and st != "ok" else "",
                         "value": best["claim"].get("value"), "values": sorted(values),
                         "evidence_id": best["claim"].get("evidence_id"), "quote": best["claim"].get("quote"),
                         "codes": sorted({code for x in recs for code in (x.get("det") or {}).get("codes", [])})}
        spec = str((fields.get("specification") or {}).get("value") or "")
        kind = "attribute" if spec.startswith("Pass/Fail") else ("variable" if spec else "unknown")
        n_rows = [{"condition": x.get("condition_label") or x["condition"], "value": x["claim"].get("value"),
                   "status": _status(x), "evidence_id": x["claim"].get("evidence_id")} for x in c["n"]]
        worst = max([f["status"] for f in fields.values()] + [x["status"] for x in n_rows] or ["ok"], key=_RANK.get)
        out.append({"name": t, "kind": kind, "fields": fields, "n": n_rows, "status": worst})
    return out


CSS = """
:root{--bg:#f6f5f1;--s:#fff;--s2:#f0eee8;--ink:#1f2328;--ink2:#57606a;--line:#dcd8cf;--acc:#1f5f8b;
--bad:#b42318;--badbg:#fde8e6;--warn:#9a6700;--warnbg:#fff4d6;--ok:#1a7f37;--okbg:#e6f4ea;--mis:#57606a;--misbg:#eceae4}
@media(prefers-color-scheme:dark){:root{--bg:#15171a;--s:#1d2024;--s2:#25292e;--ink:#e6e8eb;--ink2:#9aa4ae;--line:#343a40;
--acc:#5aa7d9;--bad:#f47067;--badbg:#3d1a18;--warn:#e0b04a;--warnbg:#3a2f12;--ok:#56c271;--okbg:#173323;--mis:#9aa4ae;--misbg:#2a2e33}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,"Microsoft JhengHei",sans-serif}
.w{max-width:1180px;margin:0 auto;padding:24px 16px 60px}h1{font-size:22px;margin:0 0 4px}.m{color:var(--ink2);font-size:13px}
.bar{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}.bar button,.bar input{font:inherit;padding:6px 12px;border:1px solid var(--line);
border-radius:999px;background:var(--s);color:var(--ink);cursor:pointer}.bar input{border-radius:8px;min-width:200px;cursor:text}
.bar button[aria-pressed=true]{background:var(--acc);color:#fff;border-color:var(--acc)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.card{background:var(--s);border:1px solid var(--line);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:8px}
.card.flag{border-top:4px solid var(--bad)}.card.review,.card.inconsistent{border-top:4px solid var(--warn)}
.card.missing{border-top:4px solid var(--mis)}.card.ok{border-top:4px solid var(--ok)}
.hd{display:flex;gap:12px;align-items:center}.hd h2{font-size:16px;margin:0}.f{border-top:1px solid var(--line);padding-top:6px}
.f b{font-size:12px;color:var(--ink2);font-weight:600;display:block}.v{overflow-wrap:anywhere}
.b{display:inline-block;font-size:11.5px;padding:1px 8px;border-radius:999px;margin-left:4px;white-space:nowrap}
.b.ok{background:var(--okbg);color:var(--ok)}.b.flag{background:var(--badbg);color:var(--bad)}
.b.review,.b.inconsistent{background:var(--warnbg);color:var(--warn)}.b.missing{background:var(--misbg);color:var(--mis)}
details{font-size:13px;color:var(--ink2)}summary{cursor:pointer}.q{border-left:3px solid var(--acc);padding:4px 8px;margin:4px 0;
background:var(--s2);overflow-wrap:anywhere}code{font-family:ui-monospace,Consolas,monospace;font-size:12px;overflow-wrap:anywhere}
table{border-collapse:collapse;width:100%;font-size:13px}td{border-bottom:1px solid var(--line);padding:3px 4px}
"""

JS = """
(function(){var q=document.getElementById('q'),bs=document.querySelectorAll('[data-filter]'),f='all';
function apply(){var t=(q.value||'').toLowerCase();document.querySelectorAll('.card').forEach(function(c){
var okf=f==='all'||(f==='attention'?c.dataset.status!=='ok':c.dataset.status==='ok');
var okt=!t||c.dataset.text.indexOf(t)>=0;c.hidden=!(okf&&okt);});}
bs.forEach(function(b){b.addEventListener('click',function(){f=b.dataset.filter;bs.forEach(function(x){
x.setAttribute('aria-pressed',x===b?'true':'false')});apply();});});q.addEventListener('input',apply);})();
"""


def build_menu(meta: dict, records: list[dict]) -> str:
    cards = _cards(records)
    need = sum(1 for c in cards if c["status"] != "ok")
    parts = ["<!doctype html><html lang='en'><head><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width,initial-scale=1'>",
             f"<title>{_e(meta.get('product'))} — test menu</title><style>{CSS}</style></head><body><div class='w'>",
             f"<h1>{_e(meta.get('product'))} — test item menu</h1>",
             f"<p class='m'>Run <code>{_e(meta.get('run_id'))}</code> · {len(cards)} items · {need} need a person · "
             f"model {_e(meta.get('model') or meta.get('adapter'))} · every value links to the clause it was copied from. "
             f"Draft for human review; nothing here is approved.</p>",
             "<div class='bar' role='toolbar'><button data-filter='all' aria-pressed='true'>All</button>"
             "<button data-filter='attention' aria-pressed='false'>Needs a person</button>"
             "<button data-filter='ok' aria-pressed='false'>Verified by rules</button>"
             "<input id='q' type='search' placeholder='Search test, value, source…' aria-label='Search'></div>",
             "<div class='grid'>"]
    for c in cards:
        text = " ".join([c["name"]] + [str(f["value"] or "") for f in c["fields"].values()] +
                        [str(f["evidence_id"] or "") for f in c["fields"].values()]).lower()
        parts.append(f"<article class='card {c['status']}' data-status='{c['status']}' data-text='{_e(text)}'>")
        parts.append(f"<div class='hd'>{_glyph(c['name'], c['kind'])}<div><h2>{_e(c['name'])}</h2>"
                     f"<span class='m'>{_e(c['kind'] if c['kind'] != 'unknown' else 'type not extracted')}"
                     f"{' requirement' if c['kind'] != 'unknown' else ''}</span>"
                     f"<span class='b {c['status']}'>{_e(_TEXT[c['status']])}</span></div></div>")
        for f in PER_TEST:
            if f not in c["fields"]:
                continue
            x = c["fields"][f]
            val = x["value"] if x["value"] not in (None, "") else "—"
            of = f" · {x['of']} conditions" if x["of"] else ""
            parts.append(f"<div class='f'><b>{_e(LABEL[f])}<span class='b {x['status']}'>{_e(_TEXT[x['status']] + of)}</span></b>"
                         f"<div class='v'>{_e(val)}</div>")
            extra = ""
            if len(x["values"]) > 1:
                extra = "<div>Values by condition: " + "; ".join(_e(v or "—") for v in x["values"]) + "</div>"
            codes = f"<div>Checks: <code>{_e(', '.join(x['codes']))}</code></div>" if x["codes"] else ""
            if x["evidence_id"] or extra or codes:
                parts.append(f"<details><summary>Source <code>{_e(x['evidence_id'] or 'none')}</code></summary>"
                             f"{'<div class=q>' + _e(x['quote']) + '</div>' if x['quote'] else ''}{extra}{codes}</details>")
            parts.append("</div>")
        if c["n"]:
            rows = "".join(f"<tr><td>{_e(n['condition'])}</td><td>{_e(n['value'] if n['value'] not in (None, '') else '—')}</td>"
                           f"<td><span class='b {n['status']}'>{_e(_TEXT[n['status']])}</span></td></tr>" for n in c["n"])
            parts.append(f"<div class='f'><b>{_e(LABEL['n'])}</b><table>{rows}</table></div>")
        parts.append("</article>")
    parts.append(f"</div></div><script>{JS}</script></body></html>")
    return "".join(parts)


def load_run(run_dir) -> tuple[dict, list[dict]]:
    from pathlib import Path
    run = Path(run_dir)
    meta = json.loads((run / "config.json").read_text(encoding="utf-8"))
    recs = [json.loads(line) for line in (run / "records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return meta, recs
