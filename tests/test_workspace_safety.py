from pathlib import Path

from openagent_harness.context import ContextBuilder
from openagent_harness.workspace import WorkspaceManager


def test_workspace_manager_excludes_secrets_databases_and_runtime_outputs(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (source / ".env").write_text("DEEPSEEK_API_KEY=secret\n", encoding="utf-8")
    (source / ".env.staging").write_text("OPENAI_API_KEY=secret\n", encoding="utf-8")
    (source / "venv").mkdir()
    (source / "venv" / "pyvenv.cfg").write_text("home = C:/Python313\n", encoding="utf-8")
    (source / "openagent.db").write_text("sqlite-bytes", encoding="utf-8")
    (source / "artifacts").mkdir()
    (source / "artifacts" / "report.html").write_text("<html></html>\n", encoding="utf-8")
    (source / "runs_deepseek").mkdir()
    (source / "runs_deepseek" / "trace.jsonl").write_text("{}\n", encoding="utf-8")
    (source / "runs_deepseek_smoke").mkdir()
    (source / "runs_deepseek_smoke" / "deepseek_smoke.json").write_text("{}\n", encoding="utf-8")

    workspace = WorkspaceManager().create(source, tmp_path / "isolated")

    assert (workspace.path / "app.py").exists()
    assert not (workspace.path / ".env").exists()
    assert not (workspace.path / ".env.staging").exists()
    assert not (workspace.path / "venv").exists()
    assert not (workspace.path / "openagent.db").exists()
    assert not (workspace.path / "artifacts").exists()
    assert not (workspace.path / "runs_deepseek").exists()
    assert not (workspace.path / "runs_deepseek_smoke").exists()


def test_context_builder_skips_secret_and_runtime_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def ok():\n    return True\n", encoding="utf-8")
    (repo / ".env").write_text("OPENAI_API_KEY=secret\n", encoding="utf-8")
    (repo / ".env.secret").write_text("DEEPSEEK_API_KEY=secret\n", encoding="utf-8")
    (repo / "venv").mkdir()
    (repo / "venv" / "pyvenv.cfg").write_text("home = C:/Python313\n", encoding="utf-8")
    (repo / "artifacts").mkdir()
    (repo / "artifacts" / "report.html").write_text("<html></html>\n", encoding="utf-8")
    (repo / "runs").mkdir()
    (repo / "runs" / "trace.jsonl").write_text("{}\n", encoding="utf-8")
    (repo / "runs_deepseek_smoke").mkdir()
    (repo / "runs_deepseek_smoke" / "deepseek_smoke.json").write_text("{}\n", encoding="utf-8")

    index = ContextBuilder(repo).build_index("check app behavior")
    indexed_paths = {item.path for item in index.files}

    assert "app.py" in indexed_paths
    assert ".env" not in indexed_paths
    assert ".env.secret" not in indexed_paths
    assert "venv/pyvenv.cfg" not in indexed_paths
    assert "artifacts/report.html" not in indexed_paths
    assert "runs/trace.jsonl" not in indexed_paths
    assert "runs_deepseek_smoke/deepseek_smoke.json" not in indexed_paths
    assert ".env" not in index.skipped
    assert ".env.secret" not in index.skipped
    assert "artifacts/report.html" not in index.skipped
