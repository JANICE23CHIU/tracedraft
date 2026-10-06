"""Dense-vector adapters — the specialised small model in the hybrid index.

The evidence store ranks every query three ways and fuses them with RRF (select.py):
    bm25     SQLite FTS5 (lexical, exact terms)
    trigram  character trigrams (spelling and unit variants)
    dense    a small local embedding model (meaning; optional)
The dense ranker is a seam: any object with `name` and `embed(texts, kind) -> list[list[float]]` plugs in.

Interface:
    OllamaEmbedder(model="nomic-embed-text", base_url=None)   # local Ollama /api/embed
    HashEmbedder(dim=256)                                      # deterministic stand-in for tests, no model
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.request

from .textnorm import norm

# nomic-embed-text expects task prefixes; other models get the raw text.
_PREFIX = {"nomic-embed-text": {"query": "search_query: ", "document": "search_document: "}}


class OllamaEmbedder:
    default_base = "http://127.0.0.1:11434"

    def __init__(self, model: str = "nomic-embed-text", base_url: str | None = None, timeout: float = 120.0):
        self.name = model
        self.base_url = (base_url or self.default_base).rstrip("/")
        self.timeout = timeout
        self.seconds = 0.0

    def embed(self, texts: list[str], kind: str = "document") -> list[list[float]]:
        prefix = _PREFIX.get(self.name.split(":")[0], {}).get(kind, "")
        body = {"model": self.name, "input": [prefix + t for t in texts]}
        req = urllib.request.Request(self.base_url + "/api/embed", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.seconds += time.perf_counter() - t0
        return data["embeddings"]


class HashEmbedder:
    """Bag of hashed word and trigram features. Not a semantic model; it only exercises the seam."""

    def __init__(self, dim: int = 256):
        self.name = f"hash{dim}"
        self.dim = dim
        self.seconds = 0.0

    def embed(self, texts: list[str], kind: str = "document") -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dim
            s = norm(t)
            feats = s.split() + [s[i:i + 3] for i in range(max(0, len(s) - 2))]
            for f in feats:
                v[int(hashlib.sha256(f.encode("utf-8")).hexdigest()[:8], 16) % self.dim] += 1.0
            out.append(v)
        return out


def cosine_dense(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
