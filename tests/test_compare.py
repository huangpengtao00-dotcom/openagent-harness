import json
from pathlib import Path

from openagent_harness.compare import CompareSummary, load_profiles, run_compare


def _write_calc_task(root: Path) -> None:
    task_dir = root / "benchmarks" / "calc-py"
    repo = task_dir / "repo"
    repo.mkdir(parents=True)
    (repo / "app.py").write_text("def divide(a, b):\n    return a / b\n", encoding="utf-8")
    (repo / "test_app.py").write_text(
        "from app import divide\n\n"
        "def test_divide_zero_returns_none():\n"
        "    assert divide(4, 0) is None\n",
        encoding="utf-8",
    )
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "id": "T1-calc-div-zero",
                "repo": "benchmarks/calc-py/repo",
                "goal": "Return None when divide receives zero denominator.",
                "allowlist": ["app.py"],
                "acceptance": ["pytest"],
                "budget": {"max_steps": 8},
            }
        ),
        encoding="utf-8",
    )


def _write_profiles(root: Path) -> Path:
    path = root / "profiles.json"
    path.write_text(
        json.dumps(
            {
                "profiles": [
                    {"name": "scripted-baseline", "mode": "local", "model": "scripted"},
                    {
                        "name": "api-placeholder",
                        "mode": "api",
                        "model": "gpt-5.5",
                        "base_url": "https://example.test/v1",
                        "api_key_env": "MISSING_TEST_KEY",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_load_profiles_keeps_key_material_out_of_public_dict(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MODEL_KEY_FOR_TEST", "sk-test-secret-value")
    path = tmp_path / "profiles.json"
    path.write_text(
        json.dumps(
            [
                {
                    "name": "gpt-5.5",
                    "mode": "api",
                    "model": "gpt-5.5",
                    "api_key_env": "MODEL_KEY_FOR_TEST",
                }
            ]
        ),
        encoding="utf-8",
    )

    profile = load_profiles(path)[0]
    public = profile.to_public_dict()

    assert public["api_key_env"] == "MODEL_KEY_FOR_TEST"
    assert public["api_key_configured"] is True
    assert "sk-test-secret-value" not in json.dumps(public)


def test_run_compare_writes_matrix_summary_and_html(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MISSING_TEST_KEY", raising=False)
    _write_calc_task(tmp_path)
    profiles = _write_profiles(tmp_path)

    summary = run_compare(
        tmp_path / "benchmarks",
        profiles,
        tmp_path / "runs_compare",
        project_root=tmp_path,
        parallel=2,
        allow_llm_calls=False,
    )

    assert isinstance(summary, CompareSummary)
    assert summary.total_tasks == 1
    assert summary.total_runs == 2
    assert {item.profile for item in summary.results} == {"scripted-baseline", "api-placeholder"}
    assert (tmp_path / "runs_compare" / "comparison_summary.json").exists()
    assert (tmp_path / "runs_compare" / "comparison_report.html").exists()

    data = json.loads((tmp_path / "runs_compare" / "comparison_summary.json").read_text(encoding="utf-8"))
    assert data["profile_summaries"][0]["profile"] == "api-placeholder"
    assert len(data["results"]) == 2
    assert "sk-" not in json.dumps(data)
