"""EvidenceStore — the smart database's storage module.

Interface (small):
    store = EvidenceStore(db_path)          # ":memory:" for tests
    store.ingest(manifest_path) -> dict     # parse sources into citable segments
    snap  = store.freeze()                  # SHA-256 over every segment: the frozen snapshot id
    store.get(evidence_id) / store.all()
    store.rank(query, ids) -> {"bm25": [...], "trigram": [...]}   # two independent rankings

Behind it (depth): Markdown parsing with page markers, table rows -> one segment each
with a column map, paragraphs -> segments, SHA-256 of every source file, SQLite FTS5 (BM25)
and a character-trigram cosine ranker. The store never decides eligibility or answers;
it only finds and returns citable text with its exact location.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

from .textnorm import cosine, key, norm, trigrams, words

PAGE = re.compile(r"<!--\s*page\s+(\d+)\s*-->", re.I)
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cells(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [c.strip() for c in inner.split("|")]


def parse_markdown(text: str) -> list[dict]:
    """Split a Markdown source into citable segments with page / section / row location."""
    segments: list[dict] = []
    page, section, table_idx = 1, "", 0
    lines = text.splitlines()
    i = 0
    para: list[str] = []

    def flush_para():
        nonlocal para
        body = " ".join(s.strip() for s in para if s.strip())
        if body:
            segments.append({"kind": "para", "page": page, "section": section, "table": None,
                             "row_index": None, "row_key": "", "columns": {}, "text": body})
        para = []

    while i < len(lines):
        line = lines[i]
        m = PAGE.search(line)
        if m:
            flush_para()
            page = int(m.group(1))
            i += 1
            continue
        h = HEADING.match(line)
        if h:
            flush_para()
            section = h.group(2).strip()
            i += 1
            continue
        if line.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*-{3,}", lines[i + 1]):
            flush_para()
            table_idx += 1
            header = _cells(line)
            i += 2
            r = 0
            while i < len(lines) and lines[i].strip().startswith("|"):
                r += 1
                cells = _cells(lines[i])
                cols = {header[j]: (cells[j] if j < len(cells) else "") for j in range(len(header))}
                row_key = cols.get("Test Name") or (cells[0] if cells else "")
                text_row = " | ".join(f"{k}: {v}" for k, v in cols.items())
                segments.append({"kind": "row", "page": page, "section": section, "table": table_idx,
                                 "row_index": r, "row_key": row_key, "columns": cols, "text": text_row})
                i += 1
            continue
        if not line.strip():
            flush_para()
        elif not line.lstrip().startswith(">"):
            para.append(line)
        i += 1
    flush_para()
    return segments


class EvidenceStore:
    def __init__(self, db_path: str | Path = ":memory:"):
        self.db = sqlite3.connect(str(db_path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS documents(doc_id TEXT, rev TEXT, role TEXT, status TEXT, path TEXT,
                sha256 TEXT, PRIMARY KEY(doc_id, rev));
            CREATE TABLE IF NOT EXISTS segments(evidence_id TEXT PRIMARY KEY, doc_id TEXT, rev TEXT, role TEXT,
                status TEXT, kind TEXT, page INTEGER, section TEXT, tbl INTEGER, row_index INTEGER, row_key TEXT,
                row_norm TEXT, columns TEXT, text TEXT);
            CREATE VIRTUAL TABLE IF NOT EXISTS seg_fts USING fts5(evidence_id UNINDEXED, text);
        """)
        self._grams: dict[str, dict[str, int]] = {}
        self.dense = None                      # optional embedder (embed.py); None = lexical-only index
        self._vecs: dict[str, list[float]] = {}

    def use_dense(self, embedder) -> None:
        """Attach a small embedding model as the third ranker. Vectors are computed once per segment."""
        self.dense = embedder
        self._vecs = {}

    # ---------------------------------------------------------------- ingest
    def ingest(self, manifest_path: str | Path) -> dict:
        manifest_path = Path(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        added = 0
        for doc in manifest["documents"]:
            path = (manifest_path.parent / doc["path"]).resolve()
            sha = sha256_file(path)
            self.db.execute("INSERT INTO documents VALUES(?,?,?,?,?,?)",
                            (doc["doc_id"], doc["rev"], doc["role"], doc["status"], str(path), sha))
            for idx, seg in enumerate(parse_markdown(path.read_text(encoding="utf-8")), 1):
                if seg["kind"] == "row":
                    eid = f"{doc['doc_id']}@{doc['rev']}:p{seg['page']}:t{seg['table']}:r{seg['row_index']}"
                else:
                    eid = f"{doc['doc_id']}@{doc['rev']}:p{seg['page']}:s{idx}"
                self.db.execute("INSERT INTO segments VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    eid, doc["doc_id"], doc["rev"], doc["role"], doc["status"], seg["kind"], seg["page"],
                    seg["section"], seg["table"], seg["row_index"], seg["row_key"], key(seg["row_key"]),
                    json.dumps(seg["columns"], ensure_ascii=False), seg["text"]))
                self.db.execute("INSERT INTO seg_fts VALUES(?,?)", (eid, seg["text"]))
                added += 1
        self.db.commit()
        self._grams = {}
        return {"documents": len(manifest["documents"]), "segments": added}

    def freeze(self) -> str:
        digest = hashlib.sha256()
        for row in self.db.execute("SELECT evidence_id, doc_id, rev, status, text FROM segments ORDER BY evidence_id"):
            digest.update("\x1f".join(str(v) for v in tuple(row)).encode("utf-8") + b"\x1e")
        return digest.hexdigest()

    # ---------------------------------------------------------------- access
    @staticmethod
    def _row(r: sqlite3.Row) -> dict:
        d = dict(r)
        d["columns"] = json.loads(d["columns"])
        d["table"] = d.pop("tbl")
        return d

    def get(self, evidence_id: str) -> dict | None:
        r = self.db.execute("SELECT * FROM segments WHERE evidence_id=?", (evidence_id,)).fetchone()
        return self._row(r) if r else None

    def all(self) -> list[dict]:
        return [self._row(r) for r in self.db.execute("SELECT * FROM segments ORDER BY evidence_id")]

    def documents(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM documents ORDER BY doc_id, rev")]

    # ---------------------------------------------------------------- ranking
    def rank(self, query: str, ids: set[str]) -> dict[str, list[str]]:
        """Two lexical rankings (plus a dense one when an embedder is attached), restricted to `ids`. Ranks start at 1."""
        terms = sorted(set(words(query)))
        bm25: list[str] = []
        if terms:
            match = " OR ".join('"' + t.replace('"', "") + '"' for t in terms)
            for r in self.db.execute("SELECT evidence_id, bm25(seg_fts) AS s FROM seg_fts WHERE seg_fts MATCH ? "
                                     "ORDER BY s, evidence_id", (match,)):
                if r["evidence_id"] in ids:
                    bm25.append(r["evidence_id"])
        if not self._grams:
            self._grams = {s["evidence_id"]: trigrams(s["text"]) for s in self.all()}
        q = trigrams(query)
        scored = sorted(((cosine(q, self._grams[i]), i) for i in ids), key=lambda x: (-x[0], x[1]))
        tri = [i for s, i in scored if s > 0]
        out = {"bm25": bm25, "trigram": tri}
        if self.dense is not None:
            from .embed import cosine_dense
            if not self._vecs:
                segs = self.all()
                vecs = self.dense.embed([sg["text"] for sg in segs], "document")
                self._vecs = {sg["evidence_id"]: v for sg, v in zip(segs, vecs)}
            qv = self.dense.embed([query], "query")[0]
            dscored = sorted(((cosine_dense(qv, self._vecs[i]), i) for i in ids), key=lambda x: (-x[0], x[1]))
            out["dense"] = [i for s, i in dscored if s > 0]
        return out
