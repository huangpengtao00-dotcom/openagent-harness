# API and Feature Tradeoff Log

This file records features that are useful but may not be worth building before interviews.

## Keep for Later

| Item | Value | Cost / Risk | Recommendation |
|---|---|---|---|
| Real LiteLLM model calls | Enables multi-model comparison | Needs API keys, spend control, retry handling, prompt tuning | Add after local demo is stable |
| Docker sandbox | Strong reproducibility | Setup overhead on Windows; interview demos can fail if Docker is not running | Keep as P1 |
| 10+ benchmark tasks | Better evaluation story | More authoring and maintenance | Current baseline has 5 passing tasks; expand to 10 next |
| Static HTML report | Strong visual demo | Not necessary for first technical screen | Add only if applying to product-facing AI roles |
| Multi-agent mode | Trendy talking point | Scope explosion and harder failure attribution | Do not add before internship interviews |
| RAG / vector DB | Familiar AI keyword | Not central to coding-agent reliability | Skip unless job description asks for RAG |
| Browser automation | Broader agent surface | Too much unrelated complexity | Skip for now |

## API Version Design

The intended API mode is:

1. Build a compact prompt from `TaskSpec`.
2. Ask a LiteLLM-compatible model for one next action.
3. Validate action against tool policy.
4. Execute the action.
5. Append trace event with token usage and cost.
6. Stop when the model requests finalization or budget is exhausted.
7. Run the same gate as local mode.

The important point is that API mode must never bypass `QualityGate`. Natural-language confidence is not a completion signal.
