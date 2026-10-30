"""Create the host directories used to preserve a run.

A run lives at runs/{experiment_id}/{task_pack_id}/{run_id}/. manifest.json
identifies it; trace/ holds events, the index, and recovery files. visible/
holds read-only task materials. container_mount/ holds agent scratch, shared
files, and accepted submissions; captured/ holds copies made during cleanup.

Host-backed workspace files survive container termination. Temporary container
storage is separate and does not have this guarantee. See docker/mounts.py for
mount permissions and docker/runner.py for capture and removal behavior."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunDir:
    root: Path  # runs/{experiment_id}/{task_pack_id}/{run_id}/

    @classmethod
    def create(
        cls, runs_root: Path, experiment_id: str, task_pack_id: str, run_id: str
    ) -> "RunDir":
        root = Path(runs_root) / experiment_id / task_pack_id / run_id
        if root.exists():
            # Refuse to interleave two runs into one archive (audit round 4
            # P1-3: colliding run ids produced a dir with two run.started
            # events that still validated). Callers wanting a rerun pick a
            # fresh run_id; nothing silently overwrites a trace.
            raise FileExistsError(f"run directory already exists: {root}")
        rd = cls(root=root)
        for d in (
            rd.trace,
            rd.container_mount,
            rd.agents_root,
            rd.shared,
            rd.submitted,
            rd.visible,
            rd.captured,
            rd.config,
            rd.attempts,
            rd.grading,
        ):
            d.mkdir(parents=True, exist_ok=True)
        return rd

    # -- trace (M1) --------------------------------------------------------- #
    @property
    def trace(self) -> Path:
        return self.root / "trace"

    # -- writable container state ------------------------------------------ #
    @property
    def container_mount(self) -> Path:
        return self.root / "container_mount"

    @property
    def agents_root(self) -> Path:
        return self.container_mount / "agents"

    def agent_scratch(self, agent_id: str) -> Path:
        return self.agents_root / agent_id

    @property
    def shared(self) -> Path:
        return self.container_mount / "shared"

    @property
    def submitted(self) -> Path:
        return self.container_mount / "submitted"

    # -- read-only materials + capture ------------------------------------- #
    @property
    def visible(self) -> Path:
        return self.root / "visible"

    @property
    def captured(self) -> Path:
        return self.root / "captured"

    @property
    def grading(self) -> Path:
        """Host-only staging for grading and assessment containers (M8 §4): one directory
        per attempt holding the checkout the grader mounts. Never mounted into an agent
        container."""
        return self.root / "grading"

    @property
    def attempts(self) -> Path:
        """Host-only attempt snapshots (M8 §3). Never mounted into any participant
        container: an unpublished attempt must not be readable by other agents."""
        return self.root / "attempts"

    @property
    def config(self) -> Path:
        """Resolved-config snapshot (DESIGN §17.3): which org/roles/agents/task/model/exposure."""
        return self.root / "config"

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    @property
    def derived(self) -> Path:
        """Re-rendered views (DESIGN §17.3): the four standard transcripts + metrics.json.
        Regenerated from the immutable trace by ``oaos2/archive`` — never a source of truth."""
        return self.root / "derived"

    @property
    def annotations(self) -> Path:
        """Analytic annotation slot (DESIGN §17.3, §16): ``AnnotationLink`` records,
        sharded by namespace, written post-hoc by ``oaos2/annotations`` over the trace."""
        return self.root / "annotations"

    def ensure_agent_scratch(self, agent_id: str) -> Path:
        p = self.agent_scratch(agent_id)
        p.mkdir(parents=True, exist_ok=True)
        return p
