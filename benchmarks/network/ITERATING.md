# Iterating on transport algorithms

The model is the same as Squeeze's algorithm experiments: keep a common workload and interface, retain baselines, and compare several quality/cost metrics. An AI proposes and implements a hypothesis; the benchmark evaluates it. A model's explanation is not performance evidence.

## Fixed evaluation contract

`suite.json` versions the workload, network profiles, observation window, deadline, and upstream KCP source hashes. `metrics.py`, `peer.c`, and `run.py` are the evaluator. Keep these fixed during an algorithm experiment. If they need a correction, version the suite/evaluator and rerun all controls. Do not compare historical v1 and v2 numbers as if their observation-window rules were identical.

Five controls are available: `udp`, `kcp`, `kcp_nocc`, `enet`, and `tcp`. UDP is a best-effort reference and cannot enter the reliable-candidate comparison. `kcp_nocc` is explicitly labeled because removing congestion control changes behavior toward competing traffic; this single-flow benchmark does not measure that fairness.

The default workload is 500 messages of 256 bytes at 100/s, then a four-second drain. Use the fixed `development` split for iteration. `validation` contains two different parameter combinations: a longer, mildly lossy path and a link with bandwidth closer to the offered load. Freeze the candidate before inspecting validation. Once repeatedly tuned against, that split is no longer independent validation; version a new suite when needed. These are public parameter splits, not secret held-out data.

## Candidate interface

Add a C file in `candidates/` implementing:

```c
#include "ikcp.h"
int configure_candidate(ikcpcb *kcp);
```

It runs after the common KCP configuration at both endpoints and returns zero on success. It can adjust startup state or install an `IKCPOPS` controller with `ikcp_setcc`. The current KCP interface offers callbacks for acknowledgements, RTT samples, retransmissions, timeouts, ticks, and pacing. Keep callbacks and state in the candidate file. A changed wire format or new transport needs a separately versioned adapter/experiment, not silent changes to the baseline.

Register an ID, relative C source path, hypothesis, kind, author, and experimental status in `candidates/registry.json`. Use a new ID/source for each substantive candidate so earlier hypotheses remain inspectable. Candidates are compiled separately against the unchanged KCP source. `kcp_iw10` demonstrates the interface: it starts with ten segments in flight and otherwise keeps built-in congestion control. It is a configuration experiment, not a novel congestion algorithm.

The receiver, payload, schedule, observation window, and accounting are fixed. Candidate code must not change them, inspect profile names to choose an answer, or bypass correctness checks. Review generated C before executing it: network namespaces isolate the test network, not arbitrary code's filesystem access.

## One bounded iteration

1. Write one hypothesis and its expected tradeoff in the registry.
2. Implement the candidate in its own file.
3. Run correctness tests and a short live smoke test.
4. Compare with every control under the same development suite; inspect per-profile results and repeat variation.
5. Freeze the source, run validation, and record the decision and artifact path in `EXPERIMENTS.md`. Keep unsuccessful candidates/results too.

```sh
python3 -m unittest discover -s benchmarks/network -p 'test_*.py'
sudo python3 benchmarks/network/run.py --out /var/tmp/transport-smoke \
  --profiles clean --count 50 --repeats 1 --candidates kcp_iw10
PEER_BINARY=/var/tmp/transport-smoke/peer \
  python3 -m unittest discover -s benchmarks/network -p 'test_*.py'

sudo python3 benchmarks/network/run.py --out /var/tmp/transport-correctness \
  --split correctness --count 100 --repeats 1 --candidates kcp_iw10
sudo python3 benchmarks/network/run.py --out /var/tmp/transport-development \
  --candidates kcp_iw10
sudo python3 benchmarks/network/run.py --out /var/tmp/transport-validation \
  --split validation --candidates kcp_iw10
python3 benchmarks/network/compare.py /var/tmp/transport-development \
  --candidate kcp_iw10
```

The default is one trial at a time to reduce CPU interference. `--jobs 3` makes a quicker exploratory pass but must be recorded. For sustained behavior, repeat with `--count 3000`; this is a different workload and must be compared with freshly rerun controls. There is no automatic endless search or automatic promotion.

## What counts as improvement?

Look at delivery rate and deadline success first, then traffic consumption and the latency distribution. A candidate that drops difficult messages must not appear faster because its latency percentiles only include successes. A candidate that floods the link may improve a deadline score at an unacceptable traffic cost. Keep all profile-level tradeoffs visible rather than inventing one score that hides them.

`compare.py` only compares reliable variants inside the same run, checks matching profiles/repeats/offered counts, and emits deadline/delivery changes in percentage points, traffic ratios, and per-repeat variation. Decisions remain `review_only`. The harness does not yet measure competing-flow fairness, CPU cost, memory limits, encryption, or Internet deployment behavior; a favorable local result is an experimental candidate, not a production recommendation.

The host's netem version does not support seeded loss in this setup. Random loss sequences are independent across trials: source/workload/profile provenance is reproducible, but exact packet outcomes are not. Three repeats are a pilot, not a confidence interval. Source hashes, raw records, compiler/library versions, and KCP queue/window traces are saved automatically.
