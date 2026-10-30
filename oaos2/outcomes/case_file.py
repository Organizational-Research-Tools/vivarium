"""The case file re-delivered with a disposition duty.

The CH2 workload pilot (2026-09-24) showed every hierarchy dismissal caused by the
integrator's context compaction: a wave's six quarter reports arrived together, the recap
kept one case, and the disposition slot's duty notice restated the schema without the
case's records, while the role held no tool to read its correspondence. A real official
opens the case file when the case comes up. So a commitment may declare, in its
``submission`` block::

    case_file:
      case_id: C-S6
      records: {from_prefix: exception_report_, records_field: exception_records,
                id_field: exception_id}
      notices: true
      alternatives: {from_notice_field: options}   # optional

and the platform renders, with every duty notice that binds the slot, the records already
committed on that case (from every commitment whose id starts with ``from_prefix``, taking
the entries of ``records_field`` whose ``id_field`` equals the case id) and — when
``notices`` is true — the environment notices THIS agent received on the case. It re-delivers
only what the agent already had: an integrator that never received notices sees none, so
the arms' visibility rules are untouched. Apparatus text, arm-identical, never a treatment.

``alternatives`` (LK1 pilot, 2026-10-04) lists the case's alternatives as the released
notices letter them, read from the named field (``[{id, text}, ...]``) of any notice on the
case that the environment has released to any role. A decision duty that asks for "the
letter, exactly as the notices label it" must show its decider the letters: in the pilot a
center that never received the notices guessed them. The alternatives are the decision's
menu, not a notice's content, and are rendered whoever decides; read at run time, they are
those of the schedule actually running.
"""
from __future__ import annotations

import json


def case_file_spec(commitment) -> dict | None:
    spec = (getattr(commitment, "submission", None) or {}).get("case_file")
    return dict(spec) if isinstance(spec, dict) else None


def collect_records(payloads: dict, spec: dict) -> list[tuple[str, dict]]:
    """(source commitment id, record) for every committed record on the case, in commit order."""
    case_id = str(spec.get("case_id", ""))
    rspec = spec.get("records") or {}
    prefix = str(rspec.get("from_prefix") or "")
    if not prefix:  # the contract names the commitments its records come from
        return []
    field = str(rspec.get("records_field", "exception_records"))
    id_field = str(rspec.get("id_field", "exception_id"))
    out: list[tuple[str, dict]] = []
    for cid, payload in payloads.items():
        if not str(cid).startswith(prefix) or not isinstance(payload, dict):
            continue
        records = payload.get(field)
        if isinstance(records, list):
            for record in records:
                if isinstance(record, dict) and str(record.get(id_field, "")).strip() == case_id:
                    out.append((str(cid), record))
        elif str(payload.get(id_field, "")).strip() == case_id:
            out.append((str(cid), payload))
    return out


def case_alternatives(spec: dict, released: list[dict] | None) -> list[dict]:
    """The alternatives the spec asks for, from the first released notice that carries them."""
    field = ((spec.get("alternatives") or {}) if isinstance(spec.get("alternatives"), dict) else {}).get(
        "from_notice_field")
    if not field:
        return []
    for notice in released or []:
        items = notice.get(field) if isinstance(notice, dict) else None
        if isinstance(items, list) and items:
            return [{"id": i.get("id"), "text": i.get("text")} for i in items if isinstance(i, dict)]
    return []


def render_case_file(spec: dict, *, payloads: dict, notices: dict[str, list[dict]] | None = None,
                     exchange_lines: list[str] | None = None, released: list[dict] | None = None) -> str:
    """The text appended to a duty notice; empty when the spec is absent."""
    if not spec:
        return ""
    case_id = str(spec.get("case_id", ""))
    lines = [f"# Case file for {case_id} (re-delivered with this duty)"]
    alternatives = case_alternatives(spec, released)
    if alternatives:
        lines.append("The alternatives on this case, as the notices label them:")
        lines.extend(f"({a.get('id')}) {a.get('text')}" for a in alternatives)
    records = collect_records(payloads, spec)
    if records:
        lines.append("Records committed on this case:")
        for cid, record in records:
            lines.append(f"- from `{cid}`: {json.dumps(record, sort_keys=True)}")
    else:
        lines.append("No record on this case has been committed yet.")
    if spec.get("notices"):
        received = list((notices or {}).get(case_id) or [])
        if received:
            lines.append("Notices you received on this case:")
            for packet in received:
                lines.append(json.dumps(packet, sort_keys=True, indent=2))
    if exchange_lines:
        # queries, replies and assents this role sent or received on the case (2026-09-25)
        lines.append("Queries, replies and assents on this case:")
        lines.extend(f"- {line}" for line in exchange_lines)
    return "\n".join(lines) + "\n"
