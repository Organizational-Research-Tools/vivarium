"""The settings reference (docs/world/settings_reference.yaml) names exactly what the workshop reads,
and the page rendered from it (docs/world/SETTINGS.md) is current."""
from __future__ import annotations

import dataclasses
import importlib.util
from pathlib import Path

import yaml

from oaos2.organizations.spec import OrganizationSpec, Role
from oaos2.tasks.plugins.materials_lab.pool import LabBounds
from oaos2.tasks.plugins.materials_lab.settings import RESTRICTED, SETTINGS
from oaos2.tasks.settings import COMMON

REPO = Path(__file__).resolve().parents[2]
REF = yaml.safe_load((REPO / "docs" / "world" / "settings_reference.yaml").read_text())


def _renderer():
    spec = importlib.util.spec_from_file_location("world_settings_reference",
                                                  REPO / "scripts" / "world_settings_reference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_reference_names_every_setting_the_workshop_reads_and_no_other():
    assert set(REF["plugin"]) == set(SETTINGS)
    assert set(REF["engine"]) == set(COMMON)
    assert set(REF["nested"]["bounds"]) == {f.name for f in dataclasses.fields(LabBounds)}
    assert set(REF["nested"]["audit"]) == {"probability", "delay_s"}
    assert set(REF["nested"]["restricted"]) == set(RESTRICTED)
    assert set(REF["nested"]["warm_start"]) == {"steps", "panels", "max_attempts"}


def test_every_setting_is_described_and_grouped():
    groups = {d for d, _ in _renderer().DIMENSIONS}
    for name, item in REF["plugin"].items():
        assert item["does"].strip() and item["values"].strip() and item["dimension"] in groups, name


def test_the_seven_parameters_each_hold_settings_and_state_their_levels():
    renderer = _renderer()
    parameters = {d for d, _ in renderer.DIMENSIONS} - {"mechanics"}
    assert len(parameters) == 7 and set(renderer.LEVELS) == parameters
    assert {item["dimension"] for item in REF["plugin"].values()} == parameters | {"mechanics"}


def test_the_organization_fields_exist():
    fields = {f.name for f in dataclasses.fields(OrganizationSpec)}
    role_fields = {f.name for f in dataclasses.fields(Role)}
    for name, item in REF["organization"].items():
        assert item["does"].strip() and item["values"].strip(), name
        assert (name.removeprefix("roles[].") in role_fields) if name.startswith("roles[].") else (name in fields), name


def test_the_page_is_current():
    page = (REPO / "docs" / "world" / "SETTINGS.md").read_text()
    assert page == _renderer().render(REF), "run scripts/world_settings_reference.py"
