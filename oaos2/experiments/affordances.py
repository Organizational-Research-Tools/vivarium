"""Readiness audit: every affordance a role is told about must be one it can use.

The original budget-execution experiment told every role, in each day's clock notice,
that its correspondence was "kept on file" under a path and that filed submissions were
"on record" under another, while no role in any arm held a tool that could read a file.
Its officer packet also described repair and follow-up slots that the clocked contract
profiles do not issue. The 2026-09-24/25 audits found zero file reads in 48 confirmatory
runs and dismissals citing records the integrator "could not access". A promise nothing
can act on is worse than silence: it makes an agent's failure look like a choice.

``audit_affordances`` lints the texts a role will actually see — its resolved system
prompt and initial user text from the pack, plus any standing notice templates the
runner sends — for three classes of promise, and checks each against what the role is
granted:

- **path promises** (``/work/...``, ``/visible/...``): usable only by a role granted
  ``read_file`` or ``run_python``; ``/work/submitted`` is readable by no tool at all;
- **tool promises** (a named built-in tool, or "read tool"): the tool must be granted;
- **slot promises** ("repair slot", "follow-up slot", "query slot" and their report
  forms): the tier's contract profile must issue a commitment of that kind.

It returns findings, never fixes anything. The runner records the findings in every
run's ``config/affordance_audit.json`` and, under ``affordance_check="strict"``, refuses
to stage a run that has any. Study presets that must be clean opt into strict; legacy
presets run with a warning so frozen prompts are never silently rewritten.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

_PATH_RE = re.compile(r"(?<![\w/])(/work/[\w./-]+|/visible/[\w./-]+)")
_TOOL_WORDS = {
    "read_file": re.compile(r"\bread_file\b|\bread tool\b", re.I),
    "run_python": re.compile(r"\brun_python\b", re.I),
    "write_file": re.compile(r"\bwrite_file\b", re.I),
}
# promise phrase -> (regex, commitment-id prefixes that honour it, tool grants that honour it)
_SLOT_WORDS = {
    "repair slot": (re.compile(r"\brepair (?:slot|report)\b", re.I), ("repair_",), frozenset()),
    "follow-up slot": (re.compile(r"\bfollow[- ]?up (?:slot|report)\b", re.I), ("followup_", "follow_up_"), frozenset()),
    # the budget exchange's query stage is an action grant, not a commitment (2026-09-25)
    "query slot": (re.compile(r"\bquery (?:slot|stage)\b|\bclarification (?:slot|stage)\b", re.I), ("query_",),
                   frozenset({"send_query", "send_reply"})),
}
_UNREADABLE_PATHS = ("/work/submitted",)
# A sentence that DENIES an affordance ("there is no later repair report, follow-up or
# query") is not a promise. A negation within the same clause before the match cancels it.
_NEGATION_RE = re.compile(r"\b(?:no|not|never|without|nor|none|neither|nothing|no longer)\b[^.;:]{0,80}$", re.I)


def _negated(text: str, start: int) -> bool:
    return bool(_NEGATION_RE.search(text[max(0, start - 100):start]))


@dataclass(frozen=True)
class AffordanceFinding:
    role_id: str
    kind: str        # path | tool | slot
    promise: str     # the text that makes the promise
    reason: str      # why the role cannot act on it
    source: str      # system_prompt | initial_user_text | notice


def _granted(role, org_spec) -> set[str]:
    if role.tools is not None:
        return set(role.tools)
    if org_spec.tools is not None:
        return set(org_spec.tools)
    return set()  # None at both levels means the runner's default grant; treat as none promised


def audit_texts(role_id: str, texts: dict[str, str], *, granted: set[str],
                commitment_ids: list[str]) -> list[AffordanceFinding]:
    """Lint the given texts for one role. ``texts`` maps a source label to the text."""
    out: list[AffordanceFinding] = []
    can_read = bool(granted & {"read_file", "run_python"})
    for source, text in texts.items():
        if not text:
            continue
        for m in _PATH_RE.finditer(text):
            if _negated(text, m.start()):
                continue
            path = m.group(1).rstrip(".,;:")
            if any(path.startswith(u) for u in _UNREADABLE_PATHS):
                out.append(AffordanceFinding(role_id, "path", path,
                                             "no tool reads this location for any role", source))
            elif not can_read:
                out.append(AffordanceFinding(role_id, "path", path,
                                             "role holds no read_file or run_python grant", source))
        for tool, rx in _TOOL_WORDS.items():
            if tool in granted:
                continue
            if any(not _negated(text, m.start()) for m in rx.finditer(text)):
                out.append(AffordanceFinding(role_id, "tool", tool, "tool not granted to this role", source))
        for label, (rx, prefixes, tools_ok) in _SLOT_WORDS.items():
            if any(c.startswith(prefixes) for c in commitment_ids) or (granted & tools_ok):
                continue
            if any(not _negated(text, m.start()) for m in rx.finditer(text)):
                out.append(AffordanceFinding(role_id, "slot", label,
                                             "the contract profile issues no such commitment", source))
    # de-duplicate identical findings from repeated mentions
    seen: set[tuple] = set()
    uniq: list[AffordanceFinding] = []
    for f in out:
        key = (f.role_id, f.kind, f.promise, f.source)
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    return uniq


def audit_affordances(org_spec, pack, tier: str, *, notice_texts: dict[str, str] | None = None
                      ) -> list[AffordanceFinding]:
    """Audit every role of ``org_spec`` against ``pack`` at ``tier``.

    ``notice_texts`` maps a label to a standing notice template every role receives
    (the runner passes the clock notice rendered with placeholder values)."""
    commitment_ids = [c.commitment_id for c in pack.outcome_contract.commitments]
    findings: list[AffordanceFinding] = []
    for role in org_spec.roles:
        packet_role = role.role_packet or role.role_id
        system_prompt, user_text = pack.build_initial_prompt(
            tier, role=packet_role, attention=role.attention, tools=role.tools)
        texts = {"system_prompt": system_prompt, "initial_user_text": user_text}
        for label, text in (notice_texts or {}).items():
            texts[f"notice:{label}"] = text
        findings.extend(audit_texts(role.role_id, texts, granted=_granted(role, org_spec),
                                    commitment_ids=commitment_ids))
    return findings


def findings_as_json(findings: list[AffordanceFinding]) -> list[dict]:
    return [asdict(f) for f in findings]
