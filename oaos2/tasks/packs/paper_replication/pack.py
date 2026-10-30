"""``paper_replication`` pack entry points — thin wrappers over the loader.

The pack is now **declarative data** in ``library/tasks/paper_replication/`` (manifest
+ assets); this module just loads it. The source of truth is the manifest, so a
config tool edits YAML, not code. The deterministic offline solver
(``produce_milestone_payload``) is a pack plugin re-exported here for the runner.
"""

from __future__ import annotations

from oaos2.tasks.loader import load_task_pack
from oaos2.tasks.pack import TaskPack
from oaos2.tasks.plugins.paper_replication.solver import (  # re-export for the offline runner
    correct_results,
    produce_milestone_payload,
)

PACK_ID = "paper_replication"


def build_paper_replication_pack(*, decomposed: bool = True) -> TaskPack:
    """Load the calibrated ``paper_replication`` pack from its manifest (M7 §2)."""
    return load_task_pack(PACK_ID, decomposed=decomposed)


__all__ = ["PACK_ID", "build_paper_replication_pack", "correct_results", "produce_milestone_payload"]
