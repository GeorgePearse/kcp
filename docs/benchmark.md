# Benchmark and results

We run a sender and receiver through Linux network namespaces, with `tc netem` introducing impairments in both directions:

```text
sender process → virtual link → router → virtual link → receiver process
                                 ↑
                         delay, loss, rate limit
```

This exercises real sockets and protocol implementations. The router is isolated from the host's normal network interfaces. Netem supports UDP and TCP, which is why it fits this comparison; [Toxiproxy](https://github.com/Shopify/toxiproxy) is a TCP proxy and would not directly exercise the UDP transports. See the [netem manual](https://man7.org/linux/man-pages/man8/tc-netem.8.html).

## Reproduce a run

Run from a Linux checkout with root privileges for network namespace setup:

```sh
sudo apt-get install build-essential libenet-dev iproute2 ethtool iputils-ping pkg-config
sudo python3 benchmarks/network/run.py \
  --out /var/tmp/transport-smoke \
  --profiles clean --count 50 --repeats 1 --candidates kcp_iw10
PEER_BINARY=/var/tmp/transport-smoke/peer \
  python3 -m unittest discover -s benchmarks/network -p 'test_*.py'
```

Always choose a fresh output directory. For full development and validation runs, use the commands in the [iteration guide](iteration.md). The [canonical benchmark README](https://github.com/GeorgePearse/kcp/blob/docs/learning-fork-callout/benchmarks/network/README.md) documents exact configuration, installation and outputs.

## What stays fixed?

The `transport-v2` workload sends 500 messages of 256 bytes at 100 messages/second, followed by a four-second drain. That is 204.8 kbit/s of offered application payload. Five controls—UDP, KCP, KCP with congestion control disabled, ENet and TCP—run alongside a registered candidate.

Latency is measured from **scheduled send time to application delivery**, so sender queueing counts. All endpoints share the host's monotonic clock. The deadline is 100 ms. Delivery and deadline percentages use all offered messages as the denominator; latency percentiles include only messages delivered within the observation window. A missing message can still be queued rather than permanently lost.

Both endpoint TX counters count traffic including acknowledgements and retries. These are interface counters in an emulated network, not physical-wire byte measurements.

| Development profile | Impairment in each direction |
| --- | --- |
| Clean | 2 ms delay |
| Distant | 50 ms delay, approximately 100 ms base RTT |
| Jitter/loss | 50 ms delay, 20 ms jitter, 1% random loss |
| Burst loss | 20 ms delay and alternating good/bad loss states |
| Constrained | 20 ms delay, 128 kbit/s—below the offered payload rate |
| Outage | 20 ms delay with roughly two seconds of complete loss |

Separate profiles test duplication/reordering and different validation conditions. See [suite.json](https://github.com/GeorgePearse/kcp/blob/docs/learning-fork-callout/benchmarks/network/suite.json) for exact parameters.

## Why was KCP so slow on the distant link?

The trace showed a small initial congestion window and a growing sender backlog. This short workload includes startup: there is no warm-up. The `kcp_iw10` candidate starts with ten segments instead of one and otherwise keeps the built-in congestion controller.

| Variant | Pooled p95 latency | Largest observed sender queue |
| --- | ---: | ---: |
| KCP baseline | 1,631.6 ms | 163 segments |
| KCP, congestion control disabled | 61.1 ms | 1 segment |
| KCP, initial window ten | 61.3 ms | 2 segments |

The initial-window candidate transmitted about 11% more traffic than the baseline in this profile. This is a **configuration experiment**, not a newly invented congestion-control algorithm. It remains experimental: in development jitter/loss trials, only 6.1% of its offered messages met the deadline and 86.3% arrived within the observation window.

## Why include UDP?

During the outage trials, UDP delivered 893 of 1,500 offered messages. Its surviving messages could arrive quickly because there was no recovery queue. Reporting only their latency would hide the missing 607 messages.

The dedicated duplication/reordering check recorded 10 duplicate UDP arrivals and 17 reordered first arrivals. All five reliable variants delivered 100/100 messages once and in order in that check.

[Open the interactive results](reports/transport-v2.html){ .md-button .md-button--primary }

The report preserves the original 144 development/validation trials and browser controls. The [experiment ledger](https://github.com/GeorgePearse/kcp/blob/docs/learning-fork-callout/benchmarks/network/EXPERIMENTS.md) records the additional six correctness trials, candidate hash, traffic tradeoffs and retained artifact locations. Documentation publication did not rerun these experiments.

## What the results do not establish

The October 10, 2026 pilot used three repeats and three concurrent trials sharing CPU resources; the runner defaults to serial execution. Random loss was unseeded: the settings are reproducible, exact packet outcomes are not. Three repeats do not establish statistical confidence.

We have not measured competing-flow fairness, CPU/memory cost, encrypted transports, or real GPU/RDMA performance. The short test includes startup and is not a sustained-throughput benchmark. Historical v1 and v2 results use different evaluator rules and should not be directly ranked against each other.
