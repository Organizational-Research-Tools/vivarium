"""Citations into the archive (DASHBOARD.md §4.3 promised "citable in memos").

A design-log quotation cited as "vertical rep2 C-S15" cannot be resolved by a
referee.  A citation here names the archive object exactly and carries a content
digest, and it needs no server to resolve — ``scripts/cite.py`` resolves it over
``runs/`` and ``--check`` verifies every citation (and the quotation beside it) in
a document against the archive.

Format (one line, ``·``-separated, prefix ``cite:``)::

    cite: <run_ref> · ev <event_id> · seq <n> · <event_class> · <agent|·> · day <d|—> · sha256:<12>
    cite: <run_ref> · submitted/<name>.json · sha256:<12>

``run_ref`` is the run dir's path relative to the runs root (the dashboard's own
URL id).  The digest is over the event payload (canonical JSON) or the file bytes,
so a citation also attests what was read.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

_PREFIX = "cite:"
_EVENT_RE = re.compile(
    r"cite:\s*(?P<run_ref>\S+)\s*·\s*ev\s+(?P<event_id>[0-9A-Z]+)\s*·\s*seq\s+(?P<seq>\d+)"
    r"\s*·\s*(?P<cls>[a-z_.]+)\s*·\s*(?P<agent>[^·]+?|·)\s*·\s*day\s+(?P<day>\d+|—)"
    r"\s*·\s*sha256:(?P<digest>[0-9a-f]{12})")
_FILE_RE = re.compile(
    r"cite:\s*(?P<run_ref>\S+)\s*·\s*(?P<path>submitted/[A-Za-z0-9_.\-]+)\s*·\s*sha256:(?P<digest>[0-9a-f]{12})")


def payload_digest(event: dict) -> str:
    raw = json.dumps(event.get("payload") or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def file_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def event_citation(run_ref: str, event: dict, day: int | None) -> str:
    return (f"{_PREFIX} {run_ref} · ev {event.get('event_id')} · seq {event.get('sequence_number')}"
            f" · {event.get('event_class')} · {event.get('agent_id') or '—'}"
            f" · day {day if day is not None else '—'} · sha256:{payload_digest(event)}")


def file_citation(run_ref: str, rel_path: str, data: bytes) -> str:
    return f"{_PREFIX} {run_ref} · {rel_path} · sha256:{file_digest(data)}"


def parse_citation(text: str) -> dict | None:
    m = _EVENT_RE.search(text)
    if m:
        d = m.groupdict()
        return {"kind": "event", "run_ref": d["run_ref"], "event_id": d["event_id"],
                "seq": int(d["seq"]), "event_class": d["cls"], "agent": d["agent"].strip(),
                "day": None if d["day"] == "—" else int(d["day"]), "digest": d["digest"]}
    m = _FILE_RE.search(text)
    if m:
        d = m.groupdict()
        return {"kind": "file", "run_ref": d["run_ref"], "path": d["path"], "digest": d["digest"]}
    return None


def find_citations(text: str) -> list[dict]:
    """Every citation in a document, in order, each with the line it sits on."""
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for m in list(_EVENT_RE.finditer(line)) + list(_FILE_RE.finditer(line)):
            parsed = parse_citation(m.group(0))
            if parsed:
                parsed.update({"line": lineno, "raw": m.group(0), "context": line})
                out.append(parsed)
    return out


# --- resolution ------------------------------------------------------------- #

def text_leaves(obj) -> list[str]:
    """Every string in a JSON-ish object (payloads, filings) — what a quote can match."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in text_leaves(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in text_leaves(v)]
    return []


def _norm(s: str) -> str:
    return " ".join(s.replace("’", "'").replace("“", '"').replace("”", '"').split())


def resolve(runs_root: Path, parsed: dict) -> dict:
    """Locate the cited object. Returns ``{"ok", "problem", "texts", "object", "run_dir"}``."""
    runs_root = Path(runs_root).resolve()
    run_dir = (runs_root / parsed["run_ref"]).resolve()
    if runs_root not in run_dir.parents or not (run_dir / "trace" / "events.jsonl").exists():
        return {"ok": False, "problem": f"run not found: {parsed['run_ref']}", "texts": [],
                "object": None, "run_dir": None}
    if parsed["kind"] == "file":
        path = run_dir / "captured" / parsed["path"]
        if not path.exists():
            path = run_dir / parsed["path"]
        if not path.exists():
            return {"ok": False, "problem": f"file not found: {parsed['path']}", "texts": [],
                    "object": None, "run_dir": run_dir}
        data = path.read_bytes()
        if file_digest(data) != parsed["digest"]:
            return {"ok": False, "problem": "file digest differs — content changed since cited",
                    "texts": [], "object": None, "run_dir": run_dir}
        try:
            obj = json.loads(data)
        except ValueError:
            obj = data.decode(errors="replace")
        return {"ok": True, "problem": None, "texts": text_leaves(obj), "object": obj,
                "run_dir": run_dir}
    from oaos2.archive.transcript import events_in_order
    events = events_in_order(run_dir)
    event = next((e for e in events if e.get("event_id") == parsed["event_id"]), None)
    if event is None:
        return {"ok": False, "problem": f"event not found: {parsed['event_id']}", "texts": [],
                "object": None, "run_dir": run_dir}
    if payload_digest(event) != parsed["digest"]:
        return {"ok": False, "problem": "payload digest differs — the archive changed since cited",
                "texts": [], "object": event, "run_dir": run_dir}
    texts = text_leaves(event.get("payload") or {})
    ref = (event.get("payload") or {}).get("raw_provider_response_ref")
    if ref:
        from oaos2.archive.transcript import _extract_prose, _load_raw
        prose = _extract_prose(_load_raw(run_dir, ref) or {})
        if prose:
            texts.append(prose)
    return {"ok": True, "problem": None, "texts": texts, "object": event, "run_dir": run_dir}


_QUOTE_RE = re.compile(r'[“"]([^”"]{20,})[”"]')


def verify_document(runs_root: Path, text: str) -> list[dict]:
    """Check every citation in a document, and every quotation (≥20 chars in
    quotes) on the same line as a citation, against the archive.  Each result:
    ``{line, raw, ok, problem, quotes: [{text, found}]}``."""
    results = []
    for c in find_citations(text):
        res = resolve(runs_root, c)
        quotes = []
        if res["ok"]:
            haystack = _norm(" ".join(res["texts"]))
            for q in _QUOTE_RE.findall(c["context"]):
                needle = _norm(q).strip(" .…")
                quotes.append({"text": q, "found": needle in haystack})
        results.append({"line": c["line"], "raw": c["raw"], "ok": res["ok"],
                        "problem": res["problem"], "quotes": quotes})
    for lineno, line in enumerate(text.splitlines(), 1):
        matches = list(_EVENT_RE.finditer(line)) + list(_FILE_RE.finditer(line))
        for marker in re.finditer(r"\bcite:", line):
            if not any(m.start() == marker.start() for m in matches):
                results.append({"line": lineno, "raw": line[marker.start():],
                                "ok": False, "problem": "malformed citation", "quotes": []})
    return sorted(results, key=lambda r: r["line"])


# --- excerpt export --------------------------------------------------------- #

def excerpt_markdown(*, citation: str, quote: str, cell: str, note: str = "") -> str:
    """The block a reader pastes into a design log or memo: quote, then citation."""
    q = "\n".join("> " + line for line in (quote or "").strip().splitlines()) or "> (no text)"
    tail = f"\n{note.strip()}" if note.strip() else ""
    return f"{q}\n>\n> — {cell} · `{citation}`{tail}\n"
