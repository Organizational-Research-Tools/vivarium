"""The calibrated ``paper_replication`` pack (``qje_good_manager``) — M7 §2.

The first real experiment, expressed through the platform abstractions and used
**unchanged, not redesigned per run**. Its calibration assets
(``expected_results.json``, the ``numeric_compare`` tolerance/OR-logic, the
feedback schema, the milestone graph, difficulty) ship hash-pinned as data/config.
"""

from oaos2.tasks.packs.paper_replication.pack import (
    build_paper_replication_pack,
    produce_milestone_payload,
)

__all__ = [
    "build_paper_replication_pack",
    "produce_milestone_payload",
]
