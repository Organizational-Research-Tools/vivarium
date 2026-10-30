"""Managed grading jobs for attempts made during a run (M8 §4).

A grader is a job, not an evaluator call: it takes an immutable attempt snapshot
and returns one terminal result kind. The result kinds are mutually exclusive
and distinguish a negative evaluation (``failed``) from infrastructure outcomes
(``evaluation_unavailable``) and from an uncompleted evaluation whose cause is
not established (``execution_limit``).

This module ships the job contract, a simulated backend for offline checks, and
a container-managed backend. The simulated backend decides by comparing the
patched file to a hidden reference and honors fault markers in the patch text,
so every result kind can be exercised without executing submitted code. The
container backend applies the gradable change to the pinned repository and runs
its public tests in a managed container; it accepts only a complete report from
its own launcher, never an exit code alone. Status: DEFERRED.md §8.

Main caller: a coordination procedure's credit dispatcher. Limit: nothing here
touches the outcome commit path or the trace; callers record events.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

RESULT_KINDS: frozenset[str] = frozenset({
    "passed", "failed", "invalid_patch", "execution_limit",
    "evaluation_unavailable", "cancelled"})

# Kinds charged to the attempt (the agent's work) versus to grading itself.
CHARGED_TO_ATTEMPT: frozenset[str] = frozenset(
    {"passed", "failed", "invalid_patch", "execution_limit"})

# Public status text per kind (M8 §4): delivered to the submitting agent. None of
# these represents an infrastructure outcome as a failed repair.
PUBLIC_STATUS: dict[str, str] = {
    "passed": "Passed: the public tests passed.",
    "failed": "Failed: at least one public test failed.",
    "invalid_patch": "Patch did not apply to the pinned base.",
    "execution_limit": ("Execution limit reached: the tests did not complete within the "
                        "declared time or memory limit. This is not a test failure; the "
                        "cause is not established."),
    "evaluation_unavailable": ("Evaluation unavailable: the grading service failed. This is "
                               "not a result about your patch; you may resubmit without "
                               "penalty."),
    "cancelled": "Evaluation cancelled: the run ended before grading completed.",
}

# Fault markers a simulated fixture may place in a patch to exercise result kinds.
SIM_MARKERS: dict[str, str] = {
    "# SIM:execution_limit": "execution_limit",
    "# SIM:evaluation_unavailable": "evaluation_unavailable",
}


@dataclass
class GradeRequest:
    attempt_id: str
    issue_id: str
    base_revision: str
    patch_text: str
    patched_files: dict  # path -> full content after the patch; None = the file was deleted
    grader_version: str


@dataclass
class GradeResult:
    attempt_id: str
    kind: str  # one of RESULT_KINDS
    failed_tests: list[str] = field(default_factory=list)
    output_excerpt: str = ""
    retries: int = 0
    diagnostics: dict = field(default_factory=dict)  # private; never delivered to agents

    def __post_init__(self) -> None:
        if self.kind not in RESULT_KINDS:
            raise ValueError(f"unknown grade result kind {self.kind!r}")

    @property
    def charged_to_attempt(self) -> bool:
        return self.kind in CHARGED_TO_ATTEMPT

    @property
    def public_status(self) -> str:
        return PUBLIC_STATUS[self.kind]


class GradingBackend(Protocol):
    """One grading job: never trusts an agent-reported result, never reads the
    agent's working copy, and raises nothing for an ordinary failed repair."""

    backend_id: str

    async def grade(self, request: GradeRequest) -> GradeResult: ...


class GradingServiceError(Exception):
    """The grading service itself failed (not a verdict on the patch)."""


