"""Cases index and dossier view models (DASHBOARD.md §4.3c) — read-only.

The dossier opens BLIND: lifecycle, what each role received, the filings and the
disposition as written, what the disposer saw, the condition the role was under.
OPEN mode adds the supplied task report's verdict and outcome; the saved key sits
behind a further explicit reveal and renders only when the asset hashes to the
run's own pin (``ItemAdapter.key_for``).  Nothing here computes a construct: the
one derived field, "committer is among the notified", is a labeled lens the reader
switches on.
"""

from __future__ import annotations

import re
from pathlib import Path

from oaos2.archive import cite as citelib
from oaos2.archive.clock import day_index
from oaos2.archive.design import cell_label, run_design
from oaos2.archive.items import build_items, item_adapter_for, turn_context

MODES = ("blind", "open")


def cases_index(run_dir: Path, events: list[dict], manifest: dict, report: dict | None) -> dict:
    built = build_items(run_dir, events, manifest=manifest, report=report)
    rows = []
    for it in built["items"]:
        d = it["disposition"]
        rows.append({
            "item_id": it["item_id"], "kind": it["kind"],
            "arrival_day": it["arrival_day"], "deadline_day": it["deadline_day"],
            "notified": it["notified_roles"],
            "filings": [(f["agent"], f["day"]) for f in it["filings"]],
            "disposed_day": d["day"] if d else None, "disposer": d["agent"] if d else None,
            "disposition": (d["payload"] or {}).get("disposition") if d and d["payload"] else None,
            "late": (d is not None and d["day"] is not None and it["deadline_day"] is not None
                     and d["day"] > it["deadline_day"]),
            "lapses": len(it["lapses"]), "interventions": len(it["interventions"]),
            "committer_in_notified": it["committer_in_notified"],
            "score": it["score"],
        })
    return {"rows": rows, "index_source": built["index_source"], "notes": built["notes"],
            "n_scored": sum(1 for r in rows if r["score"])}


_SENTENCE = re.compile(r"(?<=[.;:])\s+")


def _norm(s: str) -> str:
    return " ".join((s or "").replace("’", "'").split()).lower()


def _highlights(sources: list[str], target: str) -> list[str]:
    """Sentences (≥ 25 chars) from the filings that appear verbatim in the disposer's
    thinking — string presence, labeled as such, never "fact used"."""
    hay = _norm(target)
    out: list[str] = []
    for src in sources:
        for sent in _SENTENCE.split(src or ""):
            sent = sent.strip()
            if len(sent) >= 25 and _norm(sent).strip(" .") in hay and sent not in out:
                out.append(sent)
    return out


def case_dossier(run_dir: Path, run_ref: str, events: list[dict], manifest: dict,
                 report: dict | None, item_id: str, *, mode: str = "blind",
                 reveal_key: bool = False, lens: bool = False) -> dict | None:
    built = build_items(run_dir, events, manifest=manifest, report=report)
    it = next((x for x in built["items"] if x["item_id"] == item_id), None)
    if it is None:
        return None
    mode = mode if mode in MODES else "blind"
    days = day_index(events)
    design = run_design(run_dir, manifest)

    def _cite(eid: str | None) -> str | None:
        e = next((x for x in events if x.get("event_id") == eid), None) if eid else None
        return citelib.event_citation(run_ref, e, days.get(eid)) if e else None

    # filings and disposition as written, each with its citation
    filings = [{**f, "citation": _cite(f["event_id"]),
                "file_citation": _file_cite(run_dir, run_ref, f["payload_ref"])} for f in it["filings"]]
    disposition = None
    disposer = {"turn_id": None, "observations": [], "thinking": []}
    if it["disposition"]:
        d = it["disposition"]
        disposition = {**d, "citation": _cite(d["event_id"]),
                       "file_citation": _file_cite(run_dir, run_ref, d["payload_ref"])}
        disposer = turn_context(events, d["turn_id"])
        sources = [f["text"] for f in it["filings"]] + [a["text"] for a in it["arrivals"]]
        for t in disposer["thinking"]:
            t["highlights"] = _highlights(sources, t["thinking"] + " " + t["narration"])
        disposer["condition"] = _condition(design, events, days, d["agent"], d["day"])

    # timeline: everything that happened to this item, in order
    timeline: list[dict] = []
    for a in it["arrivals"]:
        timeline.append({"seq": a["seq"], "day": a["day"], "what": "notice",
                         "text": f"{a['notice_id'] or a['packet_id']} → {a['role']}"
                                 + (f" · {a['type']}" if a["type"] else ""),
                         "event_id": a["event_id"]})
    for role, o in sorted(it["observed"].items(), key=lambda kv: kv[1]["seq"] or 0):
        timeline.append({"seq": o["seq"], "day": o["day"], "what": "seen",
                         "text": f"{role} first sees it ({o['via']})", "event_id": o["event_id"]})
    for f in it["filings"]:
        timeline.append({"seq": f["seq"], "day": f["day"], "what": "filing",
                         "text": f"{f['commitment_id']} by {f['agent']}", "event_id": f["event_id"]})
    for x in it["interventions"]:
        timeline.append({"seq": x["seq"], "day": x["day"], "what": "intervention",
                         "text": f"{x['agent']}: {x['kind']} — {'; '.join(x['problems'])[:160]}",
                         "event_id": x["event_id"]})
    for lp in it["lapses"]:
        timeline.append({"seq": lp["seq"], "day": lp["day"], "what": "lapse",
                         "text": f"fuse lapsed (deadline day {lp['deadline_round']})"
                                 + (" · forced" if lp["forced"] else ""), "event_id": lp["event_id"]})
    if it["disposition"]:
        d = it["disposition"]
        timeline.append({"seq": d["seq"], "day": d["day"], "what": "disposition",
                         "text": f"{d['commitment_id']} by {d['agent']}"
                                 + (f" · {(d['payload'] or {}).get('disposition')}" if d["payload"] else ""),
                         "event_id": d["event_id"]})
    timeline.sort(key=lambda t: (t["seq"] or 0))

    key = None
    if mode == "open" and reveal_key:
        adapter = item_adapter_for(manifest.get("task_pack_id"))
        key = adapter.key_for(run_dir, manifest, item_id) if adapter else None

    annotate_ids = [f["event_id"] for f in it["filings"]] + \
        ([it["disposition"]["event_id"]] if it["disposition"] else [])
    return {
        "item": it, "mode": mode, "reveal_key": reveal_key, "lens": lens,
        "cell_label": cell_label(manifest) if mode == "open" else None,
        "timeline": timeline, "filings": filings, "disposition": disposition,
        "disposer": disposer, "score": it["score"] if mode == "open" else None,
        "key": key, "annotate_ids": annotate_ids,
        "index_source": built["index_source"], "notes": built["notes"],
        "design_roles": design["organization"]["roles"],
        "org_pin_ok": design["organization"]["pin_ok"],
    }


