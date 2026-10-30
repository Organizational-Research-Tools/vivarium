"""Reconstruct available design records and compare them with the current library.

Reads saved cell settings, prompt envelopes, and schedule classifications. The
organization panel reads today's library preset and reports whether its hash
matches the run's saved hash; it cannot reconstruct a removed or changed original
preset from that hash alone. Recorded channel use is reported separately. A
missing declaration in this comparison is not itself a permission violation.

The design.* labels describe assigned settings available to this reader, while
derived.* labels summarize observations and code.* labels are researcher coding.
These views support comparison; they do not identify a treatment effect on their own.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from oaos2.library import library_dir


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def cell_of(manifest: dict) -> dict:
    """Read saved cell settings; the replicate label is parsed from run_id."""
    ext = manifest.get("extensions") or {}
    clock = ext.get("clock_spec") or ext.get("clock") or {}
    rep = re.search(r"__rep(\d+)__", manifest.get("run_id") or "")
    return {
        "experiment": manifest.get("experiment_id"),
        "form": manifest.get("organization_id"),
        "requirement": ext.get("difficulty"),
        "clock_variant": clock.get("schedule_variant") or ext.get("environment_schedule_variant"),
        "rep": int(rep.group(1)) if rep else None,
        "contract_profile": ext.get("contract_profile"),
        "model": ext.get("model_ref"),
        "mode": manifest.get("mode"),
        "rounds_total": clock.get("rounds_total"),
        "calls_per_day": clock.get("calls_per_day"),
        "megabatch": clock.get("megabatch"),
        "cap_usd": ext.get("cap_usd"),
    }


def cell_label(manifest: dict) -> str:
    c = cell_of(manifest)
    parts = [c["form"], c["requirement"], c["clock_variant"],
             f"rep{c['rep']}" if c["rep"] is not None else None]
    return " · ".join(str(p) for p in parts if p)


def organization_of(manifest: dict) -> dict:
    """The organization as the library holds it now, with the pin check against
    the run's ``organization_sha256`` — a mismatch is labeled, never hidden."""
    org_id = manifest.get("organization_id")
    ext = manifest.get("extensions") or {}
    out = {"preset_id": org_id, "source": "unavailable", "pin_ok": None, "roles": {},
           "contribution_visibility": None, "scheduler": None, "mode": None, "note": None}
    if not org_id:
        return out
    from oaos2.organizations.loader import org_path
    path = org_path(org_id)
    try:
        current_sha = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        out["note"] = f"organization preset {org_id!r} is not in the library"
        return out
    pinned = ext.get("organization_sha256")
    out["pin_ok"] = (pinned == current_sha) if pinned else None
    for base in ext.get("organization_bases") or []:  # an overlay preset is current only if its bases are
        try:
            now = "sha256:" + hashlib.sha256(Path(base["ref"]).read_bytes()).hexdigest()
        except (OSError, KeyError, TypeError):
            now = None
        if now != base.get("sha256"):
            out["pin_ok"] = False
    try:
        from oaos2.organizations.loader import load_org_spec
        spec = load_org_spec(org_id)
    except Exception as exc:  # noqa: BLE001 — labeled, not fatal
        out["note"] = f"organization failed to load: {type(exc).__name__}: {exc}"[:200]
        return out
    out["source"] = "library@HEAD"
    out["scheduler"] = getattr(spec, "scheduler", None)
    lc = getattr(spec, "live_coordination", None) or {}
    out["mode"] = lc.get("mode") if isinstance(lc, dict) else None
    out["contribution_visibility"] = lc.get("contribution_visibility") if isinstance(lc, dict) else None
    out["disclosure"] = lc.get("disclosure") if isinstance(lc, dict) else None
    channels_out: dict[str, list[str]] = {}
    channels_in: dict[str, list[str]] = {}
    topo = getattr(spec, "topology", None)
    for ch in (getattr(topo, "channels", None) or []):
        channels_out.setdefault(ch.from_role, []).append(ch.to_role)
        channels_in.setdefault(ch.to_role, []).append(ch.from_role)
    comm_actions = communication_actions(manifest.get("task_pack_id"))
    org_tools = getattr(spec, "tools", None)
    for r in getattr(spec, "roles", []) or []:
        dr = getattr(r, "decision_rights", None)
        role_tools = getattr(r, "tools", None)
        effective = role_tools if role_tools is not None else org_tools
        out["roles"][r.role_id] = {
            "plays": list(getattr(r, "plays", []) or []),
            "role_packet": getattr(r, "role_packet", None),
            "attention": getattr(r, "attention", None),
            "tools": sorted(getattr(r, "tools", []) or []),
            # The organization's declaration of who may communicate voluntarily (M8 §7):
            # the board/note actions in the role's effective tool grant. None means the
            # preset restricts nothing, so every declared action is available.
            "comm_grants": sorted(a for a in comm_actions
                                  if effective is None or a in effective),
            "comm_kinds": sorted(getattr(r, "comm_kinds", []) or []),
            "max_calls_per_slot": getattr(r, "max_calls_per_slot", None),
            "context_budget_tokens": getattr(r, "context_budget_tokens", None),
            "may_submit_milestones": getattr(dr, "may_submit_milestones", None),
            "may_accept_handoffs_from": sorted(getattr(dr, "may_accept_handoffs_from", ()) or ()),
            "review_authority_over": sorted(getattr(dr, "review_authority_over", ()) or ()),
            "channels_out": sorted(channels_out.get(r.role_id, [])),
            "channels_in": sorted(channels_in.get(r.role_id, [])),
        }
    return out