@dataclass
class SimulatedGrader:
    """Offline grader for apparatus checks (M8 §11, phase 2).

    ``reference`` maps repository path -> the content a correct repair produces
    for that file; a patched file matching its reference (ignoring trailing
    whitespace) passes. ``delay_s`` simulates test duration so queue and run
    times are observable and cancellation can be exercised. Fault markers in the
    patch text produce the corresponding result kind; an ``evaluation_unavailable``
    marker fails ``unavailable_times`` times and then, if retried further,
    succeeds, so bounded retries are exercised.
    """

    reference: dict[str, str]  # used when reference_by_issue has no entry for the issue
    failing_test_name: str = "tests/test_fixture.py::test_expected_behavior"
    delay_s: float = 0.0
    unavailable_times: int = 1
    backend_id: str = "simulated"
    # issue_id -> {path: reference content}: a common faulty snapshot has one
    # reference per issue (the healthy version of that issue's file).
    reference_by_issue: dict = field(default_factory=dict)
    failing_test_by_issue: dict = field(default_factory=dict)
    _unavailable_seen: dict[str, int] = field(default_factory=dict)

    def reference_for(self, issue_id: str) -> dict:
        return self.reference_by_issue.get(issue_id, self.reference)

    async def grade(self, request: GradeRequest) -> GradeResult:
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        for marker, kind in SIM_MARKERS.items():
            if marker in request.patch_text:
                if kind == "evaluation_unavailable":
                    seen = self._unavailable_seen.get(request.attempt_id, 0)
                    self._unavailable_seen[request.attempt_id] = seen + 1
                    if seen < self.unavailable_times:
                        raise GradingServiceError("simulated grading service fault")
                    continue  # recovered on retry: fall through to the verdict
                return GradeResult(attempt_id=request.attempt_id, kind=kind,
                                   output_excerpt="simulated: tests did not complete",
                                   diagnostics={"simulated_marker": marker})
        for path, expected in self.reference_for(request.issue_id).items():
            got = request.patched_files.get(path)
            if got is None or got.rstrip() != expected.rstrip():
                return GradeResult(
                    attempt_id=request.attempt_id, kind="failed",
                    failed_tests=[self.failing_test_by_issue.get(request.issue_id,
                                                                 self.failing_test_name)],
                    output_excerpt="simulated: patched file does not match the reference",
                    diagnostics={"mismatched_path": path})
        return GradeResult(attempt_id=request.attempt_id, kind="passed",
                           output_excerpt="simulated: all public tests passed")


# --------------------------------------------------------------------------- #
# Container-managed grading and assessment (M8 §4): real execution of a patched
# checkout inside a session-registered container. Never runs on the host.
# --------------------------------------------------------------------------- #

_FAILED_LINE = re.compile(r"^(?:FAILED|ERROR) (\S+)")

# Runs pytest over a JSON list of arguments without a shell (test ids may carry quotes,
# ampersands, brackets, and " - "), and reports every item's EXACT node id and outcome
# as one marked JSON line on stdout. Parsing pytest's short summary is not reliable:
# a parametrized id that itself contains " - " or a newline gets cut. argv[1] is the
# arguments file; argv[2], when given, is the directory to run in. Exit code is pytest's.
#
# The report also carries the ids pytest COLLECTED, recorded before any test runs. The
# grader accepts only when every collected id has a reported outcome: a test process that
# ends early (submitted code calling ``os._exit(0)`` during a test, for example) exits
# without the marker or with outcomes missing, and neither is a pass. The audit of
# September 16, 2026 found that a successful exit code alone was being accepted.
PYTEST_LAUNCHER = (
    "import json, os, sys\n"
    "args = json.load(open(sys.argv[1]))\n"
    "if len(sys.argv) > 2: os.chdir(sys.argv[2])\n"
    "import pytest\n"
    "class _R:\n"
    "    def __init__(self): self.out = {}; self.collected = []\n"
    "    def pytest_collection_finish(self, session):\n"
    "        self.collected = [i.nodeid for i in session.items]\n"
    "    def pytest_runtest_logreport(self, report):\n"
    "        if report.when == 'call' or (report.when == 'setup' and report.outcome != 'passed') "
    "or report.nodeid not in self.out:\n"
    "            self.out[report.nodeid] = report.outcome if report.when == 'call' or report.outcome != 'passed' "
    "else self.out.get(report.nodeid, 'passed')\n"
    "r = _R()\n"
    "code = int(pytest.main(args, plugins=[r]))\n"
    "print('OAOS2_PYTEST_RESULTS ' + json.dumps({'exit_code': code, 'results': r.out, "
    "'collected': r.collected}))\n"
    "sys.exit(code)\n"
)
PYTEST_BASE_ARGS = ["-q", "-p", "no:cacheprovider", "--tb=line", "-rfE"]
_RESULTS_MARKER = "OAOS2_PYTEST_RESULTS "


def pytest_argv(selection_path_in_env: str, cwd_in_env: str = "/work/repo") -> list[str]:
    return ["python", "-c", PYTEST_LAUNCHER, selection_path_in_env, cwd_in_env]


