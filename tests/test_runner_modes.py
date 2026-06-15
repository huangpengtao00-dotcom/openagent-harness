import json
from pathlib import Path

from openagent_harness.runner import HarnessRunner
from openagent_harness.schema import TaskSpec


def test_scripted_runner_completes_local_demo_without_api(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text(
        "def divide(a, b):\n"
        "    return a / b\n",
        encoding="utf-8",
    )
    (repo / "test_app.py").write_text(
        "from app import divide\n\n"
        "def test_divide_zero_returns_none():\n"
        "    assert divide(4, 0) is None\n",
        encoding="utf-8",
    )
    spec = TaskSpec(
        id="T-local",
        repo=str(repo),
        goal="Return None when divide receives zero denominator.",
        allowlist=["app.py"],
        acceptance=["pytest"],
        budget={"max_steps": 8},
    )

    result = HarnessRunner(mode="local").run_task(spec, tmp_path / "runs")

    assert result.gate.status == "pass"
    assert result.gate.tests_passed is True
    assert (result.run_dir / "trace.jsonl").exists()
    assert (result.run_dir / "final_report.md").exists()


def test_api_mode_records_pending_configuration_without_calling_network(tmp_path: Path) -> None:
    spec = TaskSpec(
        id="T-api",
        repo=str(tmp_path),
        goal="Fix with model",
        allowlist=["app.py"],
        acceptance=["pytest"],
        budget={"max_steps": 3},
    )

    result = HarnessRunner(mode="api", model="gpt-4.1-mini").run_task(spec, tmp_path / "runs")

    config = json.loads((result.run_dir / "api_mode.json").read_text(encoding="utf-8"))
    assert result.gate.status == "fail"
    assert result.gate.failure_type == "ApiNotConfigured"
    assert config["model"] == "gpt-4.1-mini"
    assert config["reason"] == "API mode is wired but disabled until a key and budget are approved."


def test_scripted_runner_fixes_pagination_off_by_one(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pager.py").write_text(
        "def page(items, number, size):\n"
        "    start = number * size\n"
        "    end = start + size\n"
        "    return items[start:end]\n",
        encoding="utf-8",
    )
    (repo / "test_pager.py").write_text(
        "from pager import page\n\n"
        "def test_second_page_starts_after_first_page():\n"
        "    assert page([1, 2, 3, 4, 5], 2, 2) == [3, 4]\n",
        encoding="utf-8",
    )
    spec = TaskSpec(
        id="T-pager",
        repo=str(repo),
        goal="Fix pagination off-by-one: page number is 1-based.",
        allowlist=["pager.py"],
        acceptance=["pytest"],
        budget={"max_steps": 8},
    )

    result = HarnessRunner(mode="local").run_task(spec, tmp_path / "runs")

    assert result.gate.status == "pass"
    assert "start = (number - 1) * size" in (result.run_dir / "repo" / "pager.py").read_text(encoding="utf-8")


def test_scripted_runner_fixes_invalid_cli_flag(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "cli_tool.py").write_text(
        "import sys\n\n"
        "def main(argv=None):\n"
        "    argv = list(sys.argv[1:] if argv is None else argv)\n"
        "    if '--help' in argv:\n"
        "        print('usage: cli-tool [--help]')\n"
        "        return 0\n"
        "    print('ok')\n"
        "    return 0\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n",
        encoding="utf-8",
    )
    (repo / "test_cli_tool.py").write_text(
        "from cli_tool import main\n\n"
        "def test_invalid_flag_returns_nonzero():\n"
        "    assert main(['--bad']) == 2\n",
        encoding="utf-8",
    )
    spec = TaskSpec(
        id="T-cli",
        repo=str(repo),
        goal="Invalid CLI flags should return exit code 2.",
        allowlist=["cli_tool.py"],
        acceptance=["pytest"],
        budget={"max_steps": 8},
    )

    result = HarnessRunner(mode="local").run_task(spec, tmp_path / "runs")

    assert result.gate.status == "pass"


def test_scripted_runner_fixes_invalid_cli_flag_with_double_quotes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "cli_tool.py").write_text(
        "import sys\n\n"
        "def main(argv=None):\n"
        "    argv = list(sys.argv[1:] if argv is None else argv)\n"
        "    if \"--help\" in argv:\n"
        "        print(\"usage: cli-tool [--help]\")\n"
        "        return 0\n"
        "    print(\"ok\")\n"
        "    return 0\n\n"
        "if __name__ == \"__main__\":\n"
        "    raise SystemExit(main())\n",
        encoding="utf-8",
    )
    (repo / "test_cli_tool.py").write_text(
        "from cli_tool import main\n\n"
        "def test_invalid_flag_returns_nonzero():\n"
        "    assert main(['--bad']) == 2\n",
        encoding="utf-8",
    )
    spec = TaskSpec(
        id="T-cli-double",
        repo=str(repo),
        goal="Invalid CLI flags should return exit code 2.",
        allowlist=["cli_tool.py"],
        acceptance=["pytest"],
        budget={"max_steps": 8},
    )

    result = HarnessRunner(mode="local").run_task(spec, tmp_path / "runs")

    assert result.gate.status == "pass"


