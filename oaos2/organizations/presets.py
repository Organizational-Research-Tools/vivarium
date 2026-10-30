"""Convenience loaders for the original paper-replication organizations.

The single_agent, pipeline, role_blind_ensemble, and context_expanded_single_agent
helpers load YAML presets from library/organizations/. Other studies load their
own registered library presets. These helpers do not establish confirmatory
readiness or authorize a run."""

from __future__ import annotations

from oaos2.organizations.loader import load_org_spec
from oaos2.organizations.spec import OrganizationSpec


def single_agent() -> OrganizationSpec:
    return load_org_spec("single_agent")


def pipeline() -> OrganizationSpec:
    return load_org_spec("pipeline")


def role_blind_ensemble() -> OrganizationSpec:
    return load_org_spec("role_blind_ensemble")


def context_expanded_single_agent() -> OrganizationSpec:
    return load_org_spec("context_expanded_single_agent")


ALL_PRESETS = {
    "single_agent": single_agent,
    "pipeline": pipeline,
    "role_blind_ensemble": role_blind_ensemble,
    "context_expanded_single_agent": context_expanded_single_agent,
}