_BOARD_MODULE = "oaos2.communication.board"


def communication_actions(task_pack_id: str | None) -> dict[str, str]:
    """``action name → handler`` for the actions a pack declares from the platform's
    board module (post, read_board, send_note, read_notes, and the forum's start_thread, reply,
    board_index, read_thread, read_post). Read from the manifest, so
    shared code never lists a pack's action names; a pack that declares none, or
    whose manifest cannot be read, yields an empty map."""
    if not task_pack_id:
        return {}
    try:
        from oaos2.tasks.loader import load_manifest
        manifest = load_manifest(task_pack_id)
    except Exception:  # noqa: BLE001 — labeled elsewhere; here it is simply "none declared"
        return {}
    return {a["name"]: a.get("handler") or "" for a in (manifest.get("actions") or [])
            if isinstance(a, dict) and a.get("module") == _BOARD_MODULE and a.get("name")}


def envelopes_of(run_dir: Path) -> dict[str, dict]:
    """``role_id → prompt envelope`` as archived (system prompt, task text, role
    packet, tier, first duty) — the condition as each agent was told it."""
    out = {}
    for p in sorted(Path(run_dir).glob("config/prompt_envelope_*.json")):
        env = _read_json(p)
        if isinstance(env, dict):
            out[env.get("agent_id") or p.stem.replace("prompt_envelope_", "")] = env
    return out


def packets_of(run_dir: Path) -> dict[str, dict]:
    """``packet_id → {wave, targets, classification, case_id, notice_id, type}`` from
    the run-local schedule — the researcher-side classification agents never see."""
    sched = _read_json(Path(run_dir) / "config" / "environment_schedule.json")
    out = {}
    if not isinstance(sched, dict):
        return out
    for wave in sched.get("waves") or []:
        for pk in wave.get("packets") or []:
            pl = pk.get("payload") if isinstance(pk.get("payload"), dict) else {}
            out[pk.get("packet_id")] = {
                "wave": wave.get("wave_id"), "trigger": wave.get("trigger_commitment_id"),
                "targets": list(pk.get("target_scopes") or []),
                "classification": pk.get("classification") or {},
                "case_id": pl.get("case_id"), "notice_id": pl.get("notice_id"), "type": pl.get("type"),
            }
    return out


def run_design(run_dir: Path, manifest: dict | None = None) -> dict:
    run_dir = Path(run_dir)
    manifest = manifest or _read_json(run_dir / "manifest.json") or {}
    ext = manifest.get("extensions") or {}
    return {
        "cell": cell_of(manifest),
        "cell_label": cell_label(manifest),
        "organization": organization_of(manifest),
        "envelopes": envelopes_of(run_dir),
        "packets": packets_of(run_dir),
        "clock": ext.get("clock") or ext.get("clock_spec") or {},
        "pins": {"organization_sha256": ext.get("organization_sha256"),
                 "task_manifest_sha256": ext.get("task_manifest_sha256"),
                 "environment_schedule_sha256": ext.get("environment_schedule_sha256"),
                 "role_prompt_sha256s": ext.get("role_prompt_sha256s")},
    }


