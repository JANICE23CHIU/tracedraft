"""Self-contained HTML report for one run: metrics, then the review queue ordered by risk.

Interface: render(run_meta, metrics, records, store) -> str (HTML)
Every value from sources or models is HTML-escaped.
"""
from __future__ import annotations

import html
import json

CSS = """
:root{--bg:#f6f5f1;--s:#fff;--s2:#f0eee8;--ink:#1f2328;--ink2:#57606a;--line:#dcd8cf;--acc:#1f5f8b;
--bad:#b42318;--badbg:#fde8e6;--warn:#9a6700;--warnbg:#fff4d6;--ok:#1a7f37;--okbg:#e6f4ea;color-scheme:light}
@media(prefers-color-scheme:dark){:root{--bg:#15171a;--s:#1d2024;--s2:#25292e;--ink:#e6e8eb;--ink2:#9aa4ae;
--line:#343a40;--acc:#5aa7d9;--bad:#f47067;--badbg:#3d1a18;--warn:#e0b04a;--warnbg:#3a2f12;--ok:#56c271;--okbg:#173323;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 system-ui,"Microsoft JhengHei",sans-serif}
.w{max-width:1100px;margin:0 auto;padding:28px 18px 60px}h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:28px 0 10px}
.m{color:var(--ink2);font-size:13px}.g{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.st{background:var(--s);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.n{font-size:26px;font-weight:700}
.q{background:var(--s);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:8px 0}
.q.r3{border-left:5px solid var(--bad)}.q.r2{border-left:5px solid var(--warn)}.q.r1{border-left:5px solid var(--acc)}.q.r0{border-left:5px solid var(--ok)}
.b{display:inline-block;font-size:12px;padding:1px 8px;border-radius:999px;background:var(--s2);margin-right:4px}
.b.bad{background:var(--badbg);color:var(--bad)}.b.warn{background:var(--warnbg);color:var(--warn)}.b.ok{background:var(--okbg);color:var(--ok)}
.quote{border-left:3px solid var(--acc);padding:4px 10px;margin:6px 0;background:var(--s2);border-radius:0 6px 6px 0;font-size:14px;overflow-wrap:anywhere}
code{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;overflow-wrap:anywhere}
table{border-collapse:collapse;width:100%;font-size:14px;background:var(--s)}td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left}
"""


def e(x) -> str:
    return html.escape("" if x is None else str(x))


def render(meta: dict, metrics: dict, records: list[dict], store, limit: int = 60) -> str:
    q = sorted(records, key=lambda r: (-r.get("risk", 0), r["condition"], r["test_name"], r["field"]))
    flagged = sum(1 for r in records if r.get("risk", 0) >= 3)
    review = sum(1 for r in records if 2 <= r.get("risk", 0) < 3)
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>TraceDraft run {e(meta.get('run_id'))}</title><style>{CSS}</style></head><body><div class='w'>",
             f"<h1>TraceDraft — {e(meta.get('product'))}</h1>",
             f"<p class='m'>run <code>{e(meta.get('run_id'))}</code> · case {e(meta.get('case_id'))} · sources {e(meta.get('style'))} · "
             f"selector {e(meta.get('selector'))} · extractor {e(meta.get('adapter'))} · verifier {e(meta.get('verify_adapter'))} ({e(meta.get('llm_mode'))}) · "
             f"snapshot <code>{e(str(meta.get('snapshot'))[:16])}</code></p>",
             "<p class='m'>DRAFT FOR REVIEW. The verifier only orders human work; it approves nothing.</p>",
             "<div class='g'>"]
    for label, value in [("P̂ task correct completion", metrics.get("P_hat")), ("value accuracy", metrics.get("value_accuracy")),
                         ("citation accuracy", metrics.get("citation_accuracy")), ("mean packet tokens (est.)", metrics.get("packet_tokens_mean")),
                         ("flagged (risk ≥ 3)", flagged), ("needs review (2–3)", review)]:
        parts.append(f"<div class='st'><div class='n'>{e(value)}</div><div class='m'>{e(label)}</div></div>")
    parts.append("</div><h2>Review queue — highest risk first</h2>")
    for r in q[:limit]:
        c = r["claim"]
        risk = r.get("risk", 0)
        cls = "r3" if risk >= 3 else "r2" if risk >= 2 else "r1" if risk >= 1 else "r0"
        det = r.get("det") or {}
        llm = r.get("llm") or {}
        ev = r.get("eval") or {}
        seg = store.get(c.get("evidence_id") or "") if c.get("evidence_id") else None
        badges = [f"<span class='b'>{e(r['condition_label'])}</span>", f"<span class='b'>{e(r['field'])}</span>"]
        if det.get("outcome"):
            kind = "bad" if det["outcome"] == "FLAG" else "warn" if det["outcome"] in ("REVIEW", "MISSING") else "ok"
            badges.append(f"<span class='b {kind}'>rules: {e(det['outcome'])} {e(' '.join(det.get('codes', [])))}</span>")
        if llm.get("verdict"):
            kind = "ok" if llm["verdict"] == "SUPPORTED" else "bad"
            badges.append(f"<span class='b {kind}'>model: {e(llm['verdict'])}</span>")
        if ev:
            badges.append(f"<span class='b {'ok' if ev.get('correct') else 'bad'}'>gold: {'correct' if ev.get('correct') else 'wrong'}</span>")
        parts.append(f"<div class='q {cls}'><div><b>{e(r['test_name'])}</b> · risk {risk}</div><div>{''.join(badges)}</div>"
                     f"<div>value: <b>{e(c.get('value')) or '[MISSING]'}</b> · cited <code>{e(c.get('evidence_id'))}</code></div>")
        if seg:
            parts.append(f"<div class='quote'><span class='m'>{e(seg['doc_id'])} rev {e(seg['rev'])} · p.{e(seg['page'])} · {e(seg['section'])}</span><br>{e(seg['text'])}</div>")
        if c.get("conflict"):
            parts.append(f"<div class='m'>conflict: {e(c['conflict'])}</div>")
        parts.append("</div>")
    if len(q) > limit:
        parts.append(f"<p class='m'>{len(q) - limit} more items in records.jsonl.</p>")
    parts.append("<h2>Metrics (JSON)</h2><pre class='m'>" + e(json.dumps(metrics, indent=1, ensure_ascii=False)) + "</pre>")
    parts.append("</div></body></html>")
    return "".join(parts)
