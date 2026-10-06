"""TraceDraft tests — stdlib unittest (no pytest needed).  Run: python -m unittest discover -s tests -v"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from tracedraft.contract import FieldContract  # noqa: E402
from tracedraft.evaluate import mutations, score, verifier_metrics  # noqa: E402
from tracedraft.infer import OllamaAdapter, RelayAdapter, RuleAdapter, extract_prompt  # noqa: E402
from tracedraft.pipeline import extract_all, open_case, verify_all  # noqa: E402
from tracedraft.runlog import RunDir  # noqa: E402
from tracedraft.select import Budget, select  # noqa: E402
from tracedraft.textnorm import est_tokens, key  # noqa: E402

CASES = ROOT / "data" / "synthetic" / "cases"
C = FieldContract.load(ROOT / "contracts" / "test_protocol_v1.json")


def gold(case):
    return json.loads((CASES / case / "gold.json").read_text(encoding="utf-8"))


class DataTests(unittest.TestCase):
    def test_generator_is_reproducible(self):
        r = subprocess.run([sys.executable, "-B", str(ROOT / "data/synthetic/generate.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_no_third_party_material(self):
        banned = ["shl", "molly", "liufu", "scandinavian health", "ardentec", "欣銓", "harnesskb", "v16"]
        for p in ROOT.rglob("*"):
            if p.is_file() and p.suffix in {".md", ".json", ".py", ".txt", ".bat", ".sh", ".html"} \
                    and "runs" not in p.parts and p.name != "test_tracedraft.py":
                text = p.read_text(encoding="utf-8", errors="ignore").lower()
                for word in banned:
                    if word == "shl":
                        self.assertNotRegex(text, r"\bshl\b", p)
                    else:
                        self.assertNotIn(word, text, p)


class StoreAndContractTests(unittest.TestCase):
    def test_eligibility_excludes_superseded_and_informative(self):
        for case in ("K1", "F2"):
            for style in ("table", "prose", "proseB", "proseC"):
                ctx = open_case(CASES / case, style, C)
                for seg in ctx.store.all():
                    ok, why = C.eligible(seg)
                    if seg["status"] == "SUPERSEDED":
                        self.assertFalse(ok)
                    if "informative" in (seg["section"] or ""):
                        self.assertFalse(ok)

    def test_membership_matches_gold(self):
        for case in ("K1", "F2"):
            g = {(r["condition"], key(r["test_name"])) for r in gold(case)["rows"]}
            for style in ("table", "prose", "proseB", "proseC"):
                ctx = open_case(CASES / case, style, C)
                self.assertEqual({(r["condition"], key(r["test_name"])) for r in ctx.rows}, g)

    def test_snapshot_is_stable(self):
        a = open_case(CASES / "K1", "table", C).snapshot
        b = open_case(CASES / "K1", "table", C).snapshot
        self.assertEqual(a, b)


class SelectionTests(unittest.TestCase):
    def test_packets_respect_budget_and_fcea_is_smaller(self):
        budget = Budget()
        for style in ("table", "prose"):
            ctx = open_case(CASES / "K1", style, C)
            for row in ctx.rows[:6]:
                for field in C.fields:
                    f = select("fcea", ctx.store, C, field, row, ctx.eligible, budget)
                    t = select("topk", ctx.store, C, field, row, ctx.eligible, budget)
                    self.assertLessEqual(f.cost, budget.evidence)
                    self.assertLessEqual(t.cost, budget.evidence)
                    self.assertLessEqual(f.cost, t.cost)
                    self.assertEqual(f.needs_review, [], (row, field["name"], f.coverage))
                    for eid in f.evidence_ids + t.evidence_ids:
                        self.assertIn(eid, ctx.eligible)

    def test_prompt_overhead_fits_reserved_budget(self):
        for field in C.fields:
            task = {"field": field["name"], "field_label": field["label"], "test_name": "Temperature hold accuracy",
                    "condition_label": "Humid (35 °C / 85 % RH)", "rules": field["rules"], "evidence": []}
            task["cues"] = field.get("cues", [])
            for variant in ("v1", "v2", "v3"):
                system, user = extract_prompt(task, variant)
                self.assertLessEqual(est_tokens(system + user), Budget().prompt_overhead)


class PipelineTests(unittest.TestCase):
    def test_rule_extractor_is_perfect_on_tables(self):
        for case in ("K1", "F2"):
            ctx = open_case(CASES / case, "table", C)
            for sel in ("fcea", "topk"):
                m = score(ctx, extract_all(ctx, sel, RuleAdapter(C)), gold(case))
                self.assertEqual(m["P_hat"], 1.0, (case, sel, m))
                self.assertGreaterEqual(m["conflicts_reported_any_condition"], 1)

    def test_rule_extractor_cannot_read_prose(self):
        ctx = open_case(CASES / "K1", "prose", C)
        m = score(ctx, extract_all(ctx, "fcea", RuleAdapter(C)), gold("K1"))
        self.assertLess(m["P_hat"], 0.5)
        self.assertEqual(m["by_field"]["n"], 1.0)  # the plan stays a table in both styles

    def test_verifier_rules_catch_every_table_error_without_false_alarms(self):
        for case in ("K1", "F2"):
            ctx = open_case(CASES / case, "table", C)
            vm = verifier_metrics(ctx, mutations(ctx, gold(case)))
            self.assertEqual(vm["recall_det"], 1.0)
            self.assertEqual(vm["false_alarm_det"], 0.0)

    def test_verifier_rules_leave_paraphrase_errors_to_the_model_on_prose(self):
        ctx = open_case(CASES / "K1", "prose", C)
        vm = verifier_metrics(ctx, mutations(ctx, gold("K1")))
        self.assertEqual(vm["false_alarm_det"], 0.0)
        self.assertLess(vm["recall_det"], 1.0)  # unit swaps etc. are undecidable by rules -> REVIEW


class ClauseTests(unittest.TestCase):
    def test_clause_anchoring_catches_the_failures_seen_on_the_laptop(self):
        # 2026-10-04 laptop run: right passage, wrong clause / partial copy / TBD filled in -> verifier said PASS.
        for case in ("K1", "F2"):
            ctx = open_case(CASES / case, "prose", C)
            vm = verifier_metrics(ctx, mutations(ctx, gold(case)))
            for kind in ("wrong_clause", "partial_copy", "tbd_filled_from_other_clause", "invented_value",
                         "attribute_rule_not_applied"):
                k = vm["by_kind"][kind]
                self.assertEqual(k["det"], k["n"], (case, kind, k))
            self.assertEqual(vm["false_alarm_det"], 0.0)

    def test_held_out_phrasing_has_no_false_alarms(self):
        for case in ("K1", "F2"):
            ctx = open_case(CASES / case, "proseB", C)
            self.assertEqual(verifier_metrics(ctx, mutations(ctx, gold(case)))["false_alarm_det"], 0.0)

    def test_short_handles_map_back_to_evidence_ids(self):
        from tracedraft.infer import extract_prompt, map_handle
        task = {"field": "test_instruction", "field_label": "Test Instruction", "test_name": "Boil time",
                "condition_label": "Standard (23 °C)", "rules": [], "cues": ["test instruction"],
                "evidence": [{"evidence_id": "TMX-NK1-002@A:p2:s2", "text": "x"}, {"evidence_id": "PRS@B:p2:s3", "text": "y"}]}
        system, user = extract_prompt(task, "v2")
        self.assertIn("[E1] x", user)
        self.assertNotIn("TMX-NK1-002", user)
        self.assertEqual(map_handle(task, "E2"), "PRS@B:p2:s3")
        self.assertEqual(map_handle(task, "[e1]"), "TMX-NK1-002@A:p2:s2")
        self.assertIn("'test instruction'", extract_prompt(task, "v3")[1])


class _FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        user = body["messages"][1]["content"]
        assert body["options"]["num_ctx"] == 2048 and body["options"]["temperature"] == 0
        if user.startswith("Test:"):
            content = '{"verdict": "NOT_SUPPORTED", "reason": "unit differs"}'
        else:
            eid = user.split("[", 1)[1].split("]", 1)[0]
            content = '```json\n{"value": "30", "evidence_id": "%s", "quote": "30", "status": "SOURCED"}\n```' % eid
        data = json.dumps({"message": {"content": content}, "prompt_eval_count": 321, "eval_count": 22}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class AdapterTests(unittest.TestCase):
    def test_ollama_protocol_with_fake_server(self):
        server = HTTPServer(("127.0.0.1", 0), _FakeOllama)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            port = OllamaAdapter(base_url=f"http://127.0.0.1:{server.server_address[1]}")
            ctx = open_case(CASES / "K1", "table", C)
            row = next(r for r in ctx.rows if r["test_name"] == "Boil time")
            p = select("fcea", ctx.store, C, C.field("n"), row, ctx.eligible, Budget())
            from tracedraft.pipeline import make_task
            out = port.extract(make_task(ctx, row, C.field("n"), p))
            self.assertEqual(out["value"], 30)
            self.assertEqual(out["meta"]["prompt_eval_count"], 321)
            v = port.verify({"task_id": "x", "test_name": "Boil time", "condition_label": "Standard (23 °C)",
                             "field": "n", "field_label": "Sample size"}, {"value": 30, "evidence_id": "a", "quote": "b"})
            self.assertEqual(v["verdict"], "NOT_SUPPORTED")
        finally:
            server.shutdown()

    def test_unreachable_server_is_an_error_record_not_a_crash(self):
        port = OllamaAdapter(base_url="http://127.0.0.1:9", timeout=2)
        out = port.extract({"field": "n", "field_label": "n", "test_name": "x", "condition_label": "y",
                            "rules": [], "evidence": [], "task_id": "t"})
        self.assertEqual(out["status"], "ERROR")

    def test_relay_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            task = {"task_id": "standard|Boil time|n", "field": "n", "field_label": "Sample size", "test_name": "Boil time",
                    "condition_label": "Standard (23 °C)", "rules": [], "evidence": []}
            self.assertEqual(RelayAdapter(td).extract(task)["status"], "PENDING_RELAY")
            self.assertTrue((Path(td) / "outbox.jsonl").is_file())
            (Path(td) / "inbox.jsonl").write_text(json.dumps({"task_id": "standard|Boil time|n:extract", "value": 30,
                                                              "evidence_id": "e", "status": "SOURCED"}) + "\n", encoding="utf-8")
            self.assertEqual(RelayAdapter(td).extract(task)["value"], 30)


class RunlogTests(unittest.TestCase):
    def test_create_only_and_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            run = RunDir.create(td, "x")
            run.write_json("a.json", {"a": 1})
            with self.assertRaises(FileExistsError):
                run.write_json("a.json", {"a": 2})
            run.seal()
            self.assertIn("a.json", (run.path / "MANIFEST.sha256").read_text())

    def test_docx_build(self):
        try:
            import docx  # noqa: F401
        except ImportError:
            self.skipTest("python-docx not installed")
        from tracedraft.docx_out import build_docx
        ctx = open_case(CASES / "F2", "table", C)
        recs = verify_all(ctx, extract_all(ctx, "fcea", RuleAdapter(C)))
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "p.docx"
            counts = build_docx({"product": "Orbit F2 Desk Fan", "case_id": "F2", "run_id": "t", "snapshot": ctx.snapshot},
                                recs, out, ROOT / "templates" / "test_protocol_template.docx")
            self.assertTrue(out.is_file())
            self.assertEqual(counts["cells"], len(recs))
            self.assertGreaterEqual(counts["red"], 2)  # MISSING acceptance + conflict


class HybridIndexTests(unittest.TestCase):
    def test_dense_ranker_is_a_third_list_inside_the_eligible_set(self):
        from tracedraft.embed import HashEmbedder
        ctx = open_case(CASES / "K1", "prose", C)
        ctx.store.use_dense(HashEmbedder())
        ranks = ctx.store.rank("Boil time Specification", ctx.eligible)
        self.assertEqual(set(ranks), {"bm25", "trigram", "dense"})
        self.assertTrue(set(ranks["dense"]) <= ctx.eligible)
        self.assertTrue(ranks["dense"])

    def test_config_key_separates_context_and_dense(self):
        from tracedraft.policy_opt import _config_key
        a = _config_key({"adapter": "ollama", "model": "m", "selector": "fcea", "prompt": "v2", "llm_mode": "review"})
        b = _config_key({"adapter": "ollama", "model": "m", "selector": "fcea", "prompt": "v2", "llm_mode": "review",
                         "num_ctx": 8192})
        c = _config_key({"adapter": "ollama", "model": "m", "selector": "fcea", "prompt": "v2", "llm_mode": "review",
                         "dense": "nomic-embed-text"})
        self.assertEqual(len({a, b, c}), 3)


class MenuTests(unittest.TestCase):
    def test_menu_escapes_and_marks_inconsistent(self):
        from tracedraft.menu_out import build_menu
        base = {"condition": "a", "condition_label": "A", "test_name": "Boil <time>", "risk": 0.0,
                "det": {"outcome": "PASS", "codes": []}}
        recs = [dict(base, field="specification", claim={"value": "≤ 240 s", "evidence_id": "X@A:p1:s1", "quote": "<b>q</b>"}),
                dict(base, condition="b", field="specification",
                     claim={"value": "≤ 250 s", "evidence_id": "X@A:p1:s2", "quote": "q2"}),
                dict(base, field="n", claim={"value": 30, "evidence_id": "V@A:p1:t1:r1"})]
        out = build_menu({"product": "P", "run_id": "r"}, recs)
        self.assertIn("Boil &lt;time&gt;", out)
        self.assertNotIn("<b>q</b>", out)
        self.assertIn("differs between conditions", out)
        self.assertIn("<svg", out)
        self.assertNotIn("http", out.replace("http-equiv", ""))


class RatchetTests(unittest.TestCase):
    def test_hypervolume_and_decisions(self):
        from tracedraft.ratchet import DISCARDED, DUP_CAND, DUP_OBJ, KEPT, decide, hv
        ref = (1.0, 1.0)
        self.assertAlmostEqual(hv([(0.5, 0.5)], ref), 0.25)
        self.assertAlmostEqual(hv([(0.5, 0.5), (0.25, 0.75)], ref), 0.25 + 0.0625)
        self.assertAlmostEqual(hv([(0.5, 0.5), (0.6, 0.6)], ref), 0.25)  # dominated point adds nothing
        self.assertAlmostEqual(hv([(0.5, 0.5, 0.5, 0.5)], (1, 1, 1, 1)), 0.0625)
        arch = [{"key": "a", "vec": [0.5, 0.5, 0.5, 0.5]}]
        ref4 = (1.0, 1.0, 1.0, 1.0)
        self.assertEqual(decide(arch, "b", (0.4, 0.5, 0.5, 0.5), ref=ref4)["decision"], KEPT)
        self.assertEqual(decide(arch, "c", (0.6, 0.6, 0.6, 0.6), ref=ref4)["decision"], DISCARDED)
        self.assertEqual(decide(arch, "a", (0.1, 0.1, 0.1, 0.1), ref=ref4)["decision"], DUP_CAND)
        self.assertEqual(decide(arch, "d", (0.5, 0.5, 0.5, 0.5), ref=ref4)["decision"], DUP_OBJ)
        self.assertEqual(decide(arch, "f", (0.5, 0.49, 0.5, 0.5), ref=ref4, min_gain=0.03)["decision"], DISCARDED)
        self.assertEqual(decide(arch, "g", (0.0, 0.3, 0.3, 0.5), ref=ref4, min_gain=0.03)["decision"], KEPT)
        from tracedraft.ratchet import INFEASIBLE
        self.assertEqual(decide(arch, "e", (0.01, 0.1, 0.1, 0.1), ref=ref4, u_rate=0.01, epsilon=0.0)["decision"],
                         INFEASIBLE)

    def test_unanchored_high_risk_value_goes_to_review(self):
        from tracedraft.pipeline import open_case
        from tracedraft.verify import deterministic_check
        ctx = open_case(CASES / "K1", "proseB", C)
        row = {"test_name": "Boil time", "condition_label": "standard"}
        claim = {"value": "240 s", "evidence_id": "PRS-NK1-001@B:p2:s3", "status": "SOURCED"}
        self.assertEqual(deterministic_check(ctx.store, C, row, "acceptance", claim)["codes"], ["UNANCHORED_HIGH_RISK"])

    def test_model_cannot_clear_review_on_high_risk_field(self):
        from tracedraft.verify import risk
        det = {"outcome": "REVIEW", "codes": ["PARAPHRASE_NUMBERS_PRESENT"]}
        self.assertGreaterEqual(risk(det, {"verdict": "SUPPORTED"}, {"high_risk": True}), 2)
        self.assertLess(risk(det, {"verdict": "SUPPORTED"}, {"high_risk": False}), 2)


class PolicyOptTests(unittest.TestCase):
    def test_exact_front_on_a_toy_table(self):
        from tracedraft.policy_opt import pareto_policies
        table = {"a": {"x": {"n": 10, "e": 0.1, "l": 1.0, "h": 0.2, "u": 0.0},
                       "y": {"n": 10, "e": 0.3, "l": 0.1, "h": 0.2, "u": 0.0},
                       "z": {"n": 10, "e": 0.4, "l": 2.0, "h": 0.5, "u": 0.0}},   # dominated
                 "b": {"x": {"n": 5, "e": 0.0, "l": 1.0, "h": 0.0, "u": 0.2},     # violates eps=0
                       "y": {"n": 5, "e": 0.2, "l": 1.0, "h": 0.4, "u": 0.0}}}
        front = pareto_policies(table, epsilon=0.0)
        self.assertEqual({tuple(sorted(p["policy"].items())) for p in front},
                         {(("a", "x"), ("b", "y")), (("a", "y"), ("b", "y"))})
        self.assertTrue(all(p["U"] == 0 for p in front))


if __name__ == "__main__":
    unittest.main()
