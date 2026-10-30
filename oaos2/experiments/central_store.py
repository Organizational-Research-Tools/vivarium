"""The central store: a readable record for one role (LK1 H-F, 2026-09-25).

Galbraith's vertical information system, in one bounded component: the center can look
up, at the cost of calls and context, what the offices hold and what the quarter has
released, instead of asking (the query stage) or relying on reports alone. The store
lives in the role's own scratch directory, so only a role granted ``read_file`` can read
it and no other role's container mounts it. It holds:

- ``index.md``: what is in the store and how to read it;
- ``materials/<name>.md``: the declared standing materials (the offices' operating files,
  once authored; their program details until then), split into numbered sections under
  the read tool's output cap so no read truncates silently;
- ``notices/index.md`` and ``notices/day<NN>_<packet>.json``: every notice the clock has
  released so far, filed as it is delivered. A notice from a later round is not in the
  store until its round opens.

Writes here are platform writes at setup and at release, not agent writes; the lineage
that matters is on the read side (``file.read`` with a content hash, and the returned
text in the next saved request).
"""
from __future__ import annotations

import json
from pathlib import Path

SECTION_CHARS = 16_000  # under tools._READ_CAP (20,000), with room for the section header


def _sections(text: str, cap: int = SECTION_CHARS) -> list[str]:
    """Split on blank lines into chunks under ``cap`` characters; a paragraph longer than
    the cap is split at the cap."""
    out: list[str] = []
    cur = ""
    for para in text.split("\n\n"):
        piece = para + "\n\n"
        while len(piece) > cap:
            if cur:
                out.append(cur)
                cur = ""
            out.append(piece[:cap])
            piece = piece[cap:]
        if len(cur) + len(piece) > cap and cur:
            out.append(cur)
            cur = ""
        cur += piece
    if cur.strip():
        out.append(cur)
    return out


def write_store_materials(store: Path, pack, materials: list[str], *, notices: bool = True) -> dict:
    """Write the index and the declared materials; return the index as a dict."""
    (store / "materials").mkdir(parents=True, exist_ok=True)
    if notices:
        (store / "notices").mkdir(parents=True, exist_ok=True)
        (store / "notices" / "index.md").write_text(
            "# Released notices\n\nNone released yet. Each line below names a file you can read "
            "with read_file, in release order: day, packet id, case id (if any), file.\n")
    index = {"materials": [], "notices": "notices/index.md" if notices else None}
    lines = ["# Central store — index",
             "",
             "Read any file below with read_file, using the path exactly as given. Each read is one "
             "tool call in your turn and its text is added to your context. Long materials are "
             "split into numbered sections; read the sections you need.",
             ""]
    for name in materials:
        src = Path(pack.visible_dir) / name
        if not src.is_file():
            raise FileNotFoundError(f"central store material {name!r} not found under {pack.visible_dir}")
        text = src.read_text(errors="replace")
        parts = _sections(text)
        stem = name.replace("/", "_").rsplit(".", 1)[0]
        files = []
        for i, part in enumerate(parts, 1):
            fname = f"materials/{stem}_s{i:02d}.md" if len(parts) > 1 else f"materials/{stem}.md"
            (store / fname).write_text(part)
            files.append(fname)
        index["materials"].append({"name": name, "files": files, "chars": len(text)})
        lines.append(f"- {name}: " + ", ".join(f"`store/{f}`" for f in files)
                     + (f" ({len(parts)} sections)" if len(parts) > 1 else ""))
    if notices:
        lines += ["", "- Released notices: `store/notices/index.md` lists every notice released so far; "
                      "each entry names a `store/notices/day<NN>_<packet>.json` file."]
    (store / "index.md").write_text("\n".join(lines) + "\n")
    (store / "index.json").write_text(json.dumps(index, indent=1))
    return index


def file_released_notice(store: Path, packet, *, recipient: str) -> Path:
    """File one released notice (once per packet id) and append it to the notices index."""
    day = packet.arrival_round or 0
    payload = packet.payload if isinstance(packet.payload, dict) else {"payload": packet.payload}
    fname = f"notices/day{day:02d}_{packet.packet_id}.json"
    path = store / fname
    path.write_text(json.dumps(payload, sort_keys=True, indent=2))
    case_id = str(payload.get("case_id") or "").strip()
    idx = store / "notices" / "index.md"
    text = idx.read_text() if idx.is_file() else "# Released notices\n\n"
    if "None released yet." in text:
        text = text.replace("None released yet. ", "")
    text += f"- day {day:02d} | {packet.packet_id} | {case_id or '-'} | to {recipient} | `store/{fname}`\n"
    idx.write_text(text)
    return path
