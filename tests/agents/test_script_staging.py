"""Host script staging refuses pre-existing paths without opening them."""
import os
from types import SimpleNamespace

import pytest

from oaos2.agents.tools import ToolContext, dispatch_tool
from oaos2.docker.backend import FakeContainerBackend, ContainerHandle
from oaos2.docker.isolation import IsolationViolation
from oaos2.kernel.run_dir import RunDir
from oaos2.trace.spine import RunSpine
from oaos2.workspace.monitor import WorkspaceManager


@pytest.mark.parametrize("existing", ["symlink", "hardlink", "file", "fifo", "parent_symlink", None])
async def test_script_creation_never_opens_preexisting_path(tmp_path, existing):
    rd = RunDir.create(tmp_path, "e", "p", "r")
    spine = RunSpine(rd.root, "r")
    await spine.start()
    scratch = rd.ensure_agent_scratch("a")
    target = tmp_path / "original.txt"
    target.write_text("original")
    path = scratch / "_exec_1.py"
    if existing == "symlink":
        path.symlink_to(target)
    elif existing == "hardlink":
        os.link(target, path)
    elif existing == "file":
        path.write_text("existing")
    elif existing == "fifo":
        os.mkfifo(path)
    elif existing == "parent_symlink":
        scratch.rmdir()
        scratch.symlink_to(tmp_path, target_is_directory=True)
    rs = SimpleNamespace(spine=spine, workspace=WorkspaceManager(rd, spine))
    ctx = ToolContext("a", rs, FakeContainerBackend(),
                      ContainerHandle("a", "fake", "sha256:fake", rd.container_mount),
                      rd, None, "final")
    try:
        if existing:
            with pytest.raises(IsolationViolation):
                await dispatch_tool("run_python", {"code": "print('hello')"}, ctx,
                                    turn_id="t", caused_by=None)
            assert target.read_text() == "original"
            if existing == "parent_symlink":
                assert not (tmp_path / "_exec_1.py").exists()
        else:
            result = await dispatch_tool("run_python", {"code": "print('hello')"}, ctx,
                                         turn_id="t", caused_by=None)
            assert "exit_code=0" in result.text
            assert path.read_text() == "print('hello')"
    finally:
        await spine.finalize("failed" if existing else "completed")
