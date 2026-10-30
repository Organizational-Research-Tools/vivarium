"""A NOVEL scheduler policy built entirely OUTSIDE core — the open-registry canary.

The org YAML names this module via ``scheduler_module``; importing it registers
the policy with the open scheduler registry (``organizations/scheduler.py``), so
a new admission rule is YAML + this plugin — zero core diff (the coordination
``protocol_module`` pattern, applied to schedulers)."""

from __future__ import annotations

from oaos2.organizations.scheduler import register_scheduler_policy


def canary_last_idle_policy(snap) -> set:
    """Admit exactly the LAST idle agent in stable order — deliberately not any
    built-in's behavior, so resolution provably reached this plugin."""
    order = [a for a in snap.all_agent_order if a in snap.idle_agents]
    return {order[-1]} if order else set()


register_scheduler_policy("canary_last_idle", canary_last_idle_policy)
