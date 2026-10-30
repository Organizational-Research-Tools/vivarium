"""Registered task actions: agent-invoked tools a task pack declares (M8 §2).

A pack manifest lists ``actions:``; each entry names a handler in a registered
pack module. The tool dispatcher offers an action to a role only when the role's
tool grant names it, checks the grant exactly as for built-in tools, and records
the action's full arguments on the call event. Existing packs declare no actions
and keep their behavior.

Main caller: ``tasks/loader.py`` (construction) and ``agents/tools.py``
(dispatch). Limit: the handler runs host-side; anything that must execute inside
the agent's container goes through the existing container tools.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from oaos2.models.types import ToolSpec

# Closed effect classes (M8 §2): what an action may touch. ``submit`` means the
# action creates an attempt record; ``lifecycle`` means it changes the agent's
# turn state (wait, retire) and may end the turn.
EFFECT_CLASSES: frozenset[str] = frozenset(
    {"read", "write_private", "submit", "message", "report", "lifecycle"})


class ActionDeclarationError(ValueError):
    """A manifest action entry is malformed or its handler cannot be resolved."""


@dataclass
class TaskAction:
    name: str
    description: str
    effect_class: str
    handler: Callable[..., Awaitable]  # async (args, ctx, *, turn_id, caused_by) -> ToolResult
    module: str
    parameters_schema: dict = field(default_factory=dict)

    def toolspec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description,
                        parameters_schema=dict(self.parameters_schema))


def build_actions(pack_id: str, declared: list | None) -> dict[str, TaskAction]:
    """Resolve a manifest's ``actions`` list to TaskAction objects, fail-closed.

    Each entry: ``{name, description, effect_class, module, handler, parameters}``.
    A missing module or attribute, an unknown effect class, a duplicate name, or a
    name that shadows a built-in tool refuses the load.
    """
    from oaos2.agents.tools import BUILTIN_TOOL_NAMES

    actions: dict[str, TaskAction] = {}
    for entry in declared or []:
        entry = dict(entry or {})
        missing = {"name", "description", "effect_class", "module", "handler"} - set(entry)
        if missing:
            raise ActionDeclarationError(
                f"pack {pack_id!r} action {entry.get('name')!r} is missing {sorted(missing)}")
        name = str(entry["name"])
        if name in BUILTIN_TOOL_NAMES:
            raise ActionDeclarationError(
                f"pack {pack_id!r} action {name!r} shadows a built-in tool")
        if name in actions:
            raise ActionDeclarationError(f"pack {pack_id!r} declares action {name!r} twice")
        effect = str(entry["effect_class"])
        if effect not in EFFECT_CLASSES:
            raise ActionDeclarationError(
                f"pack {pack_id!r} action {name!r}: effect_class {effect!r} not in "
                f"{sorted(EFFECT_CLASSES)}")
        module_ref = str(entry["module"])
        try:
            module = importlib.import_module(module_ref)
            handler = getattr(module, str(entry["handler"]))
        except Exception as exc:  # noqa: BLE001 — a declared action is fail-closed
            raise ActionDeclarationError(
                f"pack {pack_id!r} action {name!r}: handler "
                f"{module_ref}.{entry['handler']} cannot be resolved: {exc}") from exc
        actions[name] = TaskAction(
            name=name, description=str(entry["description"]), effect_class=effect,
            handler=handler, module=module_ref,
            parameters_schema=dict(entry.get("parameters") or {"type": "object", "properties": {}}),
        )
    return actions
