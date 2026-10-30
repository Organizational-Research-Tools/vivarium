"""Resolve permission sets from enclosing to narrower scopes.

The default order is organization, role, then agent. None means unspecified;
an empty set grants nothing. narrow_grant intersects specified sets, while
check_not_broadening rejects attempted additions when both scopes are specified.

Callers supply the applicable scopes. order_scopes honors per-dimension order
overrides, including omitted scopes. These helpers do not enforce every field
of an organization automatically; each supported caller must use them."""

from __future__ import annotations

DEFAULT_PRECEDENCE = ("org", "role", "agent")


class BroadeningRejected(Exception):
    """A tighter scope tried to grant access an enclosing scope did not (DESIGN §4.9)."""


def narrow_grant(outer: frozenset | None, inner: frozenset | None) -> frozenset | None:
    """Intersect specified permission sets; inherit the other set when one is None.

    An empty set grants nothing. workspace.acl uses this same helper. Other
    permission paths must call it explicitly to apply this rule."""
    if inner is None:
        return outer
    if outer is None:
        return inner
    return outer & inner


def check_not_broadening(outer: frozenset | None, inner: frozenset | None, *, dimension: str = "") -> None:
    """Reject an inner grant that adds anything the outer scope didn't grant (load-time).

    Only meaningful when both are specified: an inner element absent from a specified
    outer set is a broadening attempt.
    """
    if outer is None or inner is None:
        return
    extra = set(inner) - set(outer)
    if extra:
        raise BroadeningRejected(
            f"tighter scope broadens {dimension or 'grant'} with {sorted(extra)} "
            "(a tighter scope may only narrow, DESIGN §4.9)"
        )


def resolve_scoped_grant(
    scopes: list[frozenset | None],
    *,
    dimension: str = "",
    reject_broadening: bool = True,
) -> frozenset | None:
    """Resolve one set-valued grant down the scope ladder (outermost first).

    Each tighter scope is intersected with the running grant; if ``reject_broadening``
    an inner scope that tries to add access raises ``BroadeningRejected`` (the
    load-time validator). Returns the narrowed grant (or ``None`` if no scope
    constrained the dimension at all).
    """
    present = [s for s in scopes if s is not None]
    if not present:
        return None
    resolved = present[0]
    for inner in present[1:]:
        if reject_broadening:
            check_not_broadening(resolved, inner, dimension=dimension)
        resolved = narrow_grant(resolved, inner)
    return frozenset(resolved) if resolved is not None else None


def order_scopes(scope_map: dict, *, dimension: str = "", precedence_rules: dict | None = None) -> list:
    """Order a ``{scope_name: grant}`` map outermost-first per the precedence ladder.

    Honors a per-dimension override in ``precedence_rules`` (e.g.
    ``{"tools": ("org", "role")}`` drops the agent scope entirely for tools), else the
    default org>role>agent.
    """
    order = (precedence_rules or {}).get(dimension, DEFAULT_PRECEDENCE)
    return [scope_map.get(name) for name in order]
