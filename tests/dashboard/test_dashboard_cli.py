"""The optional port flag must not replace the optional archive directory."""
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.dashboard import main


@pytest.mark.parametrize("argv,root,port", [([], "runs", 8722),
                                            (["--port", "9000"], "runs", 9000),
                                            (["other", "--port", "9000"], "other", 9000),
                                            (["--port", "9000", "other"], "other", 9000)])
def test_cli_resolves_directory_and_port_without_starting_server(tmp_path, monkeypatch, argv, root, port):
    monkeypatch.chdir(tmp_path)
    (tmp_path / root).mkdir()
    app_factory = Mock(return_value="app")
    server = Mock()
    monkeypatch.setattr("oaos2.dashboard.app.create_app", app_factory)
    monkeypatch.setattr("uvicorn.run", server)
    assert main(argv) == 0
    app_factory.assert_called_once_with(Path(root))
    server.assert_called_once_with("app", host="127.0.0.1", port=port, log_level="warning")
