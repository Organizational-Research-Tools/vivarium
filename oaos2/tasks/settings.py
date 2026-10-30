"""Check a preset's task settings (``live_coordination``) against what its task plugin reads.

A task plugin's protocol module may define ``validate_settings(spec)``. ``OrganizationSpec.validate``
calls it, so a preset with a misspelled or unsupported setting fails when it is loaded, and again
when a run starts, naming the setting, instead of running with the default. The platform audit of
October 18, 2026 found ``bench_variation_typo`` accepted and bench variation left at 0. The plugin
keeps its list of accepted names next to the code that reads them; this module holds only the
checks every plugin shares.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

# Settings any live-coordination preset may give: read by the runner and the agent loop, not by a
# task plugin (the mode, the protocol, the contract profile, PC1's runner options).
COMMON = frozenset({"mode", "protocol_module", "contract_profile", "cost_notice", "python_timeout_s",
                    "context_budget_basis"})


def check_names(pack: str, lc: Mapping, accepted: Iterable[str],
                nested: Mapping[str, Iterable[str]] | None = None, where: str = "") -> None:
    """Refuse a top-level or nested setting the plugin does not read.

    ``nested`` maps a setting whose value is a mapping to the names that mapping may hold.
    ``where`` names the file that lists the accepted settings, for the error message."""
    allowed = set(accepted) | COMMON
    unknown = sorted(str(k) for k in lc if k not in allowed)
    if unknown:
        raise ValueError(f"{pack}: unknown setting(s) {unknown} in live_coordination"
                         + (f" (accepted settings: {where})" if where else ""))
    for key, names in (nested or {}).items():
        value = lc.get(key)
        if isinstance(value, Mapping):
            bad = sorted(str(k) for k in value if k not in set(names))
            if bad:
                raise ValueError(f"{pack}: unknown {key} setting(s) {bad}; {key} accepts {sorted(set(names))}")


def check_combinations(pack: str, lc: Mapping,
                       rules: Iterable[tuple[Callable[[Mapping], bool], str]]) -> None:
    """Refuse settings that would be silently ignored: each rule is (applies, message)."""
    for applies, message in rules:
        if applies(lc):
            raise ValueError(f"{pack}: {message}")