def design_labels(run_dir: Path, manifest: dict | None = None) -> dict:
    """The ``design.*`` namespace for one run: cell labels every event inherits, and
    per-role / per-packet labels for the joins."""
    d = run_design(run_dir, manifest)
    cell = {f"design.cell.{k}": v for k, v in d["cell"].items() if v is not None}
    roles = {rid: {"design.role.packet": r.get("role_packet"),
                   "design.role.channels_out": r.get("channels_out"),
                   "design.role.comm_grants": r.get("comm_grants"),
                   "design.role.review_authority_over": r.get("review_authority_over"),
                   "design.role.max_calls_per_slot": r.get("max_calls_per_slot")}
             for rid, r in d["organization"]["roles"].items()}
    packets = {pid: {"design.packet.coverage": (p["classification"] or {}).get("rule_coverage"),
                     "design.packet.rule_ref": (p["classification"] or {}).get("rule_ref"),
                     "design.packet.arrival_round": (p["classification"] or {}).get("arrival_round"),
                     "design.packet.response_deadline_round": (p["classification"] or {}).get("response_deadline_round"),
                     "design.packet.wave": p["wave"], "design.packet.case_id": p["case_id"]}
               for pid, p in d["packets"].items()}
    return {"cell": cell, "roles": roles, "packets": packets}


# --- realization: the treatment exercised, as against available --------------- #

BOARD = "board"  # the pseudo-recipient of a post: every other active agent

def realization(events: list[dict], design: dict, items: list[dict] | None = None) -> dict:
    """Where the condition was USED, per channel and per role: declared channels
    against handoffs actually sent (with the first exercise), dispositions each
    role was allowed to commit against those it did, filings, calls.  Observables
    only — the manipulation check as a reading instrument."""
    roles = design["organization"]["roles"]
    declared: set[tuple[str, str]] = set()
    for rid, r in roles.items():
        for to in r.get("channels_out") or []:
            declared.add((rid, to))
    # Voluntary channels (M8 §7): a role that may post is declared toward the board;
    # a role that may send notes is declared toward every other role. What the router
    # further checks (topology, comm kinds) is recorded as refusals, not assumed here.
    # A forum board (October 10, 2026) posts by start_thread and reply.
    may_post = {rid for rid, r in roles.items() if {"post", "start_thread", "reply"} & set(r.get("comm_grants") or [])}
    may_note = {rid for rid, r in roles.items() if "send_note" in (r.get("comm_grants") or [])}
    declared_board = {(rid, BOARD) for rid in may_post}
    declared_notes = {(a, b) for a in may_note for b in roles if b != a}
    use: dict[tuple[str, str], dict] = {}
    use_board: dict[tuple[str, str], dict] = {}
    use_notes: dict[tuple[str, str], dict] = {}
    _ROLE_ZERO = {"handoffs_out": 0, "handoffs_in": 0, "filings": 0,
                  "dispositions": 0, "dispositions_allowed": 0,
                  "calls": 0, "ceiling_hits": 0, "compactions": 0,
                  "posts": 0, "notes_out": 0, "notes_in": 0, "board_reads": 0, "note_reads": 0}
    per_role: dict[str, dict] = {rid: dict(_ROLE_ZERO) for rid in roles}

    def role(rid: str | None) -> dict:
        return per_role.setdefault(rid or "·", dict(_ROLE_ZERO))

    def _first(table: dict, key: tuple[str, str], e: dict) -> None:
        u = table.setdefault(key, {"n": 0, "first_seq": e.get("sequence_number"),
                                   "first_event_id": e.get("event_id")})
        u["n"] += 1

    for e in events:
        cls = e.get("event_class")
        p = e.get("payload") or {}
        if cls == "handoff":
            src, dst = p.get("from_agent") or e.get("agent_id"), p.get("to_agent")
            if not src or not dst:
                continue
            _first(use, (src, dst), e)
            role(src)["handoffs_out"] += 1
            role(dst)["handoffs_in"] += 1
        elif cls == "board.posted" and e.get("agent_id"):
            _first(use_board, (e["agent_id"], BOARD), e)
            role(e["agent_id"])["posts"] += 1
        elif cls == "message.sent" and p.get("kind") == "note" and e.get("agent_id") and p.get("to"):
            _first(use_notes, (e["agent_id"], p["to"]), e)
            role(e["agent_id"])["notes_out"] += 1
            role(p["to"])["notes_in"] += 1
        elif cls == "board.retrieved":
            role(e.get("agent_id"))["board_reads"] += 1
        elif cls == "notes.retrieved":
            role(e.get("agent_id"))["note_reads"] += 1
        elif cls == "model.invoked":
            role(e.get("agent_id"))["calls"] += 1
        elif cls == "capacity.slot_ceiling":
            role(e.get("agent_id"))["ceiling_hits"] += 1
        elif cls == "context.compaction":
            role(e.get("agent_id"))["compactions"] += 1

    for it in items or []:
        for r in it.get("committers_allowed") or []:
            role(r)["dispositions_allowed"] += 1
        for f in it.get("filings") or []:
            role(f.get("agent"))["filings"] += 1
        d = it.get("disposition")
        if d:
            role(d.get("agent"))["dispositions"] += 1

    channels = []
    for kind, declared_set, used_map in (("handoff", declared, use),
                                         ("board", declared_board, use_board),
                                         ("note", declared_notes, use_notes)):
        for key in sorted(declared_set | set(used_map)):
            u = used_map.get(key) or {}
            channels.append({"from": key[0], "to": key[1], "kind": kind,
                             "declared": key in declared_set,
                             "used": u.get("n", 0), "first_seq": u.get("first_seq"),
                             "first_event_id": u.get("first_event_id")})
    n_declared = len(declared) + len(declared_board) + len(declared_notes)
    n_used = sum(1 for c in channels if c["declared"] and c["used"])
    locus = {"committer_in_notified": sum(1 for it in items or [] if it.get("committer_in_notified") is True),
             "committer_not_notified": sum(1 for it in items or [] if it.get("committer_in_notified") is False),
             "undisposed": sum(1 for it in items or [] if it.get("disposition") is None)}
    return {"channels": channels, "n_declared": n_declared, "n_used": n_used,
            "undeclared_used": [c for c in channels if not c["declared"]],
            "roles": per_role, "locus": locus}


