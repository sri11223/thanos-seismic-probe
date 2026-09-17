# thanos-quality-probe (private)

Cloud pipeline that runs the Thanos difficulty gate for a Harbor task on GitHub Actions.

## What it does
1. **validate**: builds the task in Docker, runs the oracle (must pass, reward 1.0) and NOP (must fail).
2. **probe**: 8 parallel rollouts with the gate model (`tencent/hy4-preview`) via OpenRouter, one per matrix slot.
3. **aggregate**: computes pass@8 and median assistant turns, writes `verdict.json`.

## Target band
- Difficulty: 1-2 of 8 passing (accept 1-6).
- Long horizon: median assistant turns > 80.

## Run it
Actions tab -> `thanos-quality-probe` -> Run workflow. Requires repo secret `OPENROUTER_API_KEY`.
