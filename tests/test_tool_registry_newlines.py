from pathlib import Path

from openagent_harness.policy import PermissionPolicy
from openagent_harness.tool_registry import LocalToolRegistry


def test_edit_file_preserves_lf_newlines(tmp_path: Path) -> None:
    target = tmp_path / "http_client.py"
    target.write_bytes(b"RETRYABLE_STATUSES = {500, 502, 503, 504}\n\ndef f():\n    return 1\n")
    registry = LocalToolRegistry(tmp_path, PermissionPolicy(tmp_path, ["http_client.py"]))

    result = registry.dispatch(
        "edit_file",
        {
            "path": "http_client.py",
            "old_text": "RETRYABLE_STATUSES = {500, 502, 503, 504}",
            "new_text": "RETRYABLE_STATUSES = {429, 500, 502, 503, 504}",
        },
    )

    assert result.ok is True
    data = target.read_bytes()
    assert b"{429, 500" in data
    assert b"\r\n" not in data


def test_edit_file_accepts_lf_anchor_but_preserves_crlf_file(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_bytes(b"def f():\r\n    return 1\r\n")
    registry = LocalToolRegistry(tmp_path, PermissionPolicy(tmp_path, ["app.py"]))

    result = registry.dispatch(
        "edit_file",
        {
            "path": "app.py",
            "old_text": "def f():\n    return 1",
            "new_text": "def f():\n    return 2",
        },
    )

    assert result.ok is True
    assert target.read_bytes() == b"def f():\r\n    return 2\r\n"
