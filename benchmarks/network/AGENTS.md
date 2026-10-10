# Transport experiment rules

- Read `ITERATING.md` before proposing or changing an algorithm.
- Put experimental behavior in a new registered `candidates/*.c` implementation of `configure_candidate`. Preserve baseline `ikcp.c` and `ikcp.h`.
- Record the hypothesis and expected tradeoff before inspecting results. Label parameter changes as configuration experiments, not novel algorithms.
- Keep the evaluator (`peer.c`, `metrics.py`, `run.py`, `suite.json`) fixed during a candidate experiment. Evaluator corrections require rerunning controls and distinguishing the new results from old runs.
- Do not weaken payload checks, change scheduled timestamps, drop difficult messages to improve latency percentiles, or specialize candidate behavior using knowledge of test profile names.
- For candidate changes, run correctness tests, the real sender/receiver smoke, development profiles, and validation after freezing the candidate. Retain source hashes and unsuccessful results.
- Use delivery and deadline success with traffic consumption; UDP is a best-effort reference, never a reliable-delivery winner.
- Keep the experiment bounded and record its decision in `EXPERIMENTS.md`. Do not silently promote a candidate, merge, or launch an indefinite search.
