"""A preset that names a base lists only what it changes (loader.read_preset), and the comparison
tool reads presets as they run (organizations/compare.py)."""

from __future__ import annotations

import pytest
import yaml

from oaos2.organizations.compare import describe, preset_differences
from oaos2.organizations.loader import load_org_spec, read_preset

BASE = {
    "preset_id": "world",
    "base_only": True,
    "scheduler": "free",
    "roles": [{"role_id": "a", "attention": "all", "plays": ["a"]},
              {"role_id": "b", "attention": "all", "plays": ["b"]}],
    "live_coordination": {"mode": "deliberative", "max_rounds": 3,
                          "texts": {"objective": "Do the work.", "rule": "Follow the rule."}},
}


@pytest.fixture
def library(tmp_path, monkeypatch):
    orgs = tmp_path / "library" / "organizations"
    orgs.mkdir(parents=True)
    monkeypatch.setenv("OAOS2_LIBRARY", str(tmp_path / "library"))

    def write(name: str, preset: dict) -> None:
        (orgs / f"{name}.yaml").write_text(yaml.safe_dump(preset, sort_keys=False))

    write("world", BASE)
    return write


def test_an_overlay_merges_mappings_and_replaces_everything_else(library) -> None:
    library("arm", {"base": "world", "preset_id": "arm",
                    "live_coordination": {"max_rounds": 5, "texts": {"rule": "A new rule."}},
                    "roles": [{"role_id": "solo", "attention": "all", "plays": ["a", "b"]}]})
    m, bases = read_preset("arm")
    lc = m["live_coordination"]
    assert lc["mode"] == "deliberative" and lc["max_rounds"] == 5        # kept, changed
    assert lc["texts"] == {"objective": "Do the work.", "rule": "A new rule."}  # merged key by key
    assert [r["role_id"] for r in m["roles"]] == ["solo"]               # a list replaces the base's whole
    assert "base_only" not in m and [p.name for p in bases] == ["world.yaml"]
    spec = load_org_spec("arm")
    assert spec.preset_id == "arm" and spec.n_agents == 1
    assert spec.source_ref.name == "arm.yaml" and [p.name for p in spec.base_refs] == ["world.yaml"]


def test_bases_chain_outermost_first(library) -> None:
    library("study", {"base": "world", "preset_id": "study", "base_only": True,
                      "live_coordination": {"max_rounds": 4}})
    library("cell", {"base": "study", "preset_id": "cell", "live_coordination": {"mode": "free"}})
    m, bases = read_preset("cell")
    assert [p.name for p in bases] == ["world.yaml", "study.yaml"]
    assert m["live_coordination"]["max_rounds"] == 4 and m["live_coordination"]["mode"] == "free"
    assert load_org_spec("cell").preset_id == "cell"


def test_a_base_only_preset_is_not_run_alone(library) -> None:
    with pytest.raises(ValueError, match="base for other presets"):
        load_org_spec("world")


def test_an_overlay_must_name_itself_and_may_not_loop(library) -> None:
    library("nameless", {"base": "world", "live_coordination": {"max_rounds": 2}})
    with pytest.raises(ValueError, match="must give its own preset_id"):
        load_org_spec("nameless")
    library("x", {"base": "y", "preset_id": "x"})
    library("y", {"base": "x", "preset_id": "y"})
    with pytest.raises(ValueError, match="cycle"):
        load_org_spec("x")
    library("orphan", {"base": "missing", "preset_id": "orphan"})
    with pytest.raises(FileNotFoundError):
        load_org_spec("orphan")


def test_a_preset_without_a_base_loads_as_before(library) -> None:
    plain = {k: v for k, v in BASE.items() if k != "base_only"} | {"preset_id": "plain"}
    library("plain", plain)
    spec = load_org_spec("plain")
    assert spec.base_refs == () and spec.live_coordination == BASE["live_coordination"]


def test_the_comparison_reads_presets_as_they_run(library) -> None:
    long_rule = "Follow the rule. " * 10 + "Report every exception."
    library("arm_a", {"base": "world", "preset_id": "arm_a", "live_coordination": {"credit": "individual"}})
    library("arm_b", {"base": "world", "preset_id": "arm_b",
                      "live_coordination": {"credit": "collective", "texts": {"rule": long_rule}}})
    diffs = preset_differences("arm_a", "arm_b")
    assert [d["setting"] for d in diffs] == ["live_coordination.credit", "live_coordination.texts.rule"]
    assert describe(diffs[0]) == "live_coordination.credit: 'individual' -> 'collective'"
    text = describe(diffs[1])
    assert text.endswith("  +Report every exception.") and "  -" not in text   # sentences added, none removed
    assert preset_differences("arm_a", "arm_a") == []
    library("arm_c", {"base": "world", "preset_id": "arm_c", "live_coordination": {"extra": 1}})
    assert preset_differences("arm_a", "arm_c")[1] == {"setting": "live_coordination.extra",
                                                       "a": "<not set>", "b": 1}


def test_the_design_view_marks_an_overlay_whose_base_changed(library, tmp_path) -> None:
    import hashlib

    from oaos2.archive.design import organization_of

    library("arm", {"base": "world", "preset_id": "arm", "live_coordination": {"max_rounds": 5}})
    spec = load_org_spec("arm")
    sha = lambda p: "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()  # noqa: E731
    manifest = {"organization_id": "arm", "extensions": {
        "organization_sha256": sha(spec.source_ref),
        "organization_bases": [{"ref": str(b), "sha256": sha(b)} for b in spec.base_refs]}}
    assert organization_of(manifest)["pin_ok"] is True
    library("world", {**BASE, "scheduler": "round_robin"})  # the base changes after the run
    assert organization_of(manifest)["pin_ok"] is False


def test_presets_outside_the_library_are_found_on_the_search_path(library, tmp_path, monkeypatch) -> None:
    from oaos2.organizations.loader import org_path

    extra = tmp_path / "fixtures"
    extra.mkdir()
    (extra / "fixture_arm.yaml").write_text(yaml.safe_dump({"base": "world", "preset_id": "fixture_arm"}))
    monkeypatch.setenv("OAOS2_ORGANIZATIONS", str(extra))
    assert org_path("fixture_arm") == extra / "fixture_arm.yaml"
    assert org_path("world").parent.name == "organizations"            # the library comes first
    assert load_org_spec("fixture_arm").base_refs[0].name == "world.yaml"  # a fixture may rest on a library base
    monkeypatch.delenv("OAOS2_ORGANIZATIONS")
    with pytest.raises(FileNotFoundError):
        load_org_spec("fixture_arm")


def test_the_library_page_groups_presets_by_their_declared_base(library, monkeypatch) -> None:
    from oaos2.dashboard import workbench

    library("arm_a", {"base": "world", "preset_id": "arm_a", "live_coordination": {"max_rounds": 4}})
    library("zz", {"base": "arm_a", "preset_id": "zz", "live_coordination": {"mode": "free"}})
    lib = workbench.list_library()
    fams = workbench.organization_families(lib["organizations"])
    fam = next(f for f in fams if f["base"] == "world")
    assert [m["name"] for m in fam["members"]] == ["world", "arm_a", "zz"]
    assert fam["members"][0]["is_base"] and all("error" not in m for m in fam["members"])
    assert not any(f["label"] == "presets that fail to load" for f in fams)