def test_scripted_runner_fixes_slug_conflict(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "blog.py").write_text(
        "def create_post(existing_slugs, slug):\n"
        "    existing_slugs.add(slug)\n"
        "    return {'status': 201, 'slug': slug}\n",
        encoding="utf-8",
    )
    (repo / "test_blog.py").write_text(
        "from blog import create_post\n\n"
        "def test_slug_conflict_returns_409():\n"
        "    assert create_post({'hello'}, 'hello')['status'] == 409\n",
        encoding="utf-8",
    )
    spec = TaskSpec(
        id="T-blog",
        repo=str(repo),
        goal="Slug conflict should return 409 instead of creating a duplicate post.",
        allowlist=["blog.py"],
        acceptance=["pytest"],
        budget={"max_steps": 8},
    )

    result = HarnessRunner(mode="local").run_task(spec, tmp_path / "runs")

    assert result.gate.status == "pass"


def test_scripted_runner_fixes_csv_encoding_cleanup(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "csv_cleaner.py").write_text(
        "def clean_cell(value):\n"
        "    return value.strip()\n",
        encoding="utf-8",
    )
    (repo / "test_csv_cleaner.py").write_text(
        "from csv_cleaner import clean_cell\n\n"
        "def test_clean_cell_removes_utf8_bom():\n"
        "    assert clean_cell('\\ufeffname') == 'name'\n",
        encoding="utf-8",
    )
    spec = TaskSpec(
        id="T-csv",
        repo=str(repo),
        goal="CSV cleaner should remove UTF-8 BOM from cells.",
        allowlist=["csv_cleaner.py"],
        acceptance=["pytest"],
        budget={"max_steps": 8},
    )

    result = HarnessRunner(mode="local").run_task(spec, tmp_path / "runs")

    assert result.gate.status == "pass"


def test_runner_patch_includes_out_of_scope_file_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def ok():\n    return False\n", encoding="utf-8")
    (repo / "secrets.txt").write_text("original\n", encoding="utf-8")

    runner = HarnessRunner(mode="local")
    before = runner._snapshot(repo)
    (repo / "app.py").write_text("def ok():\n    return True\n", encoding="utf-8")
    (repo / "secrets.txt").write_text("changed\n", encoding="utf-8")
    after = runner._snapshot(repo)

    patch_path = tmp_path / "patch.diff"
    runner._write_patch(patch_path, before, after)

    patch = patch_path.read_text(encoding="utf-8")
    assert "diff --git a/app.py b/app.py" in patch
    assert "diff --git a/secrets.txt b/secrets.txt" in patch


def test_runner_uses_custom_acceptance_command(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text(
        "def divide(a, b):\n"
        "    return a / b\n",
        encoding="utf-8",
    )
    (repo / "check_custom.py").write_text(
        "from app import divide\n"
        "assert divide(4, 0) is None\n",
        encoding="utf-8",
    )
    spec = TaskSpec(
        id="T-custom-acceptance",
        repo=str(repo),
        goal="Return None when divide receives zero denominator.",
        allowlist=["app.py"],
        acceptance=["python check_custom.py"],
        budget={"max_steps": 8},
    )

    result = HarnessRunner(mode="local").run_task(spec, tmp_path / "runs")
    test_result = json.loads((result.run_dir / "test_result.json").read_text(encoding="utf-8"))

    assert result.gate.status == "pass"
    assert test_result["commands"] == ["python check_custom.py"]