def _file_cite(run_dir: Path, run_ref: str, payload_ref) -> str | None:
    if not payload_ref or not isinstance(payload_ref, str):
        return None
    root = Path(run_dir).resolve()
    for base in ("captured", "container_mount", "."):
        candidate = (root / base / payload_ref).resolve()
        if root in candidate.parents and candidate.is_file():
            return citelib.file_citation(run_ref, payload_ref, candidate.read_bytes())
    return None


def _condition(design: dict, events: list[dict], days: dict, role: str | None,
               day: int | None) -> dict:
    """What the role held when it decided: its envelope, channels, rights, ceilings,
    the duty text it had that day, and the constraints that fired on it that day."""
    env = design["envelopes"].get(role) or {}
    org_role = design["organization"]["roles"].get(role) or {}
    duty, constraints, calls = None, [], 0
    for e in events:
        if e.get("agent_id") != role:
            continue
        if days and days.get(e.get("event_id")) != day:
            continue
        cls = e.get("event_class")
        p = e.get("payload") or {}
        if cls == "agent.observed":
            for o in p.get("observations") or []:
                if o.get("kind") in ("stage_assignment", "clock_notice"):
                    duty = (duty or "") + ("\n" if duty else "") + str(o.get("payload") or "")[:600]
        elif cls == "model.invoked":
            calls += 1
        elif cls in ("context.compaction", "capacity.slot_ceiling", "capacity.deadline_lapse",
                     "intervention.recorded"):
            constraints.append({"cls": cls, "event_id": e.get("event_id"),
                                "summary": _short(p)})
    return {"role": role, "day": day, "envelope": env, "org_role": org_role, "duty": duty,
            "constraints": constraints, "calls_used": calls,
            "calls_per_day": design["cell"].get("calls_per_day"),
            "org_source": design["organization"]["source"],
            "org_pin_ok": design["organization"]["pin_ok"]}


def _short(p: dict) -> str:
    if "tokens_before" in p:
        return f"compacted {p.get('tokens_before')} → {p.get('tokens_after')} tokens"
    if "problems" in p:
        return "; ".join(str(x) for x in p.get("problems") or [])[:160]
    return ", ".join(f"{k}={v}" for k, v in sorted(p.items()) if isinstance(v, (str, int, float)))[:160]


def casebook_markdown(run_dir: Path, run_ref: str, events: list[dict], manifest: dict,
                      report: dict | None, *, mode: str = "blind") -> str:
    """Deterministic per-run casebook: every item, blind content first; verdicts
    only in open mode.  Greppable, diffable, citable without the server."""
    built = build_items(run_dir, events, manifest=manifest, report=report)
    days = day_index(events)
    lines = [f"# Casebook · {run_ref}", "",
             f"mode: {mode} · items: {len(built['items'])} · index: {built['index_source']}", ""]
    for it in built["items"]:
        lines.append(f"## {it['item_id']} · {it['kind']}")
        lines.append(f"arrival day {it['arrival_day']} · fuse day {it['deadline_day']} · "
                     f"notified: {', '.join(it['notified_roles']) or '—'}")
        for a in it["arrivals"]:
            lines.append(f"- notice {a['notice_id'] or a['packet_id']} → {a['role']} (day {a['day']}): {a['text']}")
        for f in it["filings"]:
            e = next((x for x in events if x.get("event_id") == f["event_id"]), None)
            c = citelib.event_citation(run_ref, e, days.get(f["event_id"])) if e else ""
            lines += [f"- filing {f['commitment_id']} by {f['agent']} (day {f['day']})", f"  `{c}`",
                      "  ```", *("  " + ln for ln in f["text"].splitlines()), "  ```"]
        d = it["disposition"]
        if d:
            e = next((x for x in events if x.get("event_id") == d["event_id"]), None)
            c = citelib.event_citation(run_ref, e, days.get(d["event_id"])) if e else ""
            lines += [f"- disposition {d['commitment_id']} by {d['agent']} (day {d['day']})", f"  `{c}`",
                      "  ```", *("  " + ln for ln in d["text"].splitlines()), "  ```"]
        for lp in it["lapses"]:
            lines.append(f"- fuse lapsed day {lp['day']} (deadline {lp['deadline_round']})")
        if mode == "open" and it["score"]:
            s = it["score"]
            lines.append(f"- scored: {s.get('outcome')} · verdict {s.get('verdict')} ({s.get('verdict_source')})"
                         f" · lost {s.get('lost_benefit')}")
        lines.append("")
    return "\n".join(lines) + "\n"
