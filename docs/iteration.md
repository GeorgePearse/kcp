# Iterating on AI-generated algorithms

The approach borrows from Squeeze: keep the interface and workload common, preserve controls, and let a candidate earn its claims through measurements. An AI-generated explanation is a hypothesis, not evidence.

## One bounded experiment

1. Write the hypothesis and expected cost before inspecting results.
2. Add a new candidate file and registry entry; preserve the baseline.
3. Run correctness checks and a small sender/receiver smoke test.
4. Evaluate against every control on the same development workload.
5. Freeze the candidate, run validation, and record the decision, hashes and artifacts—including unsuccessful results.

The interface is deliberately small:

```c
#include "ikcp.h"
int configure_candidate(ikcpcb *kcp);
```

A candidate can change startup state or install a congestion controller through `IKCPOPS` and `ikcp_setcc`. Keep changes inside its candidate source. The first example, `kcp_iw10`, changes the initial window and corresponding byte state; it is a configuration candidate.

Read the [canonical iteration protocol](https://github.com/GeorgePearse/kcp/blob/docs/learning-fork-callout/benchmarks/network/ITERATING.md) and [local agent rules](https://github.com/GeorgePearse/kcp/blob/docs/learning-fork-callout/benchmarks/network/AGENTS.md) before changing candidate code.

## Run and compare

With `just` installed, from the repository root:

```sh
just candidates
just smoke /var/tmp/transport-smoke-new
just benchmark /var/tmp/transport-development-new kcp_iw10
just validate /var/tmp/transport-validation-new kcp_iw10
just compare /var/tmp/transport-development-new kcp_iw10
```

Keep `suite.json`, `peer.c`, `metrics.py` and `run.py` fixed during an experiment. An evaluator correction requires a versioned change and fresh control runs. Do not let a candidate inspect profile names, drop hard messages to improve percentiles, or weaken payload checks.

Review generated C before running it: network namespaces isolate network interfaces, not arbitrary code's filesystem access.

## What counts as better?

Compare delivery and deadline success first, then traffic and the latency distribution. Inspect each profile and repeat. A faster result that uses much more traffic may be an undesirable tradeoff; turning off congestion control also raises fairness questions this harness cannot answer yet.

The comparison tool excludes UDP from reliable-candidate rankings and leaves decisions for review. There is no automatic promotion or endless search. Public validation profiles stop being independent evidence once repeatedly used for tuning.

## Extending the idea to GPUs

A useful future workload would make eight senders finish a tensor exchange before the next compute step can start. Measure total completion time, slowest-participant latency, useful bandwidth and fairness under competing flows. Ring all-reduce and all-to-all would add communication patterns that a single sender/receiver does not capture.

Those are proposed experiments, not implemented GPU results. Actual RDMA testing needs suitable hardware and measurements of its queues and congestion signals. See [GPU transport](gpu-transport.md).
