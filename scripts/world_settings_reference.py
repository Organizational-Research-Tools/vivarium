"""Render docs/world/SETTINGS.md from docs/world/settings_reference.yaml, the reference of every setting a
materials-workshop preset may give.

    uv run python scripts/world_settings_reference.py           # write the page
    uv run python scripts/world_settings_reference.py --check   # exit 1 if the page is not current

tests/world/test_settings_reference.py checks that the reference names exactly the settings the workshop
reads (oaos2/tasks/plugins/materials_lab/settings.py) and that the page is current.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "docs" / "world" / "settings_reference.yaml"
PAGE = REPO / "docs" / "world" / "SETTINGS.md"

# The seven parameters of the proposal (section 5), in its order and wording, then the one group outside them.
DIMENSIONS = [
    ("interdependence", "The interdependence of components and instruments"),
    ("structure", "The structure of communication and authority"),
    ("formal_rule", "The formal rules and whether their stated rationale holds"),
    ("interests", "The interests assigned through credit and scarce resources"),
    ("surveillance_sanction", "Surveillance and sanction"),
    ("equivocality", "The equivocality of client signals"),
    ("history", "The history inherited from earlier members"),
    ("mechanics", "The workshop's mechanics: instances, scoring, bounds, logistics and presentation"),
]

# What each parameter has of released levels, stated at the head of its section.
LEVELS = {
    "interdependence": "No released standard levels. `density` and `difficulty_ladder` are free numbers and `instruments` "
                       "a free assignment. They set how hard the relations among components are to satisfy and who holds "
                       "which test; which components are related is not a setting. The generator has other interaction "
                       "layouts (`structure` in `landscape.generate`), and no preset reaches them yet.",
    "structure": "No released standard levels. The base world has six laboratories with the same actions, every channel "
                 "open and a flat board. The workshop has no lead or hierarchy setting: a study writes such a structure "
                 "with the preset's fields below, which sit outside `live_coordination`.",
    "formal_rule": "`rule_level` has three released levels: `approved_list`, `licence` and `injury`, with their texts in "
                   "`materials_workshop.yaml`. They change the reason stated. No released setting makes a stated reason "
                   "true or false in the world.",
    "interests": "`institution` (`competitive`, `cooperative`) and `allocation` (`exclusive`, `divisible`) have released "
                 "levels. The other settings are free numbers and texts.",
    "surveillance_sanction": "No released standard levels. These are switches from earlier development; the base world is "
                             "the `unreviewed` form, the only one the competition study ran.",
    "equivocality": "No released standard levels. The base world states nothing about which projects can be qualified, "
                    "and its client revisions are unambiguous.",
    "history": "No released standard levels. `seed_mode` names three forms; the base world uses a fourth, the earlier "
               "records of `restricted.legacy` and `restricted.archive` (under [settings inside mapping-valued "
               "settings](#settings-inside-mapping-valued-settings)).",
}

INTRO = """# Settings of the materials workshop

Every setting a materials-workshop preset may give under `live_coordination`, and the fields outside it that
set roles and channels, generated from [settings_reference.yaml](settings_reference.yaml) by
`scripts/world_settings_reference.py`. A preset that gives a `live_coordination` setting not listed here is refused
when it loads, naming the setting, and so are the combinations the workshop would read and then ignore
(`oaos2/tasks/plugins/materials_lab/settings.py`). [WORLD.md](../WORLD.md) explains how a study sits on the workshop.

The settings are grouped by the seven parameters of the research proposal along which the workshop's design space
is to be limited, followed by the workshop's fixed mechanics. The grouping records what each setting does now. Each
parameter's section says which released levels it has; no level has yet been measured for each model. For each
setting:

- **Does** says what it changes in the world, as the code reads it.
- **Values** gives the accepted values and the default when a preset leaves the setting out.
- **Competition study** gives its value in the two presets that study's main study ran (competitive
  and cooperative arm), or "not set".
- **Introduced** names the dated note in `library/tasks/materials_lab/INSTRUMENT_DESIGN.md` that
  introduced it, where there is one.
"""


def _text(value) -> str:
    return " ".join(str(value).split())


def _entry(name: str, item: dict, with_dimension_note: bool = True) -> list[str]:
    out = [f"### `{name}`", "", f"- **Does:** {_text(item['does'])}", f"- **Values:** {_text(item['values'])}"]
    if "competition" in item:
        out.append(f"- **Competition study:** {_text(item['competition'])}")
    if with_dimension_note and item.get("dimension_note"):
        out.append(f"- **Why this group:** {_text(item['dimension_note'])}")
    if item.get("introduced"):
        out.append(f"- **Introduced:** {_text(item['introduced'])}")
    return out + [""]


def _organization(ref: dict) -> list[str]:
    out = []
    for name, item in ref["organization"].items():
        out += _entry(name, item, with_dimension_note=False)
    return out


def render(ref: dict) -> str:
    lines = [INTRO]
    by_dim: dict[str, list[str]] = {}
    for name, item in ref["plugin"].items():
        by_dim.setdefault(item["dimension"], []).append(name)
    unknown = set(by_dim) - {d for d, _ in DIMENSIONS}
    if unknown:
        raise SystemExit(f"unknown dimension(s) in {SOURCE.name}: {sorted(unknown)}")
    lines.append("## Contents\n")
    for dim, title in DIMENSIONS:
        names = sorted(by_dim[dim]) + (list(ref["organization"]) if dim == "structure" else [])
        lines.append(f"- {title}: " + ", ".join(f"`{n}`" for n in names))
    lines.append("- Settings inside mapping-valued settings: " + ", ".join(f"`{n}`" for n in ref["nested"]))
    lines.append("- Settings the platform reads for every task: " + ", ".join(f"`{n}`" for n in ref["engine"]))
    lines.append("")
    for dim, title in DIMENSIONS:
        lines += [f"## {title}", ""]
        if dim in LEVELS:
            lines += [LEVELS[dim], ""]
        for name in sorted(by_dim[dim]):
            lines += _entry(name, ref["plugin"][name])
        if dim == "structure":
            lines += _organization(ref)
    lines += ["## Settings inside mapping-valued settings", ""]
    for parent, names in ref["nested"].items():
        lines += [f"### `{parent}`", ""]
        lines += [f"- `{n}`: {_text(i['does'])} Values: {_text(i['values'])}" for n, i in names.items()]
        lines.append("")
    lines += ["## Settings the platform reads for every task", "",
              "These are read by the runner and the agent loop, not by the workshop.", ""]
    for name, item in ref["engine"].items():
        lines += _entry(name, item, with_dimension_note=False)
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    page = render(yaml.safe_load(SOURCE.read_text()))
    if args.check:
        current = PAGE.exists() and PAGE.read_text() == page
        print(f"{PAGE.relative_to(REPO)} is {'current' if current else 'not current'}")
        return 0 if current else 1
    PAGE.write_text(page)
    print(f"wrote {PAGE.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
