"""Where two presets differ, setting by setting, before any run (``scripts/compare_presets.py``).

Both presets are read with their bases applied (``loader.read_preset``), so an overlay is compared as
it runs, not as it is written. The comparison covers every key of the preset, including the task
settings under ``live_coordination`` and every text, which the run comparison (``archive.design.arm_diff``)
does not. ``preset_id`` is left out: it names the preset and changes nothing in the run.
"""

from __future__ import annotations

import difflib
import re

from oaos2.organizations.loader import read_preset

_SKIP = {("preset_id",), ("base_only",)}
_MISSING = "<not set>"


def _walk(a, b, path: tuple, out: list) -> None:
    if path in _SKIP:
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b), key=str):
            _walk(a.get(key, _MISSING), b.get(key, _MISSING), (*path, key), out)
    elif a != b:
        out.append({"setting": ".".join(str(p) for p in path), "a": a, "b": b})


def preset_differences(a: str, b: str) -> list[dict]:
    """The settings in which presets ``a`` and ``b`` differ: ``{"setting", "a", "b"}`` in key order,
    with dotted paths (``live_coordination.institution``) and ``<not set>`` for a setting one lacks."""
    out: list[dict] = []
    _walk(read_preset(a)[0], read_preset(b)[0], (), out)
    return out


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.:;])\s+", " ".join(str(text).split())) if s]


def describe(diff: dict, width: int = 100) -> str:
    """One difference as text: short values side by side, texts as a sentence-level diff."""
    a, b = diff["a"], diff["b"]
    if isinstance(a, str) and isinstance(b, str) and max(len(a), len(b)) > width:
        lines = difflib.unified_diff(_sentences(a), _sentences(b), lineterm="", n=0)
        body = [line for line in lines if not line.startswith(("---", "+++", "@@"))]
        return f"{diff['setting']} (text):\n" + "\n".join(f"  {line}" for line in body)
    return f"{diff['setting']}: {a!r} -> {b!r}"
