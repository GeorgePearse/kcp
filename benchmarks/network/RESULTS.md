# Local sender/receiver results — 2026-10-10

Exploratory pilot: 54 trials, three repeats of each transport/profile pair, 500 messages per trial at 100 messages/s, 256 bytes each, plus a four-second drain. See [methodology and settings](README.md).

Numbers below are pooled p95 one-way application delivery latency in milliseconds. Parentheses show delivered / offered messages across the three repeats. Missing messages are excluded from latency percentiles but count against delivery and deadline success.

| Profile | KCP | ENet | TCP |
| --- | --- | --- | --- |
| clean | 13.3 (1500/1500) | 3.9 (1500/1500) | 3.8 (1500/1500) |
| distant | 1631.7 (1500/1500) | 51.8 (1500/1500) | 51.7 (1500/1500) |
| jitter_loss | 5354.0 (1036/1500) | 433.1 (1500/1500) | 152.1 (1500/1500) |
| burst_loss | 1040.9 (1500/1500) | 362.3 (1500/1500) | 22.0 (1500/1500) |
| constrained | 5928.4 (844/1500) | 4433.4 (1338/1500) | 3589.3 (1500/1500) |
| outage | 2591.4 (1500/1500) | 2147.4 (1500/1500) | 3738.3 (1500/1500) |

All received payloads and ordering checks passed. All temporary network namespaces were removed after the run.

This is a short run from freshly established connections, not a steady-state throughput test. KCP uses congestion control (`nc=0`); these results must not be generalized to its congestion-control-disabled mode or other tuning. The randomized profiles use independent, unseeded loss sequences, and three concurrent trials share the host CPU. There is no universal winner implied by this table.

Environment: 5.10.0-46-cloud-amd64, ENet 1.3.13, cc (Debian 10.2.1-6) 10.2.1 20210110. Source hashes and the exact tested source snapshot are retained with the artifacts.

Artifacts: `gs://binit-models/analysis-reports/kcp-network-20261010/report.html` and `gs://binit-models/analysis-reports/kcp-network-20261010/evidence.tar.gz` (authenticated access; temporary signed links can be generated). The interactive report includes the 100 ms delivery deadline metric and per-repeat latency curves.
