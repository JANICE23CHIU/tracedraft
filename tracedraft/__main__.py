"""TraceDraft CLI.

  python -m tracedraft demo                         # rule extractor on every case/style/selector, no model needed
  python -m tracedraft run --case K1 --style prose --selector fcea --adapter ollama --model qwen2.5:1.5b
  python -m tracedraft run ... --adapter hailo --base-url http://127.0.0.1:8000 --model <hailo model name>
  python -m tracedraft verifier-eval --case K1 --style prose --adapter ollama --llm-mode review
  python -m tracedraft build-docx --run runs/<run folder>
  python -m tracedraft ping --adapter ollama        # is the model server reachable?
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .contract import FieldContract
from .evaluate import mutations, score, verifier_metrics
from .infer import make_adapter
from .pipeline import extract_all, open_case, verify_all
from .report import render
from .runlog import RunDir, append_ledger, environment, read_ledger
from .select import Budget

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "synthetic" / "cases"
CONTRACT = ROOT / "contracts" / "test_protocol_v1.json"
TEMPLATE = ROOT / "templates" / "test_protocol_template.docx"


def _adapter(args, contract, which="extract"):
    name = args.adapter if which == "extract" else (args.verify_adapter or args.adapter)
    if name == "rule" and which == "verify":
        return None
    kw = {}
    if name in {"ollama", "hailo", "hailo-ollama"}:
        kw = {"model": args.model, "base_url": args.base_url, "num_ctx": args.num_ctx, "seed": args.seed,
              "prompt": getattr(args, "prompt", "v1")}
    if name == "relay":
        kw = {"folder": args.relay_dir}
    return make_adapter(name, contract, **kw)


def _progress(prefix):
    def cb(i, n, rec):
        if i == n or i % 10 == 0:
            print(f"  {prefix} {i}/{n}", flush=True)
    return cb


def cmd_run(args) -> int:
    contract = FieldContract.load(args.contract)
    case_dir = CASES / args.case
    gold = json.loads((case_dir / "gold.json").read_text(encoding="utf-8"))
    ctx = open_case(case_dir, args.style, contract)
    embedder = None
    if getattr(args, "dense", "none") != "none":
        from .embed import HashEmbedder, OllamaEmbedder
        embedder = HashEmbedder() if args.dense == "hash" else OllamaEmbedder(args.dense, args.base_url)
        ctx.store.use_dense(embedder)
    port = _adapter(args, contract, "extract")
    vport = _adapter(args, contract, "verify")
    budget = Budget(context=args.num_ctx)
    print(f"case {args.case} ({args.style}) rows={len(ctx.rows)} eligible={len(ctx.eligible)} budget={budget.evidence} tokens")
    records = extract_all(ctx, args.selector, port, budget, progress=_progress("extract"))
    records = verify_all(ctx, records, vport, args.llm_mode, progress=_progress("verify"))
    metrics = score(ctx, records, gold)
    label = f"{args.case}_{args.style}_{args.selector}_{args.adapter}_{args.prompt}"
    if args.adapter != "rule":
        label += "_" + args.model.replace(":", "-").replace("/", "-")
    if args.num_ctx != 2048:
        label += f"_ctx{args.num_ctx}"
    if embedder is not None:
        label += "_dense-" + embedder.name.replace(":", "-").replace("/", "-")
    run = RunDir.create(args.runs, label)
    meta = {"run_id": run.path.name, "case_id": args.case, "product": gold["product"], "style": args.style,
            "selector": args.selector, "adapter": args.adapter, "model": args.model if args.adapter != "rule" else None,
            "base_url": args.base_url, "verify_adapter": args.verify_adapter or args.adapter, "llm_mode": args.llm_mode,
            "num_ctx": args.num_ctx, "seed": args.seed, "budget_evidence_tokens": budget.evidence, "prompt": args.prompt,
            "snapshot": ctx.snapshot, "contract": contract.contract_id, "version": __version__, "env": environment(),
            "dense": embedder.name if embedder else None,
            "dense_seconds": round(embedder.seconds, 3) if embedder else 0.0}
    if args.adapter == "ollama":
        from .runlog import ollama_residency
        meta["ollama_residency"] = ollama_residency(args.base_url or "http://127.0.0.1:11434")
    run.write_json("config.json", meta)
    run.write_jsonl("records.jsonl", records)
    run.write_json("metrics.json", metrics)
    run.write_bytes("report.html", render(meta, metrics, records, ctx.store).encode("utf-8"))
    sha = run.seal()
    append_ledger(args.runs, {"run_id": run.path.name, "manifest_sha256": sha, **{k: meta[k] for k in (
        "case_id", "style", "selector", "adapter", "model", "verify_adapter", "llm_mode", "snapshot", "prompt",
        "num_ctx", "dense")},
        "P_hat": metrics["P_hat"], "value_accuracy": metrics["value_accuracy"],
        "citation_accuracy": metrics["citation_accuracy"], "packet_tokens_mean": metrics["packet_tokens_mean"]})
    print(json.dumps({"run": str(run.path), "P_hat": metrics["P_hat"], "value_accuracy": metrics["value_accuracy"],
                      "citation_accuracy": metrics["citation_accuracy"], "by_field": metrics["by_field"],
                      "packet_tokens_mean": metrics["packet_tokens_mean"], "status_counts": metrics["status_counts"]},
                     ensure_ascii=False, indent=1))
    return 0


def cmd_verifier_eval(args) -> int:
    contract = FieldContract.load(args.contract)
    case_dir = CASES / args.case
    gold = json.loads((case_dir / "gold.json").read_text(encoding="utf-8"))
    ctx = open_case(case_dir, args.style, contract)
    port = _adapter(args, contract, "verify") if args.llm_mode != "none" else None
    items = mutations(ctx, gold, seed=args.seed)
    if args.limit:
        items = items[: args.limit]
    vm = verifier_metrics(ctx, items, port, args.llm_mode, progress=_progress("verify"))
    run = RunDir.create(args.runs, f"verifier_{args.case}_{args.style}_{args.adapter}_{args.llm_mode}")
    run.write_json("config.json", {"case": args.case, "style": args.style, "adapter": args.adapter, "model": args.model,
                                   "llm_mode": args.llm_mode, "seed": args.seed, "snapshot": ctx.snapshot,
                                   "env": environment()})
    run.write_json("verifier_metrics.json", vm)
    sha = run.seal()
    append_ledger(args.runs, {"run_id": run.path.name, "manifest_sha256": sha, "kind": "verifier_eval",
                              "case_id": args.case, "style": args.style, "adapter": args.adapter, "model": args.model,
                              "llm_mode": args.llm_mode, "recall_det": vm["recall_det"], "recall_llm": vm["recall_llm"],
                              "recall_combined": vm["recall_combined"], "false_alarm_det": vm["false_alarm_det"],
                              "false_alarm_llm": vm["false_alarm_llm"], "false_alarm_combined": vm["false_alarm_combined"]})
    out = {k: v for k, v in vm.items() if k != "rows"}
    out["by_kind"] = {k: {kk: vv for kk, vv in v.items()} for k, v in vm["by_kind"].items()}
    print(json.dumps({"run": str(run.path), **out}, ensure_ascii=False, indent=1))
    return 0


def cmd_demo(args) -> int:
    contract = FieldContract.load(args.contract)
    rows = []
    for case_dir in sorted(p for p in CASES.iterdir() if p.is_dir()):
        gold = json.loads((case_dir / "gold.json").read_text(encoding="utf-8"))
        for style in ("table", "prose", "proseB", "proseC"):
            ctx = open_case(case_dir, style, contract)
            for selector in ("fcea", "topk"):
                recs = verify_all(ctx, extract_all(ctx, selector, make_adapter("rule", contract)), None, "none")
                m = score(ctx, recs, gold)
                rows.append({"case": case_dir.name, "style": style, "selector": selector, "P_hat": m["P_hat"],
                             "packet_tokens_mean": m["packet_tokens_mean"], "membership_ok": m["membership"]["missing_rows"] == 0
                             and m["membership"]["extra_rows"] == 0})
            vm = verifier_metrics(ctx, mutations(ctx, gold))
            rows.append({"case": case_dir.name, "style": style, "verifier": "rules only", "recall": vm["recall_det"],
                         "false_alarm": vm["false_alarm_det"],
                         "undecided_by_rules": {k: v["n"] - v["det"] for k, v in vm["by_kind"].items() if k != "correct" and v["n"] - v["det"]}})
    print(json.dumps(rows, ensure_ascii=False, indent=1))
    return 0


def cmd_build_docx(args) -> int:
    run = Path(args.run)
    meta = json.loads((run / "config.json").read_text(encoding="utf-8"))
    records = [json.loads(l) for l in (run / "records.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    from .docx_out import build_docx
    out = run.parent / f"{run.name}_protocol_DRAFT.docx"
    if out.exists():
        print(f"exists (create-only): {out}")
        return 2
    counts = build_docx(meta, records, out, TEMPLATE)
    print(json.dumps({"docx": str(out), **counts}))
    return 0


def cmd_menu(args) -> int:
    """Second output of the same records: an image-text menu (one card per test item). Create-only."""
    from .menu_out import build_menu, load_run
    run = Path(args.run)
    meta, records = load_run(run)
    out = run.parent / f"{run.name}_menu.html"
    if out.exists():
        print(f"exists (create-only): {out}")
        return 2
    out.write_text(build_menu(meta, records), encoding="utf-8")
    print(json.dumps({"menu": str(out), "items": len({r["test_name"] for r in records})}))
    return 0


def cmd_ping(args) -> int:
    import urllib.request
    port = _adapter(args, FieldContract.load(args.contract), "extract")
    url = getattr(port, "base_url", None)
    if not url:
        print("adapter has no server")
        return 0
    for path in ("/api/tags", "/hailo/v1/list", "/api/version"):
        try:
            with urllib.request.urlopen(url + path, timeout=5) as r:
                print(path, r.status, r.read(400).decode("utf-8", "replace"))
        except Exception as exc:  # noqa: BLE001
            print(path, "unreachable:", exc)
    return 0


def cmd_recheck(args) -> int:
    """Re-run the CURRENT deterministic verifier on the records of an earlier run (no model calls) and
    compare with the outcome stored at the time. Writes a new sealed run; never edits the old one."""
    from .verify import FLAG, PASS, deterministic_check
    src = Path(args.run)
    meta = json.loads((src / "config.json").read_text(encoding="utf-8"))
    records = [json.loads(l) for l in (src / "records.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    contract = FieldContract.load(args.contract)
    ctx = open_case(CASES / meta["case_id"], meta["style"], contract)
    if ctx.snapshot != meta["snapshot"]:
        print("SNAPSHOT_CHANGED: sources differ from the original run; refusing to compare")
        return 2
    table = {}
    for rec in records:
        truth = "correct" if rec.get("eval", {}).get("correct") else "wrong"
        before = (rec.get("det") or {}).get("outcome")
        after = deterministic_check(ctx.store, contract, rec, rec["field"], rec["claim"])
        key_ = f"{truth}|before={before}|after={after['outcome']}"
        table[key_] = table.get(key_, 0) + 1
        rec["det_recheck"] = after
    wrong = [r for r in records if not r.get("eval", {}).get("correct")]
    right = [r for r in records if r.get("eval", {}).get("correct")]
    summary = {
        "source_run": src.name, "records": len(records), "wrong": len(wrong), "correct": len(right),
        "wrong_flagged_before": sum(1 for r in wrong if (r.get("det") or {}).get("outcome") == FLAG),
        "wrong_flagged_after": sum(1 for r in wrong if r["det_recheck"]["outcome"] == FLAG),
        "wrong_passed_before": sum(1 for r in wrong if (r.get("det") or {}).get("outcome") == PASS),
        "wrong_passed_after": sum(1 for r in wrong if r["det_recheck"]["outcome"] == PASS),
        "correct_flagged_before": sum(1 for r in right if (r.get("det") or {}).get("outcome") == FLAG),
        "correct_flagged_after": sum(1 for r in right if r["det_recheck"]["outcome"] == FLAG),
        "transitions": dict(sorted(table.items())),
    }
    run = RunDir.create(args.runs, f"recheck_{src.name}")
    run.write_json("summary.json", summary)
    run.write_jsonl("records_rechecked.jsonl", records)
    sha = run.seal()
    append_ledger(args.runs, {"run_id": run.path.name, "manifest_sha256": sha, "kind": "verifier_recheck",
                              **{k: v for k, v in summary.items() if k != "transitions"}})
    print(json.dumps({"run": str(run.path), **summary}, ensure_ascii=False, indent=1))
    return 0


def cmd_optimize(args) -> int:
    from .policy_opt import field_objectives, pareto_policies
    contract = FieldContract.load(args.contract)
    table = field_objectives(args.runs, args.case, args.style, contract)
    if not table:
        print("no comparable extraction runs in the ledger for this case/style")
        return 1
    scales = {}
    if args.l_scale:
        # Hardware what-if: model time measured on THIS machine × a per-model factor for another machine.
        # The factors are assumptions supplied by the user; the output is labelled as such.
        for part in args.l_scale.split(","):
            m, f = part.rsplit("=", 1)
            scales[m.strip()] = "off" if f.strip() == "off" else float(f)
        for f_name in list(table):
            for key in list(table[f_name]):
                model = key.split("|")[1]
                if scales.get(model) == "off":       # model not available on that tier
                    del table[f_name][key]
                elif model in scales:
                    table[f_name][key]["l"] *= scales[model]
            if not table[f_name]:
                print(f"no configuration left for field {f_name} on tier {args.tier}")
                return 1
    front = pareto_policies(table, args.epsilon)
    out = {"case": args.case, "style": args.style, "epsilon_U": args.epsilon,
           "what_if_l_scale": scales or None, "tier": args.tier,
           "configs_per_field": {f: len(v) for f, v in table.items()},
           "field_objectives": table, "pareto_policies": front}
    run = RunDir.create(args.runs, f"policyopt_{args.case}_{args.style}" + (f"_whatif-{args.tier}" if scales else ""))
    run.write_json("policy_front.json", out)
    sha = run.seal()
    append_ledger(args.runs, {"run_id": run.path.name, "manifest_sha256": sha, "kind": "policy_optimisation",
                              "case_id": args.case, "style": args.style, "front_size": len(front),
                              "best_E": front[0]["E"] if front else None})
    print(json.dumps({"run": str(run.path), "configs_per_field": out["configs_per_field"],
                      "front_size": len(front), "front": front[:8]}, ensure_ascii=False, indent=1))
    return 0


def cmd_ratchet(args) -> int:
    """Hypervolume ratchet over extraction runs of one case/style, in ledger order.
    Each run's configuration (applied to every field) is a candidate x; its objective vector is
    (f1, f2, f3, f4) = (U/N, H/N, E/N, L/(N*L_cap)). Decisions are appended to the ledger; the archive is
    rebuilt from KEPT decisions only, so the ledger stays the single source of truth."""
    from .policy_opt import field_objectives
    from .ratchet import KEPT, decide, evaluator_id, hv
    contract = FieldContract.load(args.contract)
    ev = evaluator_id(args.contract)
    table = field_objectives(args.runs, args.case, args.style, contract)
    configs: dict[str, dict] = {}
    for f, by_key in table.items():
        for key, o in by_key.items():
            c = configs.setdefault(key, {"N": 0, "U": 0.0, "H": 0.0, "E": 0.0, "L": 0.0, "run_id": o["run_id"],
                                         "R": o.get("replications", 1)})
            c["N"] += o["n"]
            c["U"] += o["n"] * o["u"]
            c["H"] += o["n"] * o["h"]
            c["E"] += o["n"] * o["e"]
            c["L"] += o["n"] * o["l"]
    mine = [e for e in read_ledger(args.runs) if e.get("kind") == "ratchet_decision" and e.get("evaluator") == ev
            and e.get("case_id") == args.case and e.get("style") == args.style and e.get("epsilon_U") == args.epsilon
            and e.get("min_gain", 0.0) == args.min_gain]
    done = {e["candidate"] for e in mine}
    archive = [{"key": e["candidate"], "vec": e["vec"]} for e in mine if e.get("decision") == KEPT]
    order = [e.get("run_id") for e in read_ledger(args.runs)]
    out = []
    for key, c in sorted(configs.items(), key=lambda kv: order.index(kv[1]["run_id"])):
        if key in done:
            continue
        n = c["N"]
        vec = (round(c["U"] / n, 6), round(c["H"] / n, 6), round(c["E"] / n, 6),
               round(min(1.0, c["L"] / (n * args.l_cap)), 6))
        d = decide(archive, key, vec, u_rate=vec[0], epsilon=args.epsilon, min_gain=args.min_gain)
        entry = {"kind": "ratchet_decision", "evaluator": ev, "epsilon_U": args.epsilon, "min_gain": args.min_gain,
                 "case_id": args.case, "style": args.style, "candidate": key, "n_items": n, "replications": c["R"],
                 "source_run": c["run_id"], "vec": list(vec), "objectives": ["f1_U", "f2_H", "f3_E", "f4_L"],
                 "l_cap_seconds": args.l_cap, **{k: round(v, 6) if isinstance(v, float) else v for k, v in d.items()}}
        append_ledger(args.runs, entry)
        if d["decision"] == KEPT:
            archive.append({"key": key, "vec": list(vec)})
        out.append(entry)
    front_hv = hv([tuple(a["vec"]) for a in archive], (1.0, 1.0, 1.0, 1.0))
    # Layer switch: three non-KEPT decisions in a row → stop greedy proposals, do error analysis (L2)
    streak = 0
    for e in mine + out:
        streak = 0 if e.get("decision") == KEPT else streak + 1
    print(json.dumps({"evaluator": ev, "epsilon_U": args.epsilon, "min_gain": args.min_gain, "decisions": out, "archive": archive, "archive_hv": round(front_hv, 6),
                      "non_kept_streak": streak, "escalate_to_L2_error_analysis": streak >= 3},
                     ensure_ascii=False, indent=1))
    return 0


def cmd_ledger(args) -> int:
    for entry in read_ledger(args.runs):
        print(json.dumps(entry, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="tracedraft")
    p.add_argument("--contract", default=str(CONTRACT))
    p.add_argument("--runs", default=str(ROOT / "runs"))
    sub = p.add_subparsers(dest="cmd", required=True)

    def model_opts(sp):
        sp.add_argument("--case", default="K1")
        sp.add_argument("--style", default="prose", choices=["table", "prose", "proseB", "proseC"])
        sp.add_argument("--adapter", default="rule", choices=["rule", "ollama", "hailo", "relay"])
        sp.add_argument("--verify-adapter", default=None, choices=[None, "rule", "ollama", "hailo", "relay"])
        sp.add_argument("--model", default="qwen2.5:1.5b")
        sp.add_argument("--base-url", default=None)
        sp.add_argument("--num-ctx", type=int, default=2048)
        sp.add_argument("--seed", type=int, default=42)
        sp.add_argument("--relay-dir", default=str(ROOT / "relay"))
        sp.add_argument("--llm-mode", default="review", choices=["none", "review", "all"])
        sp.add_argument("--prompt", default="v1", choices=["v1", "v2", "v3"],
                        help="v1 full ids; v2 short evidence handles; v3 handles + contract cue words")

    r = sub.add_parser("run"); model_opts(r); r.add_argument("--selector", default="fcea", choices=["fcea", "topk"])
    r.add_argument("--dense", default="none",
                   help="embedding model for the third ranker, e.g. nomic-embed-text; 'hash' = test stand-in; 'none' = lexical only")
    r.set_defaults(fn=cmd_run)
    v = sub.add_parser("verifier-eval"); model_opts(v); v.add_argument("--limit", type=int, default=0)
    v.set_defaults(fn=cmd_verifier_eval)
    d = sub.add_parser("demo"); d.set_defaults(fn=cmd_demo)
    b = sub.add_parser("build-docx"); b.add_argument("--run", required=True); b.set_defaults(fn=cmd_build_docx)
    mn = sub.add_parser("menu"); mn.add_argument("--run", required=True); mn.set_defaults(fn=cmd_menu)
    g = sub.add_parser("ping"); model_opts(g); g.set_defaults(fn=cmd_ping)
    l = sub.add_parser("ledger"); l.set_defaults(fn=cmd_ledger)
    rc = sub.add_parser("recheck"); rc.add_argument("--run", required=True); rc.set_defaults(fn=cmd_recheck)
    op = sub.add_parser("optimize"); op.add_argument("--case", default="K1"); op.add_argument("--style", default="prose")
    op.add_argument("--epsilon", type=float, default=0.0, help="max wrong values allowed to pass the verifier (count)")
    op.add_argument("--l-scale", default="", help="what-if: model=factor,... multiplies measured model time per model")
    op.add_argument("--tier", default="measured", help="label for the hardware tier the scales describe")
    op.set_defaults(fn=cmd_optimize)
    ra = sub.add_parser("ratchet"); ra.add_argument("--case", default="K1"); ra.add_argument("--style", default="prose")
    ra.add_argument("--l-cap", type=float, default=10.0, help="seconds per field that count as f4 = 1 (fixed in advance)")
    ra.add_argument("--epsilon", type=float, default=0.0, help="max allowed U/N (wrong values let through)")
    ra.add_argument("--min-gain", type=float, default=0.0,
                    help="relative HV gain a candidate must exceed to be KEPT (fix it from replicate noise first)")
    ra.set_defaults(fn=cmd_ratchet)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
