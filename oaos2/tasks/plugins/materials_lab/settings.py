"""The settings a materials-lab preset may give, checked when the preset loads (``validate_settings``).

``SETTINGS`` lists every ``live_coordination`` name the plugin reads (``LabPool.from_context`` and
its helpers); a test keeps it in step with the code. The testing-firm pack (``pc1_testing``) uses
the same protocol and the same list. Most incompatible combinations are refused by
``LabPool.from_context`` as the pool is built, before any model call. The rules here add the
combinations it would silently ignore; no current or retained preset uses any of them
(consolidation, October 19, 2026). A setting switched off by a zero (an audit probability of 0, a
variant's gain of 0) is not refused, since tests and launchers switch features off that way.
"""

from __future__ import annotations

from dataclasses import fields

from oaos2.tasks.settings import check_combinations, check_names

SETTINGS = frozenset({
    "allocation", "audit", "bench_variation", "board", "bounds", "capacity", "carry_reason", "challenge_cost",
    "challenges", "client_text", "concern_board", "concern_effect_stated", "concern_recorded", "contest",
    "credit_text", "credit_threshold", "deadline_review", "deliberation_text", "density", "difficulty_ladder",
    "families", "family_types", "filing_status", "guidance_text", "instance_seed", "institution",
    "instrument_version", "instruments", "known_feasible", "lab_logistics", "notices", "objective_text",
    "own_panels", "peer_review", "presentation", "processing_text", "program_lines", "program_target", "projects",
    "reading_summary", "refinement", "reminder_minutes", "request_cap", "restricted", "retire_text", "rival",
    "rule_level", "rule_reasons", "rule_text", "rule_texts", "scoring_text", "seed_mode", "seed_share",
    "seed_text", "seeded_closed_projects", "seeded_projects", "spec_revisions", "stake_text",
    "state_feasible_count", "strict_report", "success_cap", "success_floor", "unreviewed", "urgency_text",
    "vocabulary", "warm_start",
})

# The type each setting must have (usability audit, October 29, 2026): a quoted "false" for a yes-or-no setting, or a
# text where a number belongs, is refused when the preset loads instead of failing, or silently reading as true, in
# the run. None (the YAML null) leaves a setting unset. docs/world/SETTINGS.md gives each setting's values.
TYPES = {
    bool: frozenset({"carry_reason", "challenges", "concern_effect_stated", "contest", "deadline_review", "filing_status",
                     "lab_logistics", "own_panels", "peer_review", "program_lines", "reading_summary", "rival",
                     "state_feasible_count", "strict_report", "unreviewed"}),
    int: frozenset({"capacity", "challenge_cost", "credit_threshold", "instance_seed", "program_target", "request_cap",
                    "success_cap", "success_floor"}),
    float: frozenset({"bench_variation", "density", "refinement"}),
    str: frozenset({"allocation", "client_text", "concern_board", "concern_recorded", "credit_text", "deliberation_text",
                    "guidance_text", "institution", "instrument_version", "objective_text", "presentation",
                    "processing_text", "retire_text", "rule_level", "rule_text", "scoring_text", "seed_mode",
                    "seed_share", "seed_text", "stake_text", "urgency_text", "vocabulary"}),
    list: frozenset({"difficulty_ladder", "families", "known_feasible", "notices", "projects", "reminder_minutes",
                     "seeded_closed_projects", "seeded_projects", "spec_revisions"}),
    dict: frozenset({"audit", "board", "bounds", "family_types", "instruments", "restricted", "rule_reasons",
                     "rule_texts", "warm_start"}),
}
_NAMES = {bool: "yes or no (true/false)", int: "a whole number", float: "a number", str: "a text",
          list: "a list", dict: "a mapping"}


def check_types(lc) -> None:
    """Refuse a setting whose value has the wrong type, naming the setting and the type it needs."""
    wrong = []
    for kind, names in TYPES.items():
        for name in sorted(names & set(lc)):
            value = lc[name]
            if value is None:
                continue
            if kind is float:
                ok = isinstance(value, (int, float)) and not isinstance(value, bool)
            elif kind is int:
                ok = isinstance(value, int) and not isinstance(value, bool)
            else:
                ok = isinstance(value, kind)
            if not ok:
                wrong.append(f"{name} must be {_NAMES[kind]}, not {value!r}")
    if wrong:
        raise ValueError("materials_lab: " + "; ".join(wrong))


# The names a mapping-valued setting may hold. The board's values are checked by ``Board.configure`` as the
# pool is built; rule texts and reasons are keyed by rule level, which ``rule_level`` checks.
RESTRICTED = frozenset({"gain", "note", "legacy", "legacy_text", "legacy_listing", "archive", "before", "rule_ref"})


# Settings of the credit institution, which have no effect without ``institution``.
INSTITUTION_ONLY = frozenset({"credit_threshold", "success_floor", "success_cap", "program_target", "program_lines",
                              "contest", "challenges", "state_feasible_count"})


def _seeding(lc) -> bool:
    return bool(lc.get("seeded_projects") or lc.get("seed_mode") or (lc.get("restricted") or {}).get("legacy"))


# (applies, message): settings that would otherwise be read and then have no effect
COMBINATIONS = (
    (lambda lc: bool(lc.get("seed_text")) and not _seeding(lc),
     "seed_text needs seeded projects, a seed_mode or earlier records"),
    (lambda lc: "seed_share" in lc and not _seeding(lc),
     "seed_share needs seeded projects, a seed_mode or earlier records"),
    (lambda lc: "warm_start" in lc and lc.get("seed_mode") != "warm",
     "warm_start settings need seed_mode: warm"),
    (lambda lc: "challenge_cost" in lc and not lc.get("challenges"),
     "challenge_cost needs challenges: true"),
    (lambda lc: "allocation" in lc and not lc.get("institution"),
     "allocation belongs to an institution"),
    # read only inside LabPool.from_context's institution block (release review, October 29, 2026)
    (lambda lc: bool(set(lc) & INSTITUTION_ONLY) and not lc.get("institution"),
     "credit_threshold, success_floor, success_cap, program_target, program_lines, contest, challenges and "
     "state_feasible_count belong to an institution"),
    (lambda lc: bool(lc.get("institution")) and lc.get("allocation", "exclusive") != "divisible"
     and bool({"success_floor", "success_cap"} & set(lc)),
     "success_floor and success_cap need allocation: divisible"),
)


def validate_settings(spec) -> None:
    """Refuse an unknown setting or an ignored combination before the run (OrganizationSpec.validate)."""
    from oaos2.tasks.plugins.materials_lab.landscape import FAMILY_TYPES, PROPERTIES
    from oaos2.tasks.plugins.materials_lab.pool import LabBounds
    lc = spec.live_coordination or {}
    check_names("materials_lab", lc, SETTINGS, where="oaos2/tasks/plugins/materials_lab/settings.py", nested={
        "bounds": [f.name for f in fields(LabBounds)],
        "audit": ("probability", "delay_s"),
        "board": ("form", "post_cap", "index_page", "thread_page"),
        "restricted": RESTRICTED,
        "warm_start": ("steps", "panels", "max_attempts"),
        "instruments": PROPERTIES,
        "family_types": FAMILY_TYPES,
    })
    archive = (lc.get("restricted") or {}).get("archive")
    if isinstance(archive, dict) and set(archive) - {"per_lab"}:
        raise ValueError(f"materials_lab: unknown restricted.archive setting(s) {sorted(set(archive) - {'per_lab'})}; "
                         "restricted.archive accepts ['per_lab']")
    check_types(lc)
    check_combinations("materials_lab", lc, COMBINATIONS)
