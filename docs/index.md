# Transport Lab

!!! warning "A learning fork"
    This is a slop fork for me to learn about different transport strategies.

What happens between “send this message” and “the other machine can use it”? This fork explores that question with a small, inspectable sender/receiver benchmark, then connects those ideas to distributed GPU systems.

Start with [KCP, ENet, TCP and UDP](transports.md), look at the [measured results](benchmark.md), or jump to [the hardware that moves data between GPUs](hardware.md).

## What is here?

| Question | Read |
| --- | --- |
| Why can reliable delivery make a message late? | [Transport fundamentals](transports.md) |
| How do we reproduce a bad network? | [Benchmark and results](benchmark.md) |
| Can AI propose better transport algorithms? | [The iteration workflow](iteration.md) |
| Does GPU communication still use packets? | [From tensors to packets](gpu-transport.md) |
| What actually handles acknowledgements and congestion? | [Network cards and switches](hardware.md) |

The benchmark runs real processes through an emulated network. The GPU chapters explain established designs; **we have not benchmarked GPUs or RDMA hardware in this repository**.

## The first useful finding

In a short workload with 50 ms of delay in each direction, KCP's starting congestion window caused a large sender backlog. An experimental initial window of ten segments reduced pooled p95 delivery latency from **1,631.6 ms to 61.3 ms**, with about **11% more transmitted traffic**. That is evidence about this configuration and workload, not a universal protocol ranking.

[Explore the interactive report](reports/transport-v2.html){ .md-button .md-button--primary }
[Read the measurement limits](benchmark.md#what-the-results-do-not-establish){ .md-button }

The report contains 144 development and validation trials from October 10, 2026. Six additional duplication/reordering trials checked correctness. See the [experiment ledger](https://github.com/GeorgePearse/kcp/blob/docs/learning-fork-callout/benchmarks/network/EXPERIMENTS.md) for provenance and decisions.
