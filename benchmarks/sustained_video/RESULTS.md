# Sustained video capacity — October 10, 2026

56 trials: 36 bitrate-screening runs of 30 seconds and 20 confirmation runs of 90 seconds. Each confirmed rate has two independent repeats. All use the conveyor fixture at 1080p/10fps, repeating five independently encoded one-second H.264 segments. Three concurrent trials share the host CPU.

## Confirmed bitrate bounds

Pass requires every segment delivered by its fixed two-second playout offset, plus no more than 250ms growth between the mean completion latency of the first and last ten segments. Highest confirmed means both 90s repeats passed; a failing upper neighbour means it did not pass both. These are finite-run observations, not proof of a continuous maximum or production reliability.

| Degraded link | Transport | Highest confirmed actual Mbit/s | Higher tested failure Mbit/s |
| --- | --- | ---: | ---: |
| loss_jitter | tcp | 0.581 | 1.152 |
| loss_jitter | kcp | 0.295 | 0.581 |
| loss_jitter | udp | None demonstrated | 0.295 |
| burst_loss | tcp | None demonstrated | 0.295 |
| burst_loss | kcp | None demonstrated | 0.295 |
| burst_loss | udp | None demonstrated | 0.295 |

Both links are limited to 5Mbit/s each direction. `loss_jitter`: 40ms±10ms normal jitter and1% independent loss each direction. `burst_loss`: 20ms delay, Gilbert–Elliott entry1%, exit25%, bad-state loss80%, good-state loss0%. Queue1000. Loss is unseeded.

## Per-confirmation evidence

| Profile | Transport | Actual Mbit/s | Repeat | On-time seconds /90 | Lag growth ms | Extra stall seconds | Pass |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| burst_loss | kcp | 0.295 | 2 | 90 | 0.0 | 0.00 | True |
| burst_loss | kcp | 0.295 | 3 | 84 | 1302.3 | 3.03 | False |
| burst_loss | kcp | 0.581 | 2 | 88 | -441.1 | 0.49 | False |
| burst_loss | kcp | 0.581 | 3 | 86 | 38.5 | 0.29 | False |
| burst_loss | tcp | 0.295 | 2 | 28 | unknown | >=63.27 | False |
| burst_loss | tcp | 0.295 | 3 | 61 | unknown | >=14.85 | False |
| burst_loss | tcp | 0.581 | 2 | 48 | unknown | >=12.85 | False |
| burst_loss | tcp | 0.581 | 3 | 27 | unknown | >=22.25 | False |
| burst_loss | udp | 0.295 | 2 | 60 | unknown | >=90.00 | False |
| burst_loss | udp | 0.295 | 3 | 64 | unknown | >=86.00 | False |
| loss_jitter | kcp | 0.295 | 2 | 90 | -130.8 | 0.00 | True |
| loss_jitter | kcp | 0.295 | 3 | 90 | -5.1 | 0.00 | True |
| loss_jitter | kcp | 0.581 | 2 | 10 | unknown | >=8.15 | False |
| loss_jitter | kcp | 0.581 | 3 | 5 | unknown | >=8.72 | False |
| loss_jitter | tcp | 0.581 | 2 | 90 | 3.7 | 0.00 | True |
| loss_jitter | tcp | 0.581 | 3 | 90 | -25.5 | 0.00 | True |
| loss_jitter | tcp | 1.152 | 2 | 56 | 424.7 | 3.15 | False |
| loss_jitter | tcp | 1.152 | 3 | 90 | 343.7 | 0.00 | False |
| loss_jitter | udp | 0.295 | 2 | 66 | unknown | >=92.00 | False |
| loss_jitter | udp | 0.295 | 3 | 67 | unknown | >=93.00 | False |

## Interpretation and scope

This answers sustained capacity under a fixed playback contract. The earlier four-second video-v1 run answers a different question and is not used as stability evidence. Six requested encoder rates are screened, then the highest screen pass and next higher rate are independently confirmed. Failed selected rates are stepped down and retested. The report shows actual payload/container bitrate; CBR targets and output sizes differ.

No segment skipping, buffer expansion, adaptive bitrate or FEC. Missing UDP fragments invalidate a whole segment, stricter than players using concealment or partial-frame recovery. KCP uses builtin congestion control and128-segment windows, not a tuned video configuration. No claim applies to every KCP or UDP media design.

Media is pre-encoded; lower rates change visual quality, which was not evaluated. Capture/encode latency is excluded. This is an application-framed transport and virtual-player deadline model, not a GStreamer/RTSP/RTP, QUIC, TLS, production GCS or physical WAN run. Two repeats and unseeded loss do not establish a reliability guarantee.

## Validation

Six metric tests passed: steady stream, missing segments despite high byte delivery, late playback stalls, growing latency before buffer exhaustion, observation cutoff, and duplicate completion rejection. All 56 trials submitted the full offered packet schedule and exited without endpoint errors. Completed segments matched source hashes; all30 encoded source segments decoded to ten frames. Source snapshots match tested repository code. Raw arrivals, encoder commands, failed trials and network counters are retained.

Private evidence: `gs://binit-models/analysis-reports/sustained-video-v1-20261010/`. Raw footage is not committed. See [README.md](README.md) for the frozen contract and reproduction command.
