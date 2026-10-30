"""A clean stop for a live run (the PI, October 21, 2026).

A first SIGINT or SIGTERM to a launcher asks the run to stop: the runner records
``run.stop_requested``, every agent is retired at its next action boundary and makes no new
model call, the task's procedure ends its work period, and the run finalizes, writes its
archive and removes its containers as at a normal end. A second signal forces the process
to exit at once; its archive may then be incomplete and its containers left running.

Before this, ``asyncio.run`` turned a first Ctrl-C into a cancellation that the materials-lab
pool's own finalization outlived, so a PC1 run interrupted with ``kill -INT`` went on to its
scheduled end (October 21, 2026: four of five runs).
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys

FORCED_EXIT_CODE = 130


class RunStop:
    """A stop request a launcher passes to ``run_org_live(stop=...)``."""

    def __init__(self) -> None:
        self.requested = asyncio.Event()
        self.signal_name: str | None = None

    @property
    def is_requested(self) -> bool:
        return self.requested.is_set()

    def request(self, signal_name: str = "request") -> bool:
        """Ask the run to stop; True on the first request, False when one was already made."""
        if self.requested.is_set():
            return False
        self.signal_name = signal_name
        self.requested.set()
        return True


def install_signal_stop(stop: RunStop, loop: asyncio.AbstractEventLoop | None = None,
                        *, out=sys.stderr, force_exit=os._exit) -> None:
    """Route SIGINT and SIGTERM to ``stop``: the first asks for a clean stop, a second forces an exit."""
    loop = loop or asyncio.get_running_loop()

    def handle(signum: int) -> None:
        name = signal.Signals(signum).name
        if stop.request(name):
            print(f"\n{name}: stopping the run cleanly (the work period ends, the archive is written and the "
                  "containers removed). Send it again to force an exit.", file=out, flush=True)
            return
        print(f"\n{name} again: forcing an exit. The archive may be incomplete; find leftover containers by "
              "their oaos2.mount_root label.", file=out, flush=True)
        force_exit(FORCED_EXIT_CODE)

    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, handle, signum)
