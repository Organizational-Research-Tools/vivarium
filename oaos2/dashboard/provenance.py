"""Compare available run-material fingerprints with the current library.

superseded means a named task or organization is missing. stale_materials means
a checked scoring-reference or task-manifest hash differs. current means the
available checks matched; older runs may supply only a headline reference hash.
unknown covers missing comparison data or a task that cannot be loaded.

These labels do not compare every model, organization setting, or analysis rule.
The separate gate-check tag uses experiment-name fragments to identify likely
materials checks; it is a naming heuristic, not a verified study classification."""

from __future__ import annotations

from oaos2.experiments.runner import _headline_ref_sha
from oaos2.library import library_dir
from oaos2.organizations.loader import available_org_specs
from oaos2.tasks.loader import load_task_pack

# experiment_id substrings that mark a materials-gate batch (see module docstring)
_GATE_MARKERS = ("manip", "guessability", "mfgcheck")

# current-library snapshot, invalidated when any pack manifest changes
_snapshot: dict | None = None
_snapshot_key: tuple | None = None


def _library_snapshot() -> dict:
    """{'packs': {pack_id: current_reference_sha|None|'LOAD_ERROR'}, 'orgs': {...}} —
    memoized on the pack manifests' mtimes so a library edit invalidates it."""
    global _snapshot, _snapshot_key
    lib = library_dir()
    manifests = sorted((lib / "tasks").glob("*/manifest.yaml"))
    orgs = frozenset(available_org_specs())
    key = (str(lib), orgs,
           tuple((str(p), p.stat().st_mtime_ns) for p in manifests))
    if _snapshot is not None and key == _snapshot_key:
        return _snapshot
    packs: dict[str, dict | str] = {}
    for mp in manifests:
        pack_id = mp.parent.name
        # The headline evaluator (whose hidden-ref hash we need) is profile-independent,
        # but load_task_pack requires SOME declared profile — try the common shapes,
        # then the pack's own first declared profile (the pool packs declare neither
        # "decomposed" nor "single_results").
        attempts: list[dict] = [{}, {"decomposed": False}]
        try:
            from oaos2.tasks.loader import load_manifest
            declared = sorted((load_manifest(pack_id).get("contracts") or {}).keys())
        except Exception:  # noqa: BLE001 — the loop below records the load error
            declared = []
        attempts += [{"profile": name} for name in declared[:1]]
        for kwargs in attempts:
            try:
                pack = load_task_pack(pack_id, **kwargs)
                import hashlib
                packs[pack_id] = {
                    "reference_sha256": _headline_ref_sha(pack),
                    "hidden_reference_sha256s": {
                        ref: spec.get("sha256") for ref, spec in sorted(pack.hidden_refs.items())
                    },
                    "task_manifest_sha256": (
                        "sha256:" + hashlib.sha256(pack.manifest_path.read_bytes()).hexdigest()
                        if pack.manifest_path else None),
                }
                break
            except Exception:  # a broken pack must not take the registry page down
                packs[pack_id] = "LOAD_ERROR"
    _snapshot = {"packs": packs, "orgs": orgs}
    _snapshot_key = key
    return _snapshot


def classify(row: dict) -> dict:
    """Provenance verdict for one registry row (needs the cache's manifest pins)."""
    snap = _library_snapshot()
    pack = row.get("task_pack_id")
    org = row.get("organization_id")
    pinned = row.get("reference_sha256")
    pinned_hidden = row.get("hidden_reference_sha256s")
    pinned_manifest = row.get("task_manifest_sha256")
    reasons: list[str] = []
    tags: list[str] = []

    exp = row.get("experiment_id") or ""
    if any(m in exp for m in _GATE_MARKERS):
        tags.append("gate-check")

    if pack and pack not in snap["packs"]:
        reasons.append(f"task pack '{pack}' is no longer in the library")
    if org and org not in snap["orgs"]:
        reasons.append(f"organization preset '{org}' is no longer in the library")
    if reasons:
        return {"provenance": "superseded", "provenance_reasons": reasons, "tags": tags}

    if pack:
        current = snap["packs"].get(pack)
        if current == "LOAD_ERROR":
            reasons.append(f"task pack '{pack}' fails to load — library state itself is broken")
            return {"provenance": "unknown", "provenance_reasons": reasons, "tags": tags}
        if isinstance(current, dict) and pinned_hidden:
            if pinned_hidden != current.get("hidden_reference_sha256s"):
                reasons.append("one or more hidden scoring/measurement references changed after this run")
                return {"provenance": "stale_materials", "provenance_reasons": reasons, "tags": tags}
            if pinned_manifest and pinned_manifest != current.get("task_manifest_sha256"):
                reasons.append("the task manifest changed after this run")
                return {"provenance": "stale_materials", "provenance_reasons": reasons, "tags": tags}
            return {"provenance": "current", "provenance_reasons": [], "tags": tags}
        current_ref = current.get("reference_sha256") if isinstance(current, dict) else current
        if pinned and current_ref and pinned != current_ref:
            reasons.append(
                f"scored against reference {pinned[:19]}…, but the pack's current "
                f"reference is {current_ref[:19]}… — the materials changed after this run")
            return {"provenance": "stale_materials", "provenance_reasons": reasons, "tags": tags}
        if pinned and current_ref and pinned == current_ref:
            return {"provenance": "current", "provenance_reasons": [], "tags": tags}

    reasons.append("no reference pin to compare (pre-pin run or a scorer with no hidden ref)")
    return {"provenance": "unknown", "provenance_reasons": reasons, "tags": tags}


def annotate_rows(rows: list[dict]) -> list[dict]:
    """Stamp provenance onto registry rows, in place (idempotent)."""
    for r in rows:
        r.update(classify(r))
    return rows


# chip roles for the UI (status palette; distinct from run-status chips)
PROVENANCE_CHIP = {
    "current": ("good", "●"),
    "stale_materials": ("warning", "◐"),
    "superseded": ("muted", "○"),
    "unknown": ("neutral", "◌"),
}
