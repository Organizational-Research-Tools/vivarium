"""Item lifecycles over an archive (DASHBOARD.md §4.3c — the case dossier).

An ITEM is anything the environment delivers and the organization must handle:
a budget delivery case, an interface case in the epistemic study, a conflict
incident.  Its lifecycle — declared → arrived (per role) → observed by →
handled (filings) → disposed → scored — is a JOIN over foundation events
(``environment.event``, ``agent.observed``, ``state.committed``,
``capacity.deadline_lapse``, ``intervention.recorded``) and the contract's own
declared metadata (``timing.case``, ``timing.role``, ``committer_roles``), never a
commitment-id grammar in the foundation.  What only a pack knows — the frozen
scorer's per-item rows, the saved answer key, and a grammar fallback for archives
whose contract cannot be loaded — comes through a registered ``ItemAdapter``.

Everything here is a pure function of the archive plus pinned library state;
"who decided" is the committer's ``agent_id`` and "who was notified" the
arrivals' target roles — observables.  Whether the committer was among the
notified is a labeled derived join, offered as a lens, never a headline.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from oaos2.archive.clock import day_index


@dataclass(frozen=True)
class ItemAdapter:
    """Pack hooks. ``score_rows(report) → {item_id: row}``; ``key_for(run_dir,
    manifest, item_id) → {"key": …, "pinned": True} | {"withheld": reason} | None``;
    ``commitment_item(cid) → (item_id, kind, role_id|None) | None`` is the fallback
    when the contract is unavailable. ``payload_items(cid, payload) → {item_id: excerpt}``,
    optional, names the items a commitment that belongs to no single item reports on
    (a quarter report with one record per case), with the part of the payload about
    each; the pack decides from its own payload grammar."""

    pack_id: str
    score_rows: Callable[[dict], dict[str, dict]] = field(default=lambda report: {})
    key_for: Callable[[Path, dict, str], dict | None] = field(default=lambda run_dir, manifest, item_id: None)
    commitment_item: Callable[[str], tuple | None] | None = None
    payload_items: Callable[[str, object], dict[str, str]] | None = None


_ADAPTERS: dict[str, ItemAdapter] = {}


def register_item_adapter(adapter: ItemAdapter, *, override: bool = False) -> None:
    if adapter.pack_id in _ADAPTERS and not override:
        raise ValueError(f"item adapter for {adapter.pack_id!r} already registered")
    _ADAPTERS[adapter.pack_id] = adapter


def item_adapter_for(pack_id: str | None) -> ItemAdapter | None:
    from oaos2.archive.renderers import ensure_pack_renderers  # same convention module
    ensure_pack_renderers(pack_id)
    return _ADAPTERS.get(pack_id) if pack_id else None


# --- the contract's declared metadata ---------------------------------------- #

_CONTRACT_CACHE: dict[tuple, dict] = {}


def contract_index(run_dir: Path, manifest: dict) -> tuple[dict[str, dict], str]:
    """``commitment_id → {item, kind, committers}`` from the pack's contract profile
    as declared (``timing.case`` / ``timing.role`` / ``committer_roles``), with the
    committer role names mapped to this run's role ids through ``config/resolved.json``.
    Returns ``({}, reason)`` when the contract cannot be loaded (pack gone, profile
    renamed) — the caller then falls back to the adapter's grammar, labeled."""
    pack_id = manifest.get("task_pack_id")
    ext = manifest.get("extensions") or {}
    profile = ext.get("contract_profile")
    if not pack_id or not profile:
        return {}, "no contract profile pinned in the manifest"
    plays_to_role: dict[str, str] = {}
    try:
        resolved = json.loads((Path(run_dir) / "config" / "resolved.json").read_text())
        for r in resolved.get("roles") or []:
            for play in r.get("plays") or []:
                plays_to_role[play] = r["role_id"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    key = (pack_id, profile)
    raw = _CONTRACT_CACHE.get(key)
    if raw is None:
        try:
            from oaos2.tasks.loader import load_task_pack
            pack = load_task_pack(pack_id, profile=profile)
            raw = {}
            for c in pack.outcome_contract.commitments:
                timing = c.timing or {}
                routing = c.routing or {}
                item = (timing.get("case") or routing.get("case")
                        or (routing.get("paired_slot") or {}).get("case"))
                kind = timing.get("role") or routing.get("stage") or "commitment"
                raw[c.commitment_id] = {"item": item, "kind": kind,
                                        "committer_plays": list(c.committer_roles or [])}
            _CONTRACT_CACHE[key] = raw
        except Exception as exc:  # noqa: BLE001 — fail soft, labeled
            return {}, f"contract unavailable at HEAD: {type(exc).__name__}: {exc}"[:200]
    out = {}
    for cid, meta in raw.items():
        out[cid] = {"item": meta["item"], "kind": meta["kind"],
                    "committers": sorted({plays_to_role.get(p, p) for p in meta["committer_plays"]})}
    return out, "contract"


def committed_payload(run_dir: Path, payload_ref) -> tuple[object, str]:
    """The submitted artifact behind a commitment: ``(parsed, text)``; containment-
    checked, and ``(None, "")`` when it was not retained on disk."""
    if not payload_ref or not isinstance(payload_ref, str):
        return None, ""
    root = Path(run_dir).resolve()
    for base in ("captured", "container_mount", "."):
        candidate = (root / base / payload_ref).resolve()
        if root not in candidate.parents or not candidate.is_file():
            continue
        try:
            raw = candidate.read_text(errors="replace")
        except OSError:
            continue
        try:
            obj = json.loads(raw)
            return obj, json.dumps(obj, indent=2, sort_keys=True)
        except ValueError:
            return raw, raw
    return None, ""


# --- the join ------------------------------------------------------------------ #

_CID_IN_TEXT = re.compile(r'"commitment_id":\s*"([A-Za-z0-9_.\-]+)"')


def build_items(run_dir: Path, events: list[dict], *, manifest: dict | None = None,
                report: dict | None = None) -> dict:
    """Every item's lifecycle for one run.  Returns ``{"items": [...],
    "index_source": "contract" | "adapter" | "none", "notes": [...]}``."""
    run_dir = Path(run_dir)
    if manifest is None:
        try:
            manifest = json.loads((run_dir / "manifest.json").read_text())
        except (OSError, ValueError):
            manifest = {}
    ext = manifest.get("extensions") or {}
    adapter = item_adapter_for(manifest.get("task_pack_id"))
    notes: list[str] = []

    index, source = contract_index(run_dir, manifest)
    if not index:
        notes.append(source)
        if adapter is not None and adapter.commitment_item is not None:
            source = "adapter"
        else:
            source = "none"

    def resolve_cid(cid: str) -> tuple[str | None, str, list[str]]:
        meta = index.get(cid)
        if meta is not None:
            return meta["item"], meta["kind"], meta["committers"]
        if adapter is not None and adapter.commitment_item is not None:
            hit = adapter.commitment_item(cid)
            if hit:
                item, kind, role = hit
                return item, kind, [role] if role else []
        return None, "commitment", []

    days = day_index(events)
    by_id = {e.get("event_id"): e for e in events}
    case_rounds = ((ext.get("clock") or {}).get("case_rounds") or {})
    items: dict[str, dict] = {}

    def item(iid: str) -> dict:
        if iid not in items:
            cr = case_rounds.get(iid) or {}
            items[iid] = {"item_id": iid, "kind": "item", "arrival_day": cr.get("arrival"),
                          "deadline_day": cr.get("deadline"), "arrivals": [],
                          "notified_roles": [], "observed": {}, "received_by": [], "filings": [],
                          "disposition": None, "commitments": [], "lapses": [],
                          "interventions": [], "committers_allowed": [], "score": None}
        return items[iid]

    def _day(e: dict) -> int | None:
        return days.get(e.get("event_id")) if days else None

    # arrivals
    for e in events:
        if e.get("event_class") != "environment.event":
            continue
        ee = (e.get("payload") or {}).get("environment_event") or {}
        pl = ee.get("payload") if isinstance(ee.get("payload"), dict) else {}
        iid = pl.get("case_id")
        if not iid:
            continue
        it = item(str(iid))
        role = ee.get("target_role_id") or e.get("agent_id")
        it["arrivals"].append({"event_id": e.get("event_id"), "seq": e.get("sequence_number"),
                               "day": _day(e), "role": role, "notice_id": pl.get("notice_id"),
                               "type": pl.get("type"), "wave": ee.get("wave_id"),
                               "packet_id": ee.get("packet_id"), "text": pl.get("text") or ""})
        if role and role not in it["notified_roles"]:
            it["notified_roles"].append(role)
        if it["arrival_day"] is None:
            it["arrival_day"] = _day(e)

    # commitments (filings / dispositions / plans) by declared metadata
    cid_to_items: dict[str, list[str]] = {}
    for e in events:
        if e.get("event_class") != "state.committed":
            continue
        sc = (e.get("payload") or {}).get("state_commitment") or {}
        cid = sc.get("commitment_id")
        if not cid:
            continue
        iid, kind, committers = resolve_cid(cid)
        obj = text = None
        parts: dict[str, str] = {}
        if not iid:
            if adapter is None or adapter.payload_items is None:
                continue
            obj, text = committed_payload(run_dir, sc.get("payload_ref"))
            parts = adapter.payload_items(cid, obj) or {}
            if not parts:
                continue
        else:
            obj, text = committed_payload(run_dir, sc.get("payload_ref"))
        turn = e.get("turn_id")
        if not turn:
            for pid in e.get("caused_by_event_ids") or []:
                parent = by_id.get(pid)
                if parent and parent.get("turn_id"):
                    turn = parent["turn_id"]
                    break
        rec = {"event_id": e.get("event_id"), "seq": e.get("sequence_number"), "day": _day(e),
               "agent": sc.get("agent_id") or e.get("agent_id"), "commitment_id": cid,
               "kind": kind, "payload_ref": sc.get("payload_ref"), "text": text,
               "turn_id": turn, "payload": obj if isinstance(obj, dict) else None}
        if parts:
            # One report about several items: each item gets the report as a filing,
            # shown by the part about that item, and the report stays one commitment.
            for part_iid, excerpt in parts.items():
                it = item(str(part_iid))
                for r in committers:
                    if r not in it["committers_allowed"]:
                        it["committers_allowed"].append(r)
                shared = {**rec, "kind": "filing", "text": excerpt, "report_text": text,
                          "covers": sorted(parts)}
                it["commitments"].append(shared)
                it["filings"].append(shared)
            cid_to_items.setdefault(cid, []).extend(sorted(parts))
            continue
        it = item(str(iid))
        for r in committers:
            if r not in it["committers_allowed"]:
                it["committers_allowed"].append(r)
        it["commitments"].append(rec)
        cid_to_items.setdefault(cid, []).append(str(iid))
        if kind == "disposition":
            it["disposition"] = rec  # the last disposition commit is the one that stands
        elif kind != "plan":
            it["filings"].append(rec)

    # who was handed a filing about the item (the broadcast's recipients)
    for e in events:
        if e.get("event_class") != "handoff":
            continue
        p = e.get("payload") or {}
        ref = (p.get("handoff_delta") or {}).get("formalized_payload_ref") or ""
        cid = ref.rsplit("/", 1)[-1].rsplit(".", 1)[0] if ref else None
        to = p.get("to_agent")
        for iid in (cid_to_items.get(cid) or []) if cid else []:
            if iid in items and to and to not in items[iid]["received_by"]:
                items[iid]["received_by"].append(to)

    # first sight per role: a notice, or a filing seen on the record
    for e in events:
        if e.get("event_class") != "agent.observed":
            continue
        role = e.get("agent_id")
        for o in (e.get("payload") or {}).get("observations") or []:
            kind = o.get("kind")
            pl = o.get("payload")
            seen: list[str] = []
            via = None
            if kind == "environment_event" and isinstance(pl, dict):
                seen, via = ([str(pl["case_id"])] if pl.get("case_id") else []), "notice"
            elif kind == "handoff" and isinstance(pl, str):
                m = _CID_IN_TEXT.search(pl)
                if m:
                    seen, via = cid_to_items.get(m.group(1)) or [], f"filing {m.group(1)}"
            for iid in seen:
                if iid in items and role:
                    obs = items[iid]["observed"]
                    if role not in obs:
                        obs[role] = {"day": _day(e), "seq": e.get("sequence_number"),
                                     "event_id": e.get("event_id"), "via": via}

    # lapses and interventions
    for e in events:
        cls = e.get("event_class")
        p = e.get("payload") or {}
        if cls == "capacity.deadline_lapse" and p.get("case_id") in items:
            items[p["case_id"]]["lapses"].append({
                "event_id": e.get("event_id"), "seq": e.get("sequence_number"), "day": _day(e),
                "deadline_round": p.get("deadline_round"), "forced": bool(p.get("forced"))})
        elif cls == "intervention.recorded":
            text = " ".join(str(x) for x in (p.get("problems") or []))
            hit = None
            for cid, iids in cid_to_items.items():
                if len(iids) == 1 and cid in text:  # a report about several cases names none
                    hit = iids[0]
                    break
            if hit is None:
                for iid in items:
                    if iid in text:
                        hit = iid
                        break
            if hit:
                items[hit]["interventions"].append({
                    "event_id": e.get("event_id"), "seq": e.get("sequence_number"),
                    "day": _day(e), "agent": e.get("agent_id"), "kind": p.get("kind"),
                    "problems": list(p.get("problems") or [])})

    # scores (pack report) and the derived lens
    rows = adapter.score_rows(report) if (adapter is not None and report) else {}
    for iid, it in items.items():
        it["score"] = rows.get(iid)
        if it["score"] and it["score"].get("coverage"):
            it["kind"] = it["score"]["coverage"]
        elif it["disposition"] or it["filings"]:
            it["kind"] = "exception"
        it["notified_roles"].sort()
        it["received_by"].sort()
        d = it["disposition"]
        it["committer_in_notified"] = (d["agent"] in it["notified_roles"]) if d and it["notified_roles"] else None

    ordered = sorted(items.values(), key=lambda it: (it["arrival_day"] if it["arrival_day"] is not None else 10**6,
                                                     _natural(it["item_id"])))
    return {"items": ordered, "index_source": source, "notes": notes}


def _natural(s: str) -> tuple:
    return tuple(int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s))


def turn_context(events: list[dict], turn_id: str | None) -> dict:
    """What one turn held: its observations (what the agent saw at wake) and its
    reasoning steps — the "what the disposer saw" panel."""
    if not turn_id:
        return {"turn_id": None, "observations": [], "thinking": []}
    observations: list[dict] = []
    thinking: list[dict] = []
    for e in events:
        if e.get("turn_id") != turn_id:
            continue
        p = e.get("payload") or {}
        if e.get("event_class") == "agent.observed":
            for o in p.get("observations") or []:
                observations.append({"kind": o.get("kind"), "payload": o.get("payload"),
                                     "event_id": e.get("event_id")})
        elif e.get("event_class") == "reasoning.step":
            thinking.append({"event_id": e.get("event_id"), "seq": e.get("sequence_number"),
                             "narration": p.get("narration") or "", "thinking": p.get("thinking") or ""})
    return {"turn_id": turn_id, "observations": observations, "thinking": thinking}
