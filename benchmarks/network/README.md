# Transport algorithm benchmark

Run real UDP, KCP, ENet, and TCP sender/receiver processes through controlled network impairments:

```text
sender namespace <-- veth --> router namespace <-- veth --> receiver namespace
                             netem both ways
```

The [iteration workflow](ITERATING.md) explains how to register and evaluate AI-assisted algorithm candidates against fixed controls, following Squeeze's common-workload/common-interface approach. [EXPERIMENTS.md](EXPERIMENTS.md) records decisions and results. The [original three-transport pilot](RESULTS.md) remains as historical evidence.

## Run

Requires Linux, root access for network namespaces, Python 3, a C compiler, and ENet headers. On Debian/Ubuntu:

```sh
sudo apt-get install build-essential libenet-dev iproute2 ethtool iputils-ping pkg-config
sudo python3 benchmarks/network/run.py --out /var/tmp/transport-results
```

Use a new output directory for every run. Defaults: five controls, six development profiles, three repeats, one trial at a time. Include the first candidate with `--candidates kcp_iw10`. If `just` is installed, `just candidates`, `just smoke /var/tmp/transport-smoke`, and `just benchmark /var/tmp/transport-results` provide shortcuts.

```sh
sudo python3 benchmarks/network/run.py --out /var/tmp/transport-smoke \
  --profiles clean --repeats 1 --count 50 --candidates kcp_iw10
PEER_BINARY=/var/tmp/transport-smoke/peer \
  python3 -m unittest discover -s benchmarks/network -p 'test_*.py'
```

Each run produces a standalone `report.html`, per-message CSVs, process logs, network commands, interface counters, netem statistics, source snapshots/hashes, build commands, and candidate comparisons. KCP senders also write `kcp-trace.csv`: congestion window, queued/in-flight segments, RTT estimate, timeout, and timeout retransmission count. Open the report directly in a browser; it has no external assets.

## Variants

| ID | Delivery contract | Configuration |
| --- | --- | --- |
| `udp` | Best effort; gaps, duplicates and reordering allowed | Plain UDP messages; no ACK/retry layer |
| `kcp` | Reliable, ordered messages | `nodelay=1`, interval 10 ms, fast retransmit 2, congestion control **enabled** |
| `kcp_nocc` | Reliable, ordered messages | Same KCP settings, congestion control **disabled** (`nc=1`) |
| `enet` | Reliable, ordered messages | One reliable channel, default reliability/congestion settings |
| `tcp` | Reliable, ordered byte stream | CUBIC, `TCP_NODELAY`, fixed 256-byte message framing |
| `kcp_iw10` | Experimental reliable, ordered messages | Built-in KCP congestion control with initial window of ten segments |

KCP windows are 128 segments; KCP and ENet MTU is 1200. All variants are unencrypted and use a 1 ms application service loop. Library/compiler versions are recorded. The registered candidate uses the same adapter and upstream KCP source as the controls; it does not modify the baseline files.

## Workload and measurement

The versioned `suite.json` specifies 500 messages of 256 bytes every 10 ms: 100/s or 204.8 kbit/s of application data, followed by a four-second drain. TCP/ENet connect before impairment; KCP/UDP are initialized before sending. There is no warm-up, so initial window growth is included.

Latency starts at the scheduled send time and ends at application delivery, including sender queueing/backpressure. The shared host monotonic clock avoids clock synchronization error. The scoring cutoff is exactly `sender_start + count * interval + drain`; raw CSV retains later arrivals but they receive no delivery credit. CSV starts with a `READY` marker followed by `sequence,scheduled_send_us,received_us` rows.

Every received message is checked for payload integrity and sequence bounds. Reliable modes must deliver in order without duplicates; a violation fails the run. UDP is allowed to arrive with gaps, duplicates, and reordering. Only the first arrival of each sequence earns delivery/deadline credit. The report separately counts duplicate arrivals and first arrivals below the highest sequence already seen.

Deadline success uses **all offered messages** as its denominator. Latency percentiles include only messages delivered within the observation window, pooled across repeats. Missing messages may still be queued rather than permanently lost. UDP is a reference and cannot be selected as a reliable candidate in `compare.py`.

Combined endpoint TX counters include protocol headers, retransmissions, ACKs, and link headers after connection setup. They count bytes injected into the emulated path, including packets later dropped; they are not physical-wire measurements. The displayed ratio is relative to all offered application bytes.

## Profiles and isolation

Both router egress interfaces get the same settings independently. A 50 ms one-way delay adds about 100 ms RTT before queueing. TSO/GSO/GRO are disabled on all virtual interfaces. No impairment is applied to the host's normal interfaces. Every trial uses fresh namespaces; they are removed on completion or exception. SIGKILL/host failure may require manual removal of remaining `kb...` namespaces.

| Development profile | Per-direction impairment |
| --- | --- |
| `clean` | 2 ms delay |
| `distant` | 50 ms delay |
| `jitter_loss` | 50 ms delay, 20 ms normal-distribution jitter, 1% random loss |
| `burst_loss` | 20 ms delay; Gilbert–Elliott model: 1% entry to bad state, 25% exit, 80% bad-state loss, 0% good-state loss |
| `constrained` | 20 ms delay, 128 kbit/s, below the offered application load |
| `outage` | 20 ms delay; approximately two seconds of 100% loss starting two seconds after GO |

The queue limit is 10,000 packets. Outage queue replacement can discard queued packets; exact transition times are saved. `--split correctness` adds deliberate duplication/reordering. `--split validation` runs different delay/loss and bandwidth settings after a candidate is frozen. All definitions are in `suite.json`.

These are synthetic profiles, not real mobile/Wi-Fi traces. Random loss is unseeded on this host: settings are repeatable, individual packet outcomes are not. `--jobs 3` permits concurrent trials sharing CPU resources; default serial execution reduces that interference. `--count 3000` provides a longer startup-plus-sustained run, but requires rerunning controls under that workload. This harness does not yet measure competing-flow fairness, CPU/memory cost, QUIC, SCTP, or SRT.

References: [netem manual](https://man7.org/linux/man-pages/man8/tc-netem.8.html), [ENet](https://github.com/lsalzman/enet).