def parse_pytest(stdout: str) -> tuple[list[str], str, dict | None]:
    """(failed ids, summary line, exact results or None). Exact ids come from the
    launcher's marker line; the short-summary lines are the fallback only."""
    lines = stdout.splitlines()
    results = None
    for line in reversed(lines):
        if line.startswith(_RESULTS_MARKER):
            try:
                results = json.loads(line[len(_RESULTS_MARKER):])
            except json.JSONDecodeError:
                results = None
            break
    if results is not None:
        failed = sorted(n for n, o in results["results"].items() if o in ("failed", "error"))
    else:
        failed = sorted({m.group(1) for line in lines for m in [_FAILED_LINE.match(line)] if m})
    summary = next((line for line in reversed(lines) if not line.startswith(_RESULTS_MARKER)
                    and ("passed" in line or "failed" in line or "error" in line)), "")
    return failed, summary, results


def verdict_complete(results: dict | None, selection: list[str] | None = None) -> tuple[bool, list[str], str]:
    """Whether the launcher's report is evidence that the selected tests ran and passed.

    Returns (complete, unproven ids, reason). The report is complete when it exists,
    pytest itself reported exit 0, at least one test was collected, and every collected
    id has the outcome ``passed``. Ids that were collected but never reported, or reported
    with any outcome other than ``passed`` (a skip raised from library code is not a
    pass), are returned as unproven. When a ``selection`` of exact node ids is given, a
    selected id absent from the collection is unproven too, so a selection that pytest
    silently failed to collect cannot pass by being empty. An exit code of 0 from the
    process is necessary but never sufficient (M8 §4).
    """
    if results is None:
        return False, sorted(selection or []), "no results report: the test process ended without reporting"
    collected = list(results.get("collected") or [])
    outcomes = dict(results.get("results") or {})
    if not collected:
        # A launcher without the collection hook (older evidence) reports nothing here;
        # fall back to the reported outcomes, which still must all be passes.
        collected = sorted(outcomes)
    unproven = sorted({n for n in collected if outcomes.get(n) != "passed"}
                      | {n for n in (selection or []) if "::" in n and n not in collected})
    if not collected:
        return False, unproven, "no tests collected"
    if results.get("exit_code") != 0:
        return False, unproven, f"pytest exit {results.get('exit_code')}"
    if unproven:
        missing = [n for n in unproven if n not in outcomes]
        return False, unproven, (f"{len(missing)} of {len(collected)} collected tests never reported"
                                 if missing else "not every collected test passed")
    return True, [], "complete"


def stage_checkout(base_repo: Path, target: Path, patched_files: dict) -> list[str]:
    """Copy the pinned base to ``target`` and apply the gradable change: full contents
    for modified or added paths, deletion for None. Returns the applied paths. Paths
    that escape the checkout are refused with ValueError."""
    shutil.copytree(base_repo, target, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    root_real = os.path.realpath(target)
    applied = []
    for rel, content in patched_files.items():
        dest = target / rel
        if not os.path.realpath(dest).startswith(root_real + os.sep):
            raise ValueError(f"patch path escapes the checkout: {rel}")
        if content is None:
            if dest.exists():
                dest.unlink()
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)
        applied.append(rel)
    return applied


