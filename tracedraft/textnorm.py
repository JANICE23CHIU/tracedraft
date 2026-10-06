"""Text normalisation shared by retrieval, matching and scoring. Pure functions, stdlib only."""
from __future__ import annotations

import math
import re
import unicodedata

_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"[A-Za-z0-9]+(?:[.,][0-9]+)*|[^\sA-Za-z0-9]")
_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_COMPARATORS = {"≤": "<=", "≥": ">=", "＜": "<", "＞": ">"}


def norm(text: str | None) -> str:
    """Case-folded, NFKC, single-spaced. Keeps symbols such as ≤ ± ° σ."""
    if text is None:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    return _WS.sub(" ", text).strip().casefold()


def key(text: str | None) -> str:
    """Row-key normalisation: letters and digits only."""
    return re.sub(r"[^0-9a-z]+", "", norm(text))


def numbers(text: str | None) -> list[str]:
    return [n.replace(",", "") for n in _NUM.findall(norm(text))]


def comparators(text: str | None) -> list[str]:
    t = str(text or "")
    out = [_COMPARATORS[c] for c in t if c in _COMPARATORS]
    out += re.findall(r"<=|>=", t)
    return out


def words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", norm(text)) if len(w) > 1]


def trigrams(text: str) -> dict[str, int]:
    t = f"  {norm(text)}  "
    grams: dict[str, int] = {}
    for i in range(len(t) - 2):
        g = t[i:i + 3]
        grams[g] = grams.get(g, 0) + 1
    return grams


def cosine(a: dict[str, int], b: dict[str, int]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def est_tokens(text: str) -> int:
    """Conservative token estimate for Qwen-family BPE: 1 token per 3 characters (real ratio ~3.5–4 for
    English). Over-estimating keeps packets inside the 2048-token context; calibrate with Ollama's
    prompt_eval_count when a model is available."""
    return max(1, math.ceil(len(text) / 3))