def arm_diff(design_a: dict, design_b: dict) -> dict:
    """Diff selected cell/organization fields and initial prompt text.
+    Organization fields come from the current library. This is not an exhaustive
+    setup comparison: absent data and omitted fields can yield an empty diff."""
    import difflib

    def _lines_org(d: dict) -> list[str]:
        out = []
        o = d["organization"]
        out.append(f"preset: {o.get('preset_id')} · mode {o.get('mode')} · visibility {o.get('contribution_visibility')}"
                   + (f" · disclosure {o.get('disclosure')}" if o.get("disclosure") else ""))
        for rid, r in sorted(o["roles"].items()):
            out.append(f"{rid}: packet={r.get('role_packet')} channels_out={','.join(r.get('channels_out') or [])}"
                       f" accepts_from={','.join(r.get('may_accept_handoffs_from') or [])}"
                       f" review_over={','.join(r.get('review_authority_over') or [])}"
                       f" calls_per_slot={r.get('max_calls_per_slot')} context={r.get('context_budget_tokens')}")
        return out

    def _diff(a: list[str], b: list[str], name: str) -> str:
        return "\n".join(difflib.unified_diff(a, b, fromfile=f"a/{name}", tofile=f"b/{name}", lineterm="", n=2))

    cell = _diff([f"{k}: {v}" for k, v in sorted(design_a["cell"].items())],
                 [f"{k}: {v}" for k, v in sorted(design_b["cell"].items())], "cell")
    org = _diff(_lines_org(design_a), _lines_org(design_b), "organization")
    envelopes = {}
    roles = sorted(set(design_a["envelopes"]) | set(design_b["envelopes"]))
    for rid in roles:
        ea, eb = design_a["envelopes"].get(rid) or {}, design_b["envelopes"].get(rid) or {}
        parts = []
        for field in ("system_prompt", "initial_user_text"):
            parts.append(_diff((ea.get(field) or "").splitlines(), (eb.get(field) or "").splitlines(),
                               f"{rid}/{field}"))
        envelopes[rid] = "\n".join(x for x in parts if x)
    return {"cell": cell, "organization": org, "envelopes": envelopes,
            "identical_envelopes": [r for r, d in envelopes.items() if not d]}
