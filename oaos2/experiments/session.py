"""Track live-run phases and the resources acquired in each phase.

The order is preflight, resources, execution, winddown, closed. preflight_ok()
is required before attaching resources. Each staged container registers with
the session, so cleanup acts on that run's handles. Finalization is guarded
against repeated calls. Cleanup is best effort: capture and isolation failures
are recorded and may leave resources for inspection. See docs/RUNBOOK.md for
orphan-container cleanup after interruption."""

from __future__ import annotations

import asyncio
import sys


class LifecycleError(RuntimeError):
    """A run-lifecycle ordering violation — a platform bug, never an
    operational failure (operational failures flow through abort())."""


_ORDER = ("preflight", "resources", "execution", "winddown", "closed")


class RunSession:
    def __init__(self, rd, run_id: str) -> None:
        self.rd = rd
        self.run_id = run_id
        self.phase = "preflight"
        self.spine = None
        self.backend = None
        self.policy = None
        self.handles: list = []  # staged container handles, in staging order
        self._preflight_ok = False
        self._finalized = False

    # ------------------------------------------------------------ ordering --
    def _advance(self, new_phase: str) -> None:
        # Single-step forward only (audit round 6 P1-2): skipping a phase is
        # as much a platform bug as moving backwards. abort() is the one
        # sanctioned jump — it closes the session directly from any phase.
        if _ORDER.index(new_phase) != _ORDER.index(self.phase) + 1:
            raise LifecycleError(
                f"run lifecycle must advance one phase: {self.phase} -> {new_phase}")
        self.phase = new_phase

    def preflight_ok(self) -> None:
        """Every load/validation check passed; resources may now exist."""
        if self.phase != "preflight":
            raise LifecycleError(f"preflight_ok in phase {self.phase}")
        self._preflight_ok = True

    def attach_resources(self, *, spine, backend, policy) -> None:
        """Attach the started event recorder and backend after preflight_ok() was called."""
        if not self._preflight_ok:
            raise LifecycleError("resources attached before preflight completed")
        self._advance("resources")
        self.spine, self.backend, self.policy = spine, backend, policy

    def register_handle(self, handle) -> None:
        if self.phase not in ("resources", "execution"):
            raise LifecycleError(f"container staged in phase {self.phase}")
        self.handles.append(handle)

    def release_handle(self, handle) -> None:
        """Forget a container the caller has already stopped and removed itself (a grading
        job, M8 §4). Teardown must not try to capture or remove it again."""
        self.handles = [h for h in self.handles if h is not handle]

    def begin_execution(self) -> None:
        self._advance("execution")

    def begin_winddown(self) -> None:
        self._advance("winddown")

    # ------------------------------------------------------------ teardown --
    async def teardown_all(self, disposition: str):
        """Attempt capture and removal for each registered container.

        Return the first IsolationViolation. Other capture errors are suppressed;
        failed captures can leave containers in place. Clear the registered handle
        list after the attempts, including handles whose cleanup failed."""
        from oaos2.docker.isolation import IsolationViolation
        from oaos2.docker.runner import capture_and_teardown
        isolation_error = None
        for handle in self.handles:
            try:
                await capture_and_teardown(self.spine, self.backend, self.rd,
                                           handle, self.policy, disposition)
            except IsolationViolation as exc:
                isolation_error = isolation_error or exc
            except Exception:  # noqa: BLE001 — capture failure must not mask the result
                pass
        self.handles = []
        return isolation_error

    async def abort(self, exc: BaseException, *, teardown: bool = True):
        """Attempt cleanup and a failed terminal record, then re-raise the original error.

        Trace finalization has a bounded retry. Cleanup or finalization can fail;
        this method does not guarantee container removal or a complete archive."""
        if teardown and self.handles:
            await self.teardown_all("failure")
        if self.spine is not None and not self._finalized:
            # Probe 2026-08-17: the retry is BOUNDED (a wedged finalize must not
            # hang abort with containers already gone — the spine's drain no
            # longer joins a dead writer, this is the belt over those braces),
            # the once-flag flips only on SUCCESS (matching finalize(); a failed
            # retry stays retryable), and a swallowed retry failure is at least
            # logged — the spine's own FINALIZE_FAILED marker records it
            # writer-independently on disk.
            try:
                await asyncio.wait_for(self.spine.finalize("failed"), timeout=60)
                self._finalized = True
            except Exception as retry_exc:  # noqa: BLE001 — the original error must surface
                print(f"RunSession.abort: terminal-record retry failed: "
                      f"{retry_exc!r} (aborting on: {exc!r})", file=sys.stderr)
        self.phase = "closed"
        raise exc

    async def finalize(self, status: str):
        """Finalize the spine exactly once and close the session.

        The flag flips only on SUCCESS (audit round 8 P1-3): if the spine's
        finalize raises, a subsequent abort() still attempts the 'failed'
        terminal record instead of silently skipping it.
        """
        if self._finalized:
            raise LifecycleError("spine finalized twice")
        self._advance("closed")
        report = await self.spine.finalize(status)
        self._finalized = True
        return report
