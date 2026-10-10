# Sender/receiver network experiment

This runs real KCP, ENet, and TCP processes through a Linux router with controlled network impairments:

```text
sender namespace <-- veth --> router namespace <-- veth --> receiver namespace
                             netem both ways
```

See the [first local run and results](RESULTS.md) for a completed 54-trial pilot.

Each run uses fresh namespaces. TCP and ENet connections are established before impairment; KCP state is initialized before sending. No impairment is applied to the host's normal interfaces. Namespaces are removed when trials finish or raise an exception; SIGKILL or host failure may require manual cleanup of the `kb...` namespaces.

## Run

Requires Linux, root access for network namespaces, a C compiler, Python 3, and ENet development headers. On Debian/Ubuntu:

```sh
sudo apt-get install build-essential libenet-dev iproute2 ethtool iputils-ping pkg-config
sudo python3 benchmarks/network/run.py --out /var/tmp/kcp-network-results
```

Choose a new output directory for each run. Defaults: three repeats, three concurrent trials, 500 messages per trial. A short functional check:

```sh
sudo python3 benchmarks/network/run.py \
  --out /var/tmp/kcp-network-smoke \
  --profiles clean --repeats 1 --count 50
```

The output includes a standalone interactive `report.html`, per-message receiver CSVs (a `READY` marker followed by `sequence,scheduled_send_us,received_us` rows), process logs, per-trial JSON results, executed network commands, interface counters, netem statistics, and source hashes. All timestamps use the same host's monotonic clock. Open the report locally in a browser; it requires no server or external assets.

## Workload and transport settings

- 256-byte messages offered every 10 ms (100/s, 204.8 kbit/s of application data).
- Reliable, ordered delivery; every received sequence number and payload is validated. A violation fails the run.
- One-way latency starts at the **scheduled** send time and ends at application delivery, so sender queueing/backpressure is included. TCP uses fixed-size message framing.
- Four seconds of drain after message generation. Messages missing then count against delivery and deadline success, but are not necessarily permanently lost.
- Connection establishment is excluded. There is no separate warm-up, so initial congestion-window growth is included.
- KCP: `nodelay=1`, update interval 10 ms, fast retransmit 2, congestion control enabled, send/receive windows 128, MTU 1200.
- ENet: one reliable ordered channel, MTU 1200, default reliability/congestion settings. The installed library version is recorded.
- TCP: CUBIC and `TCP_NODELAY`. All three transports are unencrypted and use a 1 ms application service loop.
- TSO/GSO/GRO are disabled on the virtual interfaces. Netem is on router egress, before the destination host's TCP stack, rather than on the TCP sender.

## Network profiles

Settings apply independently in each direction. For example, 50 ms per direction adds about 100 ms RTT before queueing.

| Profile | Router egress impairment |
| --- | --- |
| `clean` | 2 ms delay, no configured loss |
| `distant` | 50 ms delay |
| `jitter_loss` | 50 ms delay with 20 ms normal-distribution jitter; 1% independent packet loss |
| `burst_loss` | 20 ms delay; Gilbert–Elliott loss: 1% chance to enter bad state, 25% chance to leave, 80% loss in bad state, 0% in good state |
| `constrained` | 20 ms delay, 128 kbit/s; deliberately below the offered application load |
| `outage` | 20 ms delay; replace impairment with 100% loss approximately 2–4 seconds after GO |

Netem queue limit is 10,000 packets. Exact outage transition times are recorded; replacing the queue can discard queued packets. Profiles are synthetic examples, not measured mobile/Wi-Fi environments. Random runs are unseeded: parameters can be repeated, exact loss sequences cannot.

## Reading results

The report pools delivered-message latencies across repeats for p50/p95/p99. It uses **all offered messages** as the denominator for delivery and the 100 ms deadline. Compare both: a low latency percentile alone can hide missing messages.

Combined endpoint TX counters include protocol headers, retransmissions, ACKs, and link headers after connection setup. They count bytes injected into the emulated path, including packets later dropped by netem; they are not physical-wire bandwidth measurements. The ratio shown is relative to all offered application bytes.

This is a bounded learning experiment, not a transport ranking. Concurrent trials share host CPU resources; library versions, service intervals, buffering, congestion settings, and workload all matter. Use `--jobs 1`, more messages, and more repeats for a longer follow-up. QUIC, SCTP, and SRT are not implemented in this harness.

References: [netem manual](https://man7.org/linux/man-pages/man8/tc-netem.8.html), [ENet](https://github.com/lsalzman/enet).
