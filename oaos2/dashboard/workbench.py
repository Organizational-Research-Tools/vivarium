"""Experiments workbench data layer (DASHBOARD.md §4.8) — modify & initiate.

Two of the dashboard's three sanctioned write paths live here:

- **Library edits**: YAML under ``library/`` only, and a save lands ONLY if the
  platform's own loader accepts the result — the file is written, the loader is
  run on it, and on any error the previous content is restored byte-for-byte.
  The dashboard never grows a second validator.
- **Run launches**: a subprocess of the existing CLI scripts (``run_offline_sweep``
  free; ``run_calibration --go`` for live spend, behind the app's typed-confirmation
  gate). The dashboard never reimplements the runner and inherits every gate the
  runner enforces (confirmatory prereg, caps, isolation).

The browser also reports which YAML keys the loaders currently IGNORE (DEFERRED §7)
— so a config reads as what the engine will actually see, not what the file says.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

from oaos2.experiments.loader import load_design
from oaos2.library import library_dir
from oaos2.organizations.loader import load_org_spec, read_preset
from oaos2.pricing.ledger import validate_spending_cap
from oaos2.tasks.loader import load_task_pack

_REPO_ROOT = Path(__file__).resolve().parents[2]

# What the loaders actually read today (keep in sync with the loader modules;
# anything else in the YAML is real text the ENGINE never sees).
_ORG_PARSED_KEYS = {"preset_id", "roles", "scheduler", "scheduler_module",
                    "committer_binding", "context_expansion", "live_coordination",
                    "topology", "tools", "precedence_rules"}
_ORG_ROLE_PARSED_KEYS = {"role_id", "attention", "plays", "specialized", "role_packet",
                         "tools", "context_budget_tokens", "max_calls_per_slot",
                         "decision_rights", "comm_kinds", "model_ref", "out_of_scope_areas",
                         "packet_scopes"}
_DESIGN_PARSED_KEYS = {"name", "task_pack", "factors", "replications", "mode",
                       "parity_policy", "platform_seed", "preregistration_ref",
                       "confirmatory_evidence"}


# --- browse ------------------------------------------------------------------ #

_LIBRARY_MEMO: tuple | None = None


def _library_key(lib: Path) -> tuple:
    """Every file under the library with its size and modification time: loading a
    design or preset reads task manifests and prompts too, so any change anywhere in
    the library invalidates the memo (stat-ing ~700 files takes about 10 ms)."""
    import os
    parts = []
    for root, _dirs, files in os.walk(lib):
        for f in files:
            try:
                st = os.stat(os.path.join(root, f))
            except OSError:
                continue
            parts.append((os.path.join(root, f), st.st_size, st.st_mtime_ns))
    return tuple(sorted(parts))


def list_library() -> dict:
    """Every library entry with its RESOLVED engine view (or the load error), memoized
    until any library file changes. Callers must not mutate the result."""
    global _LIBRARY_MEMO
    key = _library_key(library_dir())
    if _LIBRARY_MEMO is not None and _LIBRARY_MEMO[0] == key:
        return _LIBRARY_MEMO[1]
    out = _list_library()
    _LIBRARY_MEMO = (key, out)
    return out


def _list_library() -> dict:
    lib = library_dir()
    out = {"experiments": [], "organizations": [], "tasks": []}

    for p in sorted((lib / "experiments").glob("*.yaml")):
        entry = {"name": p.stem, "path": f"experiments/{p.name}"}
        try:
            d = load_design(p.stem)
            entry["resolved"] = {"task_pack": d.task_pack, "mode": d.mode,
                                 "factors": d.factors, "replications": d.replications,
                                 "preregistration_ref": d.preregistration_ref,
                                 "parity_policy": {
                                     "basis": d.parity_policy.basis,
                                     "regime": d.parity_policy.regime,
                                     "cap_usd": d.parity_policy.cap_usd,
                                     "cap_tokens": d.parity_policy.cap_tokens,
                                     "reserve_tokens": d.parity_policy.reserve_tokens,
                                 }}
            entry["ignored_keys"] = _ignored_keys(p, _DESIGN_PARSED_KEYS)
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
        out["experiments"].append(entry)

    for p in sorted((lib / "organizations").glob("*.yaml")):
        entry = {"name": p.stem, "path": f"organizations/{p.name}"}
        try:
            declared, bases = read_preset(p.stem)
            entry["bases"] = [b.stem for b in bases]          # outermost first; [] for a preset without a base
            entry["base_only"] = bool(declared.get("base_only"))
            spec = load_org_spec(p.stem, allow_base_only=True)
            entry["resolved"] = {
                "n_agents": spec.n_agents, "scheduler": spec.scheduler,
                "committer_binding": spec.committer_binding,
                "live_coordination": spec.live_coordination,
                "tools": sorted(spec.tools) if spec.tools is not None else None,
                "precedence_rules": spec.precedence_rules,
                "topology": [
                    {"from_role": c.from_role, "to_role": c.to_role,
                     "kinds": sorted(c.kinds)}
                    for c in (spec.topology.channels if spec.topology else ())
                ],
                "roles": [{"role_id": r.role_id, "plays": r.plays, "attention": r.attention,
                           "tools": r.tools, "context_budget_tokens": r.context_budget_tokens,
                           "max_calls_per_slot": r.max_calls_per_slot,
                           "comm_kinds": sorted(r.comm_kinds) if r.comm_kinds is not None else None,
                           "model_ref": r.model_ref,
                           "out_of_scope_areas": list(r.out_of_scope_areas),
                           "packet_scopes": list(r.packet_scopes),
                           "decision_rights": _rights_view(r.decision_rights)}
                          for r in spec.roles],
            }
            entry["ignored_keys"] = _org_ignored_keys(p)
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
        out["organizations"].append(entry)

    for mp in sorted((lib / "tasks").glob("*/manifest.yaml")):
        pack_id = mp.parent.name
        entry = {"name": pack_id, "path": f"tasks/{pack_id}/manifest.yaml"}
        try:
            m = yaml.safe_load(mp.read_text()) or {}
            profiles = sorted((m.get("contracts") or {}).keys())
            # New packs need not define the legacy ``decomposed`` profile.  Load
            # a profile they actually declare; this page is an inspector, not an
            # experiment-arm selector.
            inspect_profile = "decomposed" if "decomposed" in profiles else (
                "single_results" if "single_results" in profiles else profiles[0])
            pack = load_task_pack(pack_id, profile=inspect_profile)
            env = m.get("environment") or {}
            entry["resolved"] = {
                "task_id": m.get("task_id") or pack.pack_id,
                "evaluators": sorted(pack.evaluators),
                "tiers": sorted((m.get("visible_materials") or {}).keys()),
                "profiles": profiles,
                "inspected_profile": inspect_profile,
                "clock": pack.clock.to_manifest() if pack.clock else None,
                "environment_driver": env.get("driver"),
                "schedule_tiers": sorted((env.get("schedules") or {}).keys()),
                "schedule_variants": sorted((env.get("schedule_variants") or {}).keys()),
                "staged_coordination": pack.staged_coordination,
                "offline_solver": pack.offline_solver,
            }
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
        out["tasks"].append(entry)
    return out


def _rights_view(rights) -> dict | None:
    if rights is None:
        return None
    return {
        "may_submit_milestones": rights.may_submit_milestones,
        "may_accept_handoffs_from": list(rights.may_accept_handoffs_from),
        "review_authority_over": list(rights.review_authority_over),
        "extensions": rights.extensions,
    }


def _ignored_keys(path: Path, parsed: set[str]) -> list[str]:
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return []
    return sorted(set(data) - parsed) if isinstance(data, dict) else []


def _org_ignored_keys(path: Path) -> list[str]:
    ignored = _ignored_keys(path, _ORG_PARSED_KEYS)
    try:
        data = yaml.safe_load(path.read_text()) or {}
        for r in data.get("roles") or []:
            if isinstance(r, dict):
                for k in set(r) - _ORG_ROLE_PARSED_KEYS:
                    tag = f"roles[].{k}"
                    if tag not in ignored:
                        ignored.append(tag)
    except Exception:
        pass
    return sorted(ignored)


# --- edit (validated save) ---------------------------------------------------- #

def resolve_library_file(rel: str) -> Path | None:
    """Editable-file containment: YAML under library/ only — experiment/org yamls
    or a task manifest. Anything else (assets, hidden refs, escapes) → None."""
    lib = library_dir().resolve()
    candidate = (lib / rel).resolve()
    if lib not in candidate.parents or not candidate.is_file():
        return None
    r = candidate.relative_to(lib)
    ok = ((r.parts[0] in ("experiments", "organizations") and len(r.parts) == 2
           and r.suffix == ".yaml")
          or (r.parts[0] == "tasks" and len(r.parts) == 3 and r.name == "manifest.yaml"))
    return candidate if ok else None


def save_validated(rel: str, content: str) -> tuple[bool, str]:
    """Write the file, run the real loader on it, revert byte-for-byte on failure.
    Returns (saved, message)."""
    path = resolve_library_file(rel)
    if path is None:
        return False, f"not an editable library file: {rel}"
    previous = path.read_text()
    path.write_text(content)
    try:
        parts = path.relative_to(library_dir().resolve()).parts
        if parts[0] == "experiments":
            load_design(path.stem)
        elif parts[0] == "organizations":
            load_org_spec(path.stem)
        else:
            # Validate every declared profile; current tasks need not provide
            # the legacy "decomposed" default used by direct loader callers.
            manifest = yaml.safe_load(content) or {}
            profiles = manifest.get("contracts") or {}
            if not profiles:
                raise ValueError("task manifest must declare at least one contract profile")
            for profile in profiles:
                load_task_pack(parts[1], profile=profile)
        return True, "saved — loader accepted the new config"
    except Exception as exc:
        path.write_text(previous)
        return False, f"REVERTED — loader rejected it: {type(exc).__name__}: {exc}"


# --- launch (subprocess of the existing scripts) ------------------------------ #

def _launch_dir(runs_root: Path) -> Path:
    d = Path(runs_root) / ".dashboard" / "launches"
    d.mkdir(parents=True, exist_ok=True)
    return d


def launch(runs_root: Path, *, design: str, execution: str, reps: int | None = None,
           cap_usd: float | None = None) -> dict:
    """Spawn the launcher subprocess (detached; survives the dashboard).

    The typed-confirmation gate for ``live`` is the APP's job — by the time this
    runs, spend was explicitly confirmed. Offline needs no gate (stub, no Docker)."""
    if execution == "offline":
        argv = [sys.executable, "scripts/run_offline_sweep.py", "--design", design,
                "--runs-root", str(Path(runs_root).resolve())]
        if reps:
            argv += ["--reps", str(reps)]
    elif execution == "live":
        cap_usd = validate_spending_cap(cap_usd)
        # Live runs land under the repo's runs/ (run_calibration owns that path);
        # confirmatory-mode prereg enforcement is inside load_design — inherited.
        argv = [sys.executable, "scripts/run_calibration.py", "--design", design, "--go"]
        if cap_usd:
            argv += ["--cap-usd", str(cap_usd)]
        if reps:
            argv += ["--reps", str(reps)]
    else:
        raise ValueError(f"unknown execution {execution!r}")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = _launch_dir(runs_root) / f"{stamp}_{design}_{execution}.log"
    env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT))
    with log_path.open("wb") as log:
        proc = subprocess.Popen(argv, cwd=_REPO_ROOT, env=env,
                                stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
    record = {"pid": proc.pid, "argv": argv, "design": design, "execution": execution,
              "started": stamp, "log": str(log_path)}
    log_path.with_suffix(".json").write_text(json.dumps(record, indent=2, sort_keys=True))
    return record


def list_launches(runs_root: Path) -> list[dict]:
    """Every recorded launch, newest first, with liveness + log tail."""
    d = Path(runs_root) / ".dashboard" / "launches"
    out = []
    for sidecar in sorted(d.glob("*.json"), reverse=True) if d.is_dir() else []:
        try:
            rec = json.loads(sidecar.read_text())
        except (OSError, ValueError):
            continue
        rec["alive"] = _alive(rec.get("pid"))
        log = Path(rec.get("log", ""))
        rec["log_tail"] = "\n".join(log.read_text(errors="replace").splitlines()[-40:]) \
            if log.is_file() else ""
        out.append(rec)
    return out


def _alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


# --- organization families: near-duplicate presets read as a base and its variants --- #

_ORG_FIELDS = ("n_agents", "scheduler", "committer_binding", "live_coordination", "tools",
               "precedence_rules", "topology")
_ROLE_FIELDS = ("plays", "attention", "tools", "context_budget_tokens", "max_calls_per_slot",
                "comm_kinds", "model_ref", "out_of_scope_areas", "packet_scopes", "decision_rights")


def _short(v) -> str:
    text = str(v) if not isinstance(v, (list, tuple)) else ", ".join(str(x) for x in v)
    return text if len(text) <= 60 else text[:57] + "…"


def _field_diffs(label: str, base, other) -> list[str]:
    """Human-readable differences for one field: key by key for mappings, added and
    removed members for lists, else the two values."""
    if isinstance(base, dict) and isinstance(other, dict):
        out = []
        for k in sorted(set(base) | set(other)):
            if base.get(k) != other.get(k):
                out.extend(_field_diffs(f"{label}.{k}", base.get(k), other.get(k)))
        return out
    if isinstance(base, (list, tuple)) and isinstance(other, (list, tuple)) \
            and all(not isinstance(x, dict) for x in list(base) + list(other)):
        added = [str(x) for x in other if x not in base]
        removed = [str(x) for x in base if x not in other]
        parts = ([f"+{', '.join(added)}"] if added else []) + ([f"−{', '.join(removed)}"] if removed else [])
        return [f"{label}: {' '.join(parts)}"] if parts else []
    return [f"{label}: {_short(base)} → {_short(other)}"]


def _common_prefix(names: list[str]) -> str:
    if not names:
        return ""
    prefix = names[0]
    for n in names[1:]:
        while not n.startswith(prefix):
            prefix = prefix[:-1]
    return prefix.rstrip("_")


def organization_families(entries: list[dict]) -> list[dict]:
    """Group loaded presets into families and list what every member changes against the family's base, field by
    field. A preset that names a base (``base:``) belongs to its outermost base's family, whose base it is; the other
    presets are grouped by the set of roles they declare (the organization's shape), the shortest name taken as the
    base. Sameness of shape is a reading aid, not a claim that the variants are comparable conditions; presets that
    fail to load are listed apart."""
    groups: dict[tuple, list[dict]] = {}
    broken = []
    based_on = {e["bases"][0] for e in entries if e.get("bases")}
    for e in entries:
        if "error" in e or not e.get("resolved"):
            broken.append(e)
            continue
        if e.get("bases") or e["name"] in based_on:
            key = ("base", (e.get("bases") or [e["name"]])[0])
        else:
            key = tuple(sorted(r["role_id"] for r in e["resolved"]["roles"]))
        groups.setdefault(key, []).append(e)
    families = []
    for key, members in groups.items():
        shape = tuple(sorted(r["role_id"] for r in members[0]["resolved"]["roles"]))
        if key[0] == "base":   # the declared base first, then the presets that build on it
            members = sorted(members, key=lambda e: (e["name"] != key[1], len(e.get("bases") or []), e["name"]))
        else:
            members = sorted(members, key=lambda e: (len(e["name"]), e["name"]))
        base = members[0]
        base_roles = {r["role_id"]: r for r in base["resolved"]["roles"]}
        rows = []
        for e in members:
            diffs = []
            if e is not base:
                for f in _ORG_FIELDS:
                    if e["resolved"].get(f) != base["resolved"].get(f):
                        diffs.extend(_field_diffs(f, base["resolved"].get(f), e["resolved"].get(f)))
                for r in e["resolved"]["roles"]:
                    b = base_roles.get(r["role_id"]) or {}
                    for f in _ROLE_FIELDS:
                        if r.get(f) != b.get(f):
                            diffs.extend(_field_diffs(f"{r['role_id']}.{f}", b.get(f), r.get(f)))
            rows.append({**e, "is_base": e is base, "diffs": diffs})
        names = [e["name"] for e in members]
        families.append({"label": base["name"] if key[0] == "base" else (_common_prefix(names) or base["name"]),
                         "roles": list(shape),
                         "n_agents": base["resolved"].get("n_agents"), "base": base["name"],
                         "members": rows})
    families.sort(key=lambda f: (-len(f["members"]), f["label"]))
    if broken:
        families.append({"label": "presets that fail to load", "roles": [], "n_agents": None,
                         "base": None, "members": [{**e, "is_base": False, "diffs": []} for e in broken]})
    return families
