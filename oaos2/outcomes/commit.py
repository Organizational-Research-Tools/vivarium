"""Accept official submissions through the host's sole StateCommitment writer.

commit checks dependencies and required structure, writes the submitted payload,
records its agent and hash, and checks whether the outcome can close. Containers
mount submitted/ read-only. A per-outcome lock covers acceptance through closure
so competing submissions cannot close the outcome twice. Callers supply causal
predecessors used later to identify contributing interventions."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from oaos2.outcomes.conformance import CommitmentConformanceError, check_conformance
from oaos2.outcomes.contracts import OutcomeContract, closure_met
from oaos2.trace.records import StateCommitment
from oaos2.trace.spine import RunSpine


class OutcomeCoordinator:
    """Owns an OutcomeContract's committed set and the sole commit() path."""

    def __init__(self, contract: OutcomeContract, spine: RunSpine, submitted_dir: Path,
                 on_close=None, on_commit=None):
        contract.validate()  # reject cyclic blocks / no closure at load
        self.contract = contract
        self.spine = spine
        self.submitted_dir = Path(submitted_dir)
        self.submitted_dir.mkdir(parents=True, exist_ok=True)
        self.committed: dict[str, StateCommitment] = {}
        self.committed_event_ids: dict[str, str] = {}  # commitment_id -> state.committed event id
        self.payloads: dict[str, dict] = {}  # commitment_id -> committed payload (for scoring)
        self.on_close = on_close  # called when the outcome closes (e.g. rs.close_outcome)
        # Optional async task-generic stage hook.  It runs only after the immutable
        # state.committed event exists, so any resulting observation cites the commit.
        self.on_commit = on_commit
        self._lock = asyncio.Lock()
        self.closed = False
        self.closed_event_id: str | None = None

    async def commit(
        self,
        *,
        commitment_id: str,
        payload: dict,
        agent_id: str,
        session_id: str,
        caused_by: str | list[str] | None = None,
    ) -> StateCommitment | None:
        """Commit one StateCommitment; close the outcome if the condition is met.

        Returns the StateCommitment, or None on a protocol violation (refused).
        """
        c = self.contract.commitment(commitment_id)
        async with self._lock:  # serialize commits to THIS outcome (gate→store→close)
            unmet = [b for b in c.blocks if b not in self.committed]
            if unmet:
                await self.spine.emit_event(
                    "protocol.violation", agent_id=agent_id, caused_by=caused_by,
                    payload={"reason": "commit_before_blockers", "unmet": unmet},
                )
                return None
            if commitment_id in self.committed:
                await self.spine.emit_event(
                    "protocol.violation", agent_id=agent_id, caused_by=caused_by,
                    payload={"reason": "already_committed", "commitment_id": commitment_id},
                )
                return None

            # This is the sole writer, so it is also the final conformance authority.
            # Agent submissions are prechecked to provide corrective feedback, while
            # platform coordination and offline solvers reach this backstop directly.
            ok, problems = check_conformance(payload, c.submission or {}, committed=self.payloads,
                                             commitment=c)
            if not ok:
                await self.spine.emit_event(
                    "outcome.commit_refused", agent_id=agent_id, caused_by=caused_by,
                    payload={"commitment_id": commitment_id, "reason": "nonconformant",
                             "problems": problems},
                )
                raise CommitmentConformanceError(commitment_id, problems)

            blob = json.dumps(payload, sort_keys=True).encode()
            content_hash = "sha256:" + hashlib.sha256(blob).hexdigest()
            payload_path = self.submitted_dir / f"{commitment_id}.json"
            payload_path.write_bytes(blob)  # host writes the OS-ro-to-container zone

            sc = StateCommitment(
                commitment_id=commitment_id, kind=c.kind, agent_id=agent_id,
                session_id=session_id, payload_ref=f"submitted/{commitment_id}.json",
                content_hash=content_hash, caused_by_event_ids=_as_list(caused_by),
            )
            self.committed[commitment_id] = sc
            self.payloads[commitment_id] = payload
            committed_event = await self.spine.emit_event(
                "state.committed", agent_id=agent_id, session_id=session_id, caused_by=caused_by,
                payload={"state_commitment": sc.model_dump(), "content_hash": content_hash},
            )
            self.committed_event_ids[commitment_id] = committed_event

            if self.on_commit is not None:
                await self.on_commit(commitment_id, sc, committed_event)

            if not self.closed and closure_met(
                self.contract.closure_condition, self.committed, self.contract
            ):
                self.closed = True
                self.closed_event_id = await self.spine.emit_event(
                    "outcome.closed", caused_by=committed_event,
                    payload={"outcome_id": self.contract.outcome_id},
                )
                if self.on_close is not None:
                    self.on_close()  # e.g. rs.close_outcome() → scheduler exits
            return sc


def _as_list(caused_by) -> list[str]:
    if caused_by is None:
        return []
    if isinstance(caused_by, str):
        return [caused_by]
    return list(caused_by)
