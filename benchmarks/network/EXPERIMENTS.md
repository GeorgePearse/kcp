# Transport experiments

## 2026-10-10 — UDP controls and startup-window experiment

Suite: `transport-v2`. Six variants, 108 development trials, 36 frozen-candidate validation trials, and six live duplication/reordering correctness trials. Development/validation use 500 messages at 100/s, three repeats, and a four-second drain. This exploratory pass used `--jobs 3`; the runner defaults to serial trials.

The v2 evaluator counts unique UDP deliveries, records duplicates/reordering, verifies sender timestamps, and enforces an exact observation cutoff. It reruns all controls; do not treat historical v1 scores as directly comparable.

Candidate: `kcp_iw10`, an AI-assisted **configuration experiment**, not a newly invented congestion algorithm. Hypothesis: increasing the initial congestion window from one to ten segments reduces startup queueing on distant links while retaining built-in congestion control. Only `cwnd` and its matching `incr` state change; the wire format, evaluator, reliability, and later ACK/loss behavior stay fixed.

Candidate SHA-256: `f53a47d5b5c45607f741b8613655f350f3e56426f99b1d3a2aaa3903280b1e57`. Candidate/evaluator/suite hashes match across development, correctness, and validation.

### Development comparison

| Profile | Baseline deadline % | Candidate deadline % | Baseline delivery % | Candidate delivery % | Candidate/baseline TX |
| --- | ---: | ---: | ---: | ---: | ---: |
| burst_loss | 20.5 | 58.1 | 100.0 | 100.0 | 1.01x |
| clean | 100.0 | 100.0 | 100.0 | 100.0 | 1.00x |
| constrained | 0.2 | 1.3 | 60.5 | 63.9 | 1.07x |
| distant | 0.2 | 100.0 | 100.0 | 100.0 | 1.11x |
| jitter_loss | 0.2 | 6.1 | 63.5 | 86.3 | 1.33x |
| outage | 24.8 | 40.1 | 100.0 | 100.0 | 1.03x |

### Validation comparison

| Profile | Baseline deadline % | Candidate deadline % | Baseline delivery % | Candidate delivery % | Candidate/baseline TX |
| --- | ---: | ---: | ---: | ---: | ---: |
| validation_delay_loss | 0.2 | 2.0 | 52.6 | 60.0 | 1.16x |
| validation_rate | 0.2 | 71.7 | 67.5 | 95.5 | 1.44x |

### Distant-link diagnosis

| Variant | Pooled p95 ms | Max queued segments across repeats |
| --- | ---: | ---: |
| kcp | 1631.6 | 163 |
| kcp_nocc | 61.1 | 1 |
| kcp_iw10 | 61.3 | 2 |

### UDP reference

| Profile | Unique delivered / offered | Within 100 ms % | Duplicate arrivals | Reordered first arrivals |
| --- | ---: | ---: | ---: | ---: |
| clean | 1500/1500 | 100.0 | 0 | 0 |
| distant | 1500/1500 | 100.0 | 0 | 0 |
| jitter_loss | 1485/1500 | 98.6 | 0 | 718 |
| burst_loss | 1458/1500 | 97.2 | 0 | 0 |
| constrained | 1440/1500 | 1.5 | 0 | 0 |
| outage | 893/1500 | 59.5 | 0 | 0 |

### Correctness and decision

Nine unit/live-UDP tests passed, including malformed payloads, sequence bounds, timestamp checks, duplicate accounting, and rejecting UDP as a reliable-candidate winner. In the dedicated netem profile UDP recorded 10 duplicate arrivals and 17 reordered first arrivals; all five reliable variants delivered all 100 messages once and in order. All completed trial receiver payload checks passed.

Decision: retain `kcp_iw10` as an experimental startup variant; do not replace the baseline. The distant-link backlog is dramatically reduced, but the jitter/loss workload still has large latency and bounded-window misses. Removing congestion control is a separate control, not an equivalent improvement. Traffic tradeoffs and repeat variation remain visible. A single flow cannot establish fairness toward other traffic.

Random loss sequences were independent and unseeded. Validation used different public parameter combinations after freezing the candidate; it is not an indefinitely reusable unseen test set. Three repeats are exploratory, not a confidence interval.

Artifacts: `gs://binit-models/analysis-reports/kcp-network-v2-20261010/report.html` (combined development/validation interactive report), `development.html`, `validation.html`, `correctness.html`, and `evidence.tar.gz` in the same prefix. The bundle retains source snapshots, trial records, KCP traces, build/network commands, and comparisons.

Rerun with `just benchmark <new-directory> kcp_iw10` and `just validate <new-directory> kcp_iw10`; see [ITERATING.md](ITERATING.md) for the full protocol.
