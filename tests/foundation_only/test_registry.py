"""Registry composition tests (M0 §5.4 / DESIGN §5.4).

Exercises the four committed semantics: inherits_from, override-required-on-
redefine, removes, and a deterministic diamond resolution (the synthetic-registry
gate, §22).
"""

from __future__ import annotations

import pytest

from oaos2.registry import RegistryError, RegistrySpec


def test_inherits_and_extends() -> None:
    base = RegistrySpec("base", entries={"a": 1, "b": 2})
    child = RegistrySpec("child", entries={"c": 3}, inherits_from=(base,))
    r = child.resolve()
    assert r.ids() == {"a", "b", "c"}
    assert r["a"] == 1 and r["c"] == 3


def test_redefine_requires_override() -> None:
    base = RegistrySpec("base", entries={"a": 1})
    bad = RegistrySpec("bad", entries={"a": 99}, inherits_from=(base,))
    with pytest.raises(RegistryError):
        bad.resolve()
    good = RegistrySpec(
        "good", entries={"a": 99}, inherits_from=(base,), overrides=frozenset({"a"})
    )
    assert good.resolve()["a"] == 99


def test_removes() -> None:
    base = RegistrySpec("base", entries={"a": 1, "b": 2})
    child = RegistrySpec("child", inherits_from=(base,), removes=("b",))
    r = child.resolve()
    assert "b" not in r and "a" in r


def test_diamond_resolves_deterministically() -> None:
    # root -> {left, right} -> top ; top overrides root's "x".
    root = RegistrySpec("root", entries={"x": "root", "shared": "root"})
    left = RegistrySpec("left", entries={"l": "L"}, inherits_from=(root,))
    right = RegistrySpec("right", entries={"r": "R"}, inherits_from=(root,))
    top = RegistrySpec(
        "top",
        entries={"x": "top"},
        inherits_from=(left, right),
        overrides=frozenset({"x"}),
    )
    # Resolve repeatedly: identical resolution across loads (§22 diamond assertion).
    first = top.resolve()
    second = top.resolve()
    assert first.ids() == second.ids() == {"x", "shared", "l", "r"}
    assert first["x"] == second["x"] == "top"
    # root appears via two paths but contributes "shared" exactly once, consistently.
    assert first["shared"] == "root"


def test_unknown_entry_raises_on_access_and_validate() -> None:
    r = RegistrySpec("base", entries={"a": 1}).resolve()
    with pytest.raises(RegistryError):
        _ = r["nope"]
    with pytest.raises(RegistryError):
        r.validate("nope")
    assert r.get("nope") is None
