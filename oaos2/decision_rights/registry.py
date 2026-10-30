"""Validate role-authority declarations and answer common permission checks.

Runtime callers check submission permission and accepted handoff senders.
Review authority is declared metadata: its predicate has no current enforcement
caller. Missing values permit submissions and handoffs and declare no review
targets. Extensions can add registered names, but callers must implement their
behavior. There is no built-in veto action."""

from __future__ import annotations

from dataclasses import dataclass, field

# Built-in default rights. Extensions can register additional keys; their callers
# must implement any new permission checks.
COLLABORATION_DEFAULT_RIGHTS = frozenset({
    "may_submit_milestones",     # bool: may this role close/commit outcome milestones
    "may_accept_handoffs_from",  # tuple[str]|("*",): role_ids whose handoffs it may receive
    "review_authority_over",     # tuple[str]: declared review targets; not an action gate
})


class UnknownDecisionRight(Exception):
    """A role declared a decision-right key not in the registry (DESIGN §18.1)."""


@dataclass(frozen=True)
class DecisionRights:
    """One role's declared rights. Absent keys take the collaboration-default (permissive
    for ``may_submit_milestones`` / ``may_accept_handoffs_from``, empty for review).

    ``extensions`` carries pack-specific rights (politics/culture); their KEYS are
    validated against the registry just like the built-ins.
    """

    may_submit_milestones: bool = True
    may_accept_handoffs_from: tuple = ("*",)  # "*" ⇒ any role
    review_authority_over: tuple = ()
    extensions: dict = field(default_factory=dict)

    def declared_keys(self) -> set[str]:
        """Return declared key names for validation, including all built-ins.

        A validated declaration does not establish that an action checks it.
        """
        return set(COLLABORATION_DEFAULT_RIGHTS) | set(self.extensions)

    # Pure predicates; runtime callers currently use submission and acceptance.

    def can_submit(self) -> bool:
        return self.may_submit_milestones

    def can_accept_handoff_from(self, from_role: str) -> bool:
        return "*" in self.may_accept_handoffs_from or from_role in self.may_accept_handoffs_from

    def has_review_authority_over(self, role_id: str) -> bool:
        """Check declared review metadata; no current runtime action calls this."""
        return role_id in self.review_authority_over


class DecisionRightsRegistry:
    """The open set of valid decision-right keys (DESIGN §18.1, §23).

    Defaults to the collaboration-default rights; a pack registers additional keys
    before validating roles. ``validate`` rejects any role using an unregistered key.
    """

    def __init__(self, rights: frozenset[str] | set[str] | None = None) -> None:
        self.rights: set[str] = set(rights) if rights is not None else set(COLLABORATION_DEFAULT_RIGHTS)

    def register(self, key: str) -> None:
        self.rights.add(key)

    def __contains__(self, key: str) -> bool:
        return key in self.rights

    def validate(self, decision_rights: DecisionRights, *, role_id: str = "") -> None:
        unknown = decision_rights.declared_keys() - self.rights
        if unknown:
            raise UnknownDecisionRight(
                f"role {role_id!r} declares decision rights not in the registry: "
                f"{sorted(unknown)} (register them on the pack's DecisionRightsRegistry first)"
            )
