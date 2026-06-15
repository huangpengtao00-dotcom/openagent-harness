from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .runner import HarnessRunner
from .scoring import RunScorecard, score_run
from .schema import TaskSpec


@dataclass(frozen=True)
class CandidateResult:
    name: str
    run_id: str
    run_dir: str
    scorecard: RunScorecard

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["scorecard"] = self.scorecard.to_dict()
        return data


@dataclass(frozen=True)
class PortfolioResult:
    best: CandidateResult | None
    candidates: list[CandidateResult]

    def to_dict(self) -> dict[str, object]:
        return {
            "best": self.best.to_dict() if self.best else None,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


class PortfolioRunner:
    """Run multiple agent candidates and select the strongest verified patch.

    In offline demos this is still useful: it creates the same selection/evidence surface used by
    expensive LLM runs, without requiring real API spend.
    """

    def __init__(self, candidate_modes: list[str] | None = None) -> None:
        self.candidate_modes = candidate_modes or ["local"]

    def run(self, spec: TaskSpec, runs_root: Path) -> PortfolioResult:
        runs_root.mkdir(parents=True, exist_ok=True)
        candidates: list[CandidateResult] = []
        for index, mode in enumerate(self.candidate_modes, start=1):
            candidate_root = runs_root / f"candidate_{index}_{mode}"
            result = HarnessRunner(mode="local" if mode == "local" else "api").run_task(spec, candidate_root)
            scorecard = score_run(result.run_dir, result.gate)
            candidates.append(CandidateResult(mode, result.run_id, str(result.run_dir), scorecard))
        best = sorted(candidates, key=lambda c: (c.scorecard.score, c.scorecard.status == "pass"), reverse=True)[0] if candidates else None
        portfolio = PortfolioResult(best=best, candidates=candidates)
        (runs_root / "portfolio_summary.json").write_text(json.dumps(portfolio.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return portfolio