@dataclass
class ContainerGrader:
    """Grade an attempt by running the public tests inside a managed container.

    The checkout is staged host-side under the run's ``grading/<attempt_id>/`` area and
    mounted read-only at ``/work/repo``; the container has no network, runs as a
    non-root user on a read-only root filesystem with a private ``/tmp``, and is
    registered with the run session while it lives. Result kinds follow M8 §4:
    ``passed``, ``failed`` (with the failing test ids), ``invalid_patch`` (the change
    could not be applied), ``execution_limit`` (the tests did not finish within the
    limit; the container is stopped), ``evaluation_unavailable`` (the service failed),
    each with the container's timing in the diagnostics.
    """

    backend: object
    spine: object
    session: object
    run_dir: object
    image_ref: str
    image_digest: str
    base_repo: Path
    public_tests_by_issue: dict  # issue_id -> [pytest node ids]
    test_timeout_s: int = 300
    mem_limit: str = "2g"
    cpu_limit: float = 2.0
    pid_limit: int = 512
    backend_id: str = "container"
    _container_seq: int = 0

    async def _run_in_container(self, attempt_id: str, label: str, mounts: list, argv: list[str],
                                timeout_s: int, extra_env: dict | None = None) -> dict:
        """Start a container over ``mounts``, exec ``argv`` once, stop and remove it.
        Returns {exit_code, stdout, stderr, timed_out, duration_s, service_error}."""
        from oaos2.docker.isolation import IsolationViolation
        self._container_seq += 1
        agent_id = f"grader_{label}_{self._container_seq}"
        handle = None
        t0 = time.monotonic()
        try:
            handle = await self.backend.run(
                image=self.image_ref, digest=self.image_digest, mounts=mounts,
                env={"HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "/work/repo",
                     **(extra_env or {})},
                network="disabled", memory=self.mem_limit, cpus=self.cpu_limit,
                pids=self.pid_limit, disk="1g", wall_clock=timeout_s + 120,
                user="nonroot_ro_rootfs", agent_id=agent_id, mount_root=mounts[0].host_path,
                tmpfs_tmp=True)
        except Exception as exc:  # noqa: BLE001 — a launch failure is a service failure
            return {"service_error": repr(exc), "duration_s": time.monotonic() - t0}
        timed_out = False
        try:
            if self.session is not None:
                self.session.register_handle(handle)
            await self.spine.emit_event(
                "grade.container_started", agent_id=agent_id,
                payload={"attempt_id": attempt_id, "container_id": handle.container_id,
                         "image_digest": self.image_digest, "label": label})
            try:
                res = await self.backend.exec(handle, argv, timeout=timeout_s)
            except IsolationViolation as exc:
                # The backend stops the container on a tool timeout and raises; for a
                # grading job that is the execution-limit outcome, not a run failure.
                timed_out = "timed out" in str(exc)
                if not timed_out:
                    return {"service_error": repr(exc), "duration_s": time.monotonic() - t0}
                res = None
            except Exception as exc:  # noqa: BLE001 — the daemon failed mid-job
                return {"service_error": repr(exc), "duration_s": time.monotonic() - t0}
            return {"exit_code": None if res is None else res.exit_code,
                    "stdout": "" if res is None else res.stdout,
                    "stderr": "" if res is None else res.stderr,
                    "timed_out": timed_out, "duration_s": time.monotonic() - t0,
                    "oom_killed": bool(res and res.oom_killed)}
        finally:
            try:
                if not timed_out:
                    await self.backend.stop(handle)
            except Exception:  # noqa: BLE001
                pass
            try:
                await self.backend.remove(handle)
            except Exception:  # noqa: BLE001
                pass
            if self.session is not None:
                self.session.release_handle(handle)
            await self.spine.emit_event(
                "grade.container_removed", agent_id=agent_id,
                payload={"attempt_id": attempt_id, "label": label,
                         "duration_s": round(time.monotonic() - t0, 3)})

    def _mounts(self, checkout: Path, extra: list | None = None) -> list:
        from oaos2.docker.policy import Mount
        from oaos2.workspace.zones import MountMode
        return [Mount(checkout, "/work/repo", MountMode.RO), *(extra or [])]

    async def grade(self, request: GradeRequest) -> GradeResult:
        stage_dir = Path(self.run_dir.grading) / request.attempt_id
        checkout = stage_dir / "repo"
        try:
            stage_checkout(self.base_repo, checkout, request.patched_files)
        except Exception as exc:  # noqa: BLE001 — a change that cannot be applied
            return GradeResult(attempt_id=request.attempt_id, kind="invalid_patch",
                               output_excerpt=str(exc)[:500], diagnostics={"stage_error": repr(exc)})
        tests = list(self.public_tests_by_issue.get(request.issue_id) or ["tests"])
        select_dir = stage_dir / "select"
        select_dir.mkdir(exist_ok=True)
        (select_dir / "public.json").write_text(json.dumps(PYTEST_BASE_ARGS + tests))
        from oaos2.docker.policy import Mount
        from oaos2.workspace.zones import MountMode
        out = await self._run_in_container(
            request.attempt_id, "public",
            self._mounts(checkout, [Mount(select_dir, "/work/select", MountMode.RO)]),
            pytest_argv("/work/select/public.json"), self.test_timeout_s)
        diag = {"container": {k: v for k, v in out.items() if k not in ("stdout", "stderr")},
                "stderr_tail": (out.get("stderr") or "")[-1500:]}
        if out.get("service_error"):
            return GradeResult(attempt_id=request.attempt_id, kind="evaluation_unavailable",
                               diagnostics={**diag, "error": out["service_error"]})
        if out.get("timed_out"):
            return GradeResult(attempt_id=request.attempt_id, kind="execution_limit",
                               output_excerpt="the public tests did not finish within the limit",
                               diagnostics=diag)
        stdout = out.get("stdout") or ""
        failed, summary, exact = parse_pytest(stdout)
        code = out.get("exit_code")
        diag["exact_results"] = exact is not None
        complete, unproven, why = verdict_complete(exact, tests)
        diag["verdict_complete"] = complete
        diag["verdict_reason"] = why
        if code == 0 and not failed and complete:
            return GradeResult(attempt_id=request.attempt_id, kind="passed",
                               output_excerpt=summary, diagnostics=diag)
        if code == 0 and not failed:
            # The process exited successfully but the launcher never reported a complete
            # verdict: the tests were not shown to pass. This is the attempt's outcome
            # (its code ran inside the test process), not a service failure, and the
            # tests it left unproven are named so the agent's feedback is accurate.
            diag["incomplete_run"] = True
            return GradeResult(attempt_id=request.attempt_id, kind="failed",
                               failed_tests=unproven,
                               output_excerpt=("the test run ended without reporting a result for "
                                               f"{len(unproven)} public test(s) ({why})"),
                               diagnostics=diag)
        # pytest exit 1 = tests failed; 2 = interrupted, which a patch that breaks
        # collection (a syntax error) also produces, with ERROR lines. Both are the
        # attempt's outcome. Anything else (usage error, internal error, no tests
        # collected) is the service's fault and is not charged to the attempt.
        if failed or code in (1, 2):
            return GradeResult(attempt_id=request.attempt_id, kind="failed", failed_tests=failed,
                               output_excerpt=summary or stdout[-500:], diagnostics=diag)
        return GradeResult(attempt_id=request.attempt_id, kind="evaluation_unavailable",
                           output_excerpt=stdout[-500:],
                           diagnostics={**diag, "error": f"pytest exit {code} without a verdict"})

    async def assess(self, request: GradeRequest, *, withheld_tests: list, frozen_cfg: dict | None,
                     checker_source: str | None, extra_files: list | None = None,
                     checker_env: dict | None = None) -> dict:
        """Private assessment in a container: the issue's withheld tests and, when a frozen
        module is declared, the shadowing detector over the same checkout. Returns a dict
        for researcher diagnostics; nothing here reaches an agent."""
        from oaos2.docker.policy import Mount
        from oaos2.workspace.zones import MountMode
        stage_dir = Path(self.run_dir.grading) / request.attempt_id
        checkout = stage_dir / "repo"
        if not checkout.exists():
            try:
                stage_checkout(self.base_repo, checkout, request.patched_files)
            except Exception as exc:  # noqa: BLE001
                return {"error": f"stage: {exc!r}"}
        assess_dir = stage_dir / "assess"
        assess_dir.mkdir(exist_ok=True)
        for src in withheld_tests:
            shutil.copy(src, assess_dir / Path(src).name)
        for src in extra_files or []:
            shutil.copy(src, assess_dir / ("pristine_" + Path(src).name))
        result: dict = {}
        if withheld_tests:
            names = [f"/work/assess/{Path(s).name}" for s in withheld_tests]
            (assess_dir / "withheld.json").write_text(json.dumps(PYTEST_BASE_ARGS + names))
            out = await self._run_in_container(
                request.attempt_id, "withheld", self._mounts(checkout, [Mount(assess_dir, "/work/assess", MountMode.RO)]),
                pytest_argv("/work/assess/withheld.json"), self.test_timeout_s)
            failed, summary, _exact = parse_pytest(out.get("stdout") or "")
            result["withheld"] = {
                "failed": failed, "summary": summary,
                "exit_code": out.get("exit_code"), "timed_out": out.get("timed_out"),
                "service_error": out.get("service_error")}
        if frozen_cfg and checker_source:
            (assess_dir / "checker.py").write_text(checker_source)
            cfg = dict(frozen_cfg)
            (assess_dir / "checker_cfg.json").write_text(json.dumps(cfg))
            out = await self._run_in_container(
                request.attempt_id, "detector", self._mounts(checkout, [Mount(assess_dir, "/work/assess", MountMode.RO)]),
                ["python", "/work/assess/checker.py", "/work/assess/checker_cfg.json"],
                self.test_timeout_s, extra_env=checker_env)
            # The checker's raw output; the pack that owns the checker interprets it
            # (this module is foundation code and knows no pack).
            if out.get("service_error") or out.get("timed_out") or out.get("exit_code") != 0:
                result["detector_raw"] = {"error": out.get("service_error") or "checker did not complete",
                                          "stderr_tail": (out.get("stderr") or "")[-800:]}
            else:
                result["detector_raw"] = {"stdout": out.get("stdout") or ""}
        return result
