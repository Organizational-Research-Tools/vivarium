"""Load role and organization settings from library YAML files.

The loader builds OrganizationSpec with roles, tools, authority, communication
paths, scheduling, and coordination settings, then validates supported fields.
A preset may name another as its ``base`` and list only what it changes (``read_preset``).
The runtime and coordination procedures enforce behavior. Consult spec.py and
docs/mechanism/DEFERRED.md before relying on a declared setting for a treatment."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from oaos2.library import library_dir
from oaos2.decision_rights import DecisionRights
from oaos2.organizations.spec import OrganizationSpec, Role
from oaos2.organizations.topology import Channel, Topology


def org_path(name: str) -> Path:
    """The file of preset ``name``: in the library's ``organizations/``, else in the first folder of
    ``OAOS2_ORGANIZATIONS`` (paths separated by ``os.pathsep``) that holds it. The library's path is
    returned when no folder holds it, so a missing preset is reported where it belongs."""
    path = library_dir() / "organizations" / f"{name}.yaml"  # resolved at call time
    if not path.is_file():
        for folder in filter(None, os.environ.get("OAOS2_ORGANIZATIONS", "").split(os.pathsep)):
            if (Path(folder) / f"{name}.yaml").is_file():
                return Path(folder) / f"{name}.yaml"
    return path


_org_path = org_path


def _overlay(base: dict, changes: dict) -> dict:
    """``base`` with ``changes`` applied: mappings merge key by key, any other value (a list, a text, a
    number) replaces the base's whole. An overlay can set or replace a setting, never remove one."""
    out = dict(base)
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _overlay(out[key], value)
        else:
            out[key] = value
    return out


def read_preset(name: str, _below: tuple = ()) -> tuple[dict, list[Path]]:
    """The preset ``name`` as a mapping, with its bases applied, and the base files it rests on (outermost
    first). A preset that names ``base: <preset>`` lists only what it changes in that preset and must give
    its own ``preset_id``; a preset marked ``base_only: true`` is a base for others and is not run alone."""
    path = _org_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"no org spec {name!r} at {path}")
    m = yaml.safe_load(path.read_text()) or {}
    base = m.pop("base", None)
    if base is None:
        return m, []
    if base == name or base in _below:
        raise ValueError(f"org {name!r}: base {base!r} makes a cycle ({' <- '.join((*_below, name, base))})")
    if "preset_id" not in m:
        raise ValueError(f"org {name!r} names base {base!r} and must give its own preset_id")
    parent, bases = read_preset(base, (*_below, name))
    parent.pop("base_only", None)  # not inherited: an overlay is runnable unless it says otherwise
    return _overlay(parent, m), [*bases, _org_path(base)]


def load_org_spec(name: str, *, allow_base_only: bool = False) -> OrganizationSpec:
    """The preset ``name`` as a run loads it. A base for other presets is refused unless ``allow_base_only``
    (the dashboard's library page shows a base as it reads)."""
    path = _org_path(name)
    m, bases = read_preset(name)
    if m.get("base_only") and not allow_base_only:
        raise ValueError(f"org {name!r} is a base for other presets (base_only: true); "
                         f"run a preset that names it as its base")

    # Org-declared scheduler plugin (the coordination `protocol_module` pattern):
    # importing the module registers the policy with the open scheduler registry
    # (organizations/scheduler.py), so a novel admission rule is YAML + a plugin
    # module — never a core edit. Fail-closed on a broken module.
    scheduler_module = m.get("scheduler_module")
    if scheduler_module:
        import importlib
        try:
            importlib.import_module(str(scheduler_module))
        except Exception as exc:  # noqa: BLE001 — a missing policy module is fail-closed
            raise ValueError(
                f"org {name!r}: scheduler_module {scheduler_module!r} failed to "
                f"import: {exc}") from exc
    # PROVENANCE, not presence (probe round 2, 2026-08-17): a non-built-in
    # policy must have been registered BY the module this org itself declares
    # — a bogus scheduler_module (or another config's earlier import) is
    # refused. Provenance is the policy function's module, recorded at
    # registration, so repeated loads stay valid.
    from oaos2.organizations.scheduler import (
        FOUNDATION_SCHEDULER_POLICIES,
        SCHEDULER_PROVENANCE,
    )
    declared_scheduler = m.get("scheduler", "free")
    if (declared_scheduler not in FOUNDATION_SCHEDULER_POLICIES
            and SCHEDULER_PROVENANCE.get(declared_scheduler) != str(scheduler_module or "")):
        raise ValueError(
            f"org {name!r}: scheduler {declared_scheduler!r} is not a built-in "
            "policy and is not registered by this org's declared "
            f"`scheduler_module:` ({scheduler_module!r}; registered by: "
            f"{SCHEDULER_PROVENANCE.get(declared_scheduler, 'nothing')!r}) — "
            "another config's earlier import is not a declaration")

    def _rights(raw):
        if raw is None:
            return None
        known = {"may_submit_milestones", "may_accept_handoffs_from", "review_authority_over"}
        return DecisionRights(
            may_submit_milestones=bool(raw.get("may_submit_milestones", True)),
            may_accept_handoffs_from=tuple(raw.get("may_accept_handoffs_from", ["*"])),
            review_authority_over=tuple(raw.get("review_authority_over", [])),
            extensions={k: v for k, v in raw.items() if k not in known},
        )

    roles = [
        Role(role_id=r["role_id"], attention=r.get("attention", "all"),
             plays=list(r.get("plays", [])), specialized=bool(r.get("specialized", False)),
             role_packet=r.get("role_packet"), tools=r.get("tools"),
             context_budget_tokens=r.get("context_budget_tokens"),
             max_calls_per_slot=r.get("max_calls_per_slot"),
             calls_per_day=r.get("calls_per_day"),
             decision_rights=_rights(r.get("decision_rights")),
             comm_kinds=(frozenset(r["comm_kinds"]) if r.get("comm_kinds") is not None else None),
             model_ref=r.get("model_ref"),
             packet_scopes=tuple(r.get("packet_scopes", [])),
             out_of_scope_areas=tuple(r.get("out_of_scope_areas", [])))
        for r in m.get("roles", [])
    ]
    topology_raw = m.get("topology")
    topology = None
    if topology_raw is not None:
        channels = (topology_raw if isinstance(topology_raw, list)
                    else topology_raw.get("channels", []))
        topology = Topology(channels=tuple(
            Channel(from_role=c["from_role"], to_role=c["to_role"],
                    kinds=frozenset(c.get("kinds", ["*"]))) for c in channels
        ))
    spec = OrganizationSpec(
        preset_id=m["preset_id"],
        roles=roles,
        scheduler=m.get("scheduler", "free"),
        committer_binding=m.get("committer_binding", "by_role"),
        context_expansion=m.get("context_expansion"),
        live_coordination=m.get("live_coordination"),  # e.g. {mode: deliberative, max_rounds: 6}
        topology=topology,
        tools=(frozenset(m["tools"]) if m.get("tools") is not None else None),
        precedence_rules={k: tuple(v) for k, v in (m.get("precedence_rules") or {}).items()},
        source_ref=path,
        base_refs=tuple(bases),
    )
    spec.validate()
    return spec


def available_org_specs() -> list[str]:
    d = library_dir() / "organizations"
    return sorted(p.stem for p in d.glob("*.yaml")) if d.is_dir() else []
