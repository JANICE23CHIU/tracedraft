"""InferencePort — the seam between TraceDraft and whatever runs the model.

Interface (two calls, nothing else):
    port.extract(task) -> {"value", "evidence_id", "quote", "status", "conflict"?, "meta"}
    port.verify(task, claim) -> {"verdict": SUPPORTED|NOT_SUPPORTED|INSUFFICIENT|ABSTAIN, "reason", "meta"}

Adapters:
    RuleAdapter        deterministic, contract-driven; no model. CI baseline and pipeline upper bound.
    OllamaAdapter      Ollama /api/chat (laptop CPU/GPU). Stage I stand-in for the accelerator.
    HailoOllamaAdapter same protocol against hailo-ollama on the ASUS UGen300 (default port 8000).
    RelayAdapter       manual copy/paste to a chat assistant (prompts out, answers in); optional.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from .textnorm import key, norm

STATUSES = ("SOURCED", "MISSING")
VERDICTS = ("SUPPORTED", "NOT_SUPPORTED", "INSUFFICIENT")

EXTRACT_SYSTEM = (
    "You fill ONE field of a product test protocol. Use ONLY the evidence lines given. "
    "Each evidence line starts with its id in square brackets. "
    "Reply with one JSON object and nothing else: "
    '{"value": <string or null>, "evidence_id": <id or null>, "quote": <exact text copied from that evidence line or null>, '
    '"status": "SOURCED" or "MISSING", "conflict": <null or short note>}. '
    "If the evidence does not state the value, or states TBD, set status MISSING and value null. Never guess."
)

VERIFY_SYSTEM = (
    "You check a citation. Decide whether the quoted source text states exactly the claimed value for the "
    "named test, field and condition. Different numbers, comparison signs, units, negation, a different test "
    "or a different condition mean NOT_SUPPORTED. If the quote does not mention the test or field, answer "
    "INSUFFICIENT. Reply with one JSON object and nothing else: "
    '{"verdict": "SUPPORTED" or "NOT_SUPPORTED" or "INSUFFICIENT", "reason": <short>}.'
)


PROMPT_VARIANTS = ("v1", "v2", "v3")
# v1  evidence lines carry the full evidence id; the model must copy it back (Stage I first run).
# v2  evidence lines carry short handles [E1]..[En]; the system maps the handle back to the id.
#     (finding 2026-10-04: the 1.5B model rewrote "TMX-NK1-002" as "TM-NK1-002" in 17/17 K1 citations)
# v3  v2 + the contract's cue words for this field ("the value follows 'acceptance criteria'").
#     (finding 2026-10-04: in prose the model copied the specification clause as the acceptance criteria)


def handles(task: dict) -> dict[str, str]:
    return {f"E{i}": e["evidence_id"] for i, e in enumerate(task["evidence"], 1)}


def extract_prompt(task: dict, variant: str = "v1") -> tuple[str, str]:
    rules = list(task["rules"])
    if variant == "v3" and task.get("cues"):
        quoted = ", ".join(f"'{c}'" for c in task["cues"][:3])
        rules.append(f"In a sentence, the value is the text right after {quoted}; copy that part only, "
                     "not the specification, the requirement sentence or other parts.")
    rule_text = "\n".join(f"- {r}" for r in rules)
    cond = f"\nCondition: {task['condition_label']}" if task["field"] == "n" else ""
    if variant in ("v2", "v3"):
        h = handles(task)
        inv = {v: k for k, v in h.items()}
        evidence = "\n".join(f"[{inv[e['evidence_id']]}] {e['text']}" for e in task["evidence"])
        system = EXTRACT_SYSTEM.replace("its id in square brackets", "a short handle such as E1 in square brackets") \
                               .replace('"evidence_id": <id or null>', '"evidence_id": <handle such as "E1", or null>')
    else:
        evidence = "\n".join(f"[{e['evidence_id']}] {e['text']}" for e in task["evidence"])
        system = EXTRACT_SYSTEM
    user = (f"Field: {task['field_label']}\nTest: {task['test_name']}{cond}\nRules:\n{rule_text}\n\n"
            f"Evidence:\n{evidence}\n\nJSON:")
    return system, user


def map_handle(task: dict, cited) -> str | None:
    """Turn a handle (E2, [E2], e2) back into the real evidence id. Full ids pass through unchanged."""
    if cited is None:
        return None
    text = str(cited).strip().strip("[]").strip()
    h = handles(task)
    return h.get(text.upper(), text)


def verify_prompt(task: dict, claim: dict) -> tuple[str, str]:
    user = (f"Test: {task['test_name']}\nCondition: {task['condition_label']}\nField: {task['field_label']}\n"
            f"Claimed value: {claim.get('value')}\nQuoted source ({claim.get('evidence_id')}): {claim.get('quote')}\n\nJSON:")
    return VERIFY_SYSTEM, user


def parse_json_reply(text: str) -> dict:
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("NO_JSON_OBJECT")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("NOT_OBJECT")
    return value


# --------------------------------------------------------------------------- deterministic
class RuleAdapter:
    name = "rule"

    def __init__(self, contract):
        self.contract = contract

    def extract(self, task: dict) -> dict:
        """Read the field from the packet's table rows with the contract's column rules. Prose sources
        are out of reach for rules by design: the adapter answers MISSING with the reason."""
        from .contract import mentions
        field = self.contract.field(task["field"])
        roles = field.get("authority") or [u["role"] for u in field["units"]]
        rows = [e for e in task["evidence"] if e["kind"] == "row" and mentions(e, task["test_name"])]
        found = None
        for role in roles:
            found = next((e for e in rows if e["role"] == role), None)
            if found:
                break
        if not found:
            prose = any(e["kind"] == "para" and mentions(e, task["test_name"]) for e in task["evidence"])
            return {"value": None, "evidence_id": None, "quote": None, "status": "MISSING",
                    "meta": {"reason": "PROSE_NOT_PARSEABLE_BY_RULES" if prose else "NO_MATCHING_ROW_IN_PACKET"}}
        status, value = self.contract.expected_from(field, found, task["condition_label"])
        if status != "SOURCED":
            return {"value": None, "evidence_id": found["evidence_id"], "quote": found["text"], "status": "MISSING",
                    "meta": {"reason": "SOURCE_STATES_NO_VALUE"}}
        conflict = None
        for other in rows:
            if other["role"] == found["role"]:
                continue
            ostatus, ovalue = self.contract.expected_from(field, other, task["condition_label"])
            if ostatus == "SOURCED" and key(str(ovalue)) not in {key(str(value)), "seeprs"}:
                conflict = f"{other['evidence_id']} states '{ovalue}'"
        return {"value": value, "evidence_id": found["evidence_id"], "quote": found["text"], "status": "SOURCED",
                "conflict": conflict, "meta": {}}

    def verify(self, task: dict, claim: dict) -> dict:
        return {"verdict": "ABSTAIN", "reason": "rule adapter has no semantic judgement", "meta": {}}


# --------------------------------------------------------------------------- Ollama-compatible
class OllamaAdapter:
    name = "ollama"
    default_base = "http://127.0.0.1:11434"

    def __init__(self, model: str = "qwen2.5:1.5b", base_url: str | None = None, num_ctx: int = 2048,
                 seed: int = 42, timeout: int = 180, max_output: int = 160, prompt: str = "v1"):
        if prompt not in PROMPT_VARIANTS:
            raise ValueError(f"unknown prompt variant {prompt}")
        self.prompt = prompt
        self.model = model
        self.base_url = (base_url or self.default_base).rstrip("/")
        self.options = {"temperature": 0, "seed": seed, "num_ctx": num_ctx, "num_predict": max_output}
        self.timeout = timeout

    def _chat(self, system: str, user: str) -> tuple[dict, dict]:
        body = {"model": self.model, "stream": False, "format": "json", "options": self.options,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        req = urllib.request.Request(self.base_url + "/api/chat", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        meta = {"wall_s": round(time.monotonic() - t0, 3), "model": self.model, "backend": self.name,
                "prompt_eval_count": data.get("prompt_eval_count"), "eval_count": data.get("eval_count"),
                "total_duration_ns": data.get("total_duration")}
        return data, meta

    def extract(self, task: dict) -> dict:
        system, user = extract_prompt(task, self.prompt)
        try:
            data, meta = self._chat(system, user)
            out = parse_json_reply(data.get("message", {}).get("content", ""))
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            return {"value": None, "evidence_id": None, "quote": None, "status": "ERROR",
                    "meta": {"error": f"{type(exc).__name__}: {exc}", "backend": self.name}}
        status = out.get("status") if out.get("status") in STATUSES else ("SOURCED" if out.get("value") else "MISSING")
        value = out.get("value")
        if task["field"] == "n" and value is not None:
            try:
                value = int(str(value).replace(",", "").strip())
            except ValueError:
                pass
        meta["prompt"] = self.prompt
        meta["raw_evidence_id"] = out.get("evidence_id")
        cited = map_handle(task, out.get("evidence_id")) if self.prompt in ("v2", "v3") else out.get("evidence_id")
        return {"value": value, "evidence_id": cited, "quote": out.get("quote"), "status": status,
                "conflict": out.get("conflict"), "meta": meta}

    def verify(self, task: dict, claim: dict) -> dict:
        system, user = verify_prompt(task, claim)
        try:
            data, meta = self._chat(system, user)
            out = parse_json_reply(data.get("message", {}).get("content", ""))
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            return {"verdict": "ERROR", "reason": f"{type(exc).__name__}: {exc}", "meta": {"backend": self.name}}
        verdict = out.get("verdict") if out.get("verdict") in VERDICTS else "INSUFFICIENT"
        return {"verdict": verdict, "reason": out.get("reason"), "meta": meta}


class HailoOllamaAdapter(OllamaAdapter):
    """Same Ollama-compatible protocol, served by hailo-ollama on the UGen300 (Hailo-10H).
    Default port 8000 per hailo_model_zoo_genai. Whether hailo-ollama honours `format`, `seed`
    and `num_ctx` is NOT verified yet — Stage II checks it on the device and records the result."""
    name = "hailo-ollama"
    default_base = "http://127.0.0.1:8000"


# --------------------------------------------------------------------------- manual relay
class RelayAdapter:
    """Prompts go to relay/outbox.jsonl; a person pastes answers into relay/inbox.jsonl (one JSON per line,
    with the same task_id). Nothing is sent anywhere automatically."""
    name = "relay"

    def __init__(self, folder: str | Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        inbox = self.folder / "inbox.jsonl"
        self.answers = {}
        if inbox.is_file():
            for line in inbox.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    item = json.loads(line)
                    self.answers[item["task_id"]] = item

    def _out(self, kind: str, task: dict, system: str, user: str) -> None:
        with (self.folder / "outbox.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"task_id": task["task_id"] + ":" + kind, "system": system, "user": user},
                                ensure_ascii=False) + "\n")

    def extract(self, task: dict) -> dict:
        ans = self.answers.get(task["task_id"] + ":extract")
        if not ans:
            self._out("extract", task, *extract_prompt(task, "v1"))
            return {"value": None, "evidence_id": None, "quote": None, "status": "PENDING_RELAY", "meta": {}}
        return {"value": ans.get("value"), "evidence_id": ans.get("evidence_id"), "quote": ans.get("quote"),
                "status": ans.get("status", "SOURCED"), "conflict": ans.get("conflict"), "meta": {"backend": "relay"}}

    def verify(self, task: dict, claim: dict) -> dict:
        ans = self.answers.get(task["task_id"] + ":verify")
        if not ans:
            self._out("verify", task, *verify_prompt(task, claim))
            return {"verdict": "ABSTAIN", "reason": "PENDING_RELAY", "meta": {}}
        return {"verdict": ans.get("verdict", "INSUFFICIENT"), "reason": ans.get("reason"), "meta": {"backend": "relay"}}


def make_adapter(name: str, contract, **kw):
    if name == "rule":
        return RuleAdapter(contract)
    if name == "ollama":
        return OllamaAdapter(**kw)
    if name in {"hailo", "hailo-ollama"}:
        return HailoOllamaAdapter(**kw)
    if name == "relay":
        return RelayAdapter(kw.get("folder", "relay"))
    raise ValueError(f"unknown adapter {name}")
