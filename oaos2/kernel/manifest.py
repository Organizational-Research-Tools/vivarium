"""Record the versions and execution settings needed to identify a run.

manifest.json includes the image digest, execution-policy hash, pricing and
retention settings, and archive schema version. Additional runner fields
identify the task, organization, model assignments, and resolved study inputs.
A hash is a content fingerprint; matching one field is not a complete test of
whether two runs are comparable."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from oaos2.trace.schema import SCHEMA_VERSION


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    experiment_id: str
    task_pack_id: str
    mode: str = "pilot"
    schema_version: str = SCHEMA_VERSION

    image_ref: str | None = None
    image_digest: str | None = None
    policy_hash: str | None = None
    pricing_table_version: str | None = None  # M3
    retention_policy_hash: str | None = None  # M0 §7
    organization_id: str | None = None
    extensions: dict = Field(default_factory=dict)  # namespaced; core never reads

    def write(self, path: Path) -> None:
        Path(path).write_text(json.dumps(self.model_dump(), indent=2, sort_keys=True))

    @classmethod
    def read(cls, path: Path) -> "Manifest":
        return cls.model_validate_json(Path(path).read_text())
