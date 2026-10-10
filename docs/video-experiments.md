# How much video can the network carry?

This pilot sends **actual encoded video bytes** through the same kind of isolated Linux sender/router/receiver network used by the small-message benchmark. It measures how much complete video arrives, and how much arrives soon enough for a chosen playback deadline.

[Explore the video delivery report](reports/video-v1.html){ .md-button .md-button--primary }

## Workload

The sources are existing edge-test fixtures: four seconds of conveyor footage and the first four seconds of a Big Buck Bunny clip. The Bunny opening is smooth and low-detail; the conveyor contains textured moving material. These are a small pilot, not a representative video corpus.

Both are encoded at **1920×1080, 10fps**, using either H.264 (libx264 veryfast, CRF23, no B frames) or MJPEG (quality 4). Each one-second segment is independently decodable. The settings are not matched for visual quality; this does not measure codec quality or downstream detection accuracy.

| Source | H.264 encoded bitrate | MJPEG encoded bitrate |
| --- | ---: | ---: |
| Conveyor | 7.357 Mbit/s | 12.991 Mbit/s |
| Bunny opening | 0.951 Mbit/s | 4.993 Mbit/s |

These rates include the segment container, before network/protocol overhead. A link needs additional headroom. The large difference between clips shows why resolution and FPS alone do not determine video bandwidth.

## Network experiment

The suite runs TCP, KCP with built-in congestion control, and best-effort UDP. Each receives the same encoded payload, packet framing and pacing schedule. There are four profiles, each with 20ms delay per direction: 20 Mbit/s, 5 Mbit/s, 5 Mbit/s with 1% random loss, and 1 Mbit/s. Two repeats across all combinations produce **96 trials**. Three trials run concurrently on the same host.

Each trial offers four seconds of video over four seconds, then permits three seconds to drain. A segment is **complete** only when its SHA-256 matches the original. It is **on time** only if complete within 1.5 seconds of its scheduled release. Every source segment was decoded to ten frames before transmission.

A partly received segment earns byte-delivery credit but no usable-video credit. That is intentionally conservative: a specialised decoder could recover some frames from a damaged stream. It does not mean every UDP/RTP streaming system would lose as much video as this simple no-retry framing.

## What this tells us about the edge

At these settings, a 5 Mbit/s uplink cannot carry the conveyor's H.264 output in real time even before transport overhead. The Bunny clip fits much more easily. Choosing an appropriate encoding, frame rate or resolution is therefore necessary before tuning transport.

The 20 Mbit/s capacity control distinguishes link saturation from transport startup and window behaviour. KCP uses the existing small-window controller, not a video-tuned configuration. Slow results here do not establish a limit on every possible KCP configuration.

Use the report to compare **complete seconds**, **on-time seconds**, received payload and transmitted traffic. Looking at bytes alone can hide scattered losses that prevent reconstruction; looking only at latency of successful deliveries can hide missing video.

## A concrete loss comparison

For the Bunny H.264 clip on the 5 Mbit/s link with 1% loss, across two repeats:

| Transport | Complete seconds / 8 offered | On-time seconds / 8 offered |
| --- | ---: | ---: |
| TCP | 8 | 8 |
| KCP | 8 | 6 |
| UDP | 2 | 2 |

The clean 20 Mbit/s control delivered all eight conveyor seconds on time with TCP and UDP for both encodings. At 5 Mbit/s, neither encoding delivered any complete conveyor segment within the chosen deadline, regardless of transport. TCP still completed all eight H.264 seconds during the longer observation window: complete delivery and timely playback are different outcomes.

## Reproduce and inspect

The [benchmark README](https://github.com/GeorgePearse/kcp/blob/docs/learning-fork-callout/benchmarks/video/README.md) documents dependencies, commands and the fixed workload. The [results ledger](https://github.com/GeorgePearse/kcp/blob/docs/learning-fork-callout/benchmarks/video/RESULTS.md) contains every aggregate comparison and validation details. Source hashes, segment hashes, raw arrivals, network commands and counters are retained with the run.

This is separate from the original transport-v2 benchmark. It uses pre-encoded media, excludes capture/encoding cost, and does not run GStreamer, RTP/RTSP, QUIC, TLS or the production GCS uploader. Random loss is unseeded and two repeats are exploratory. Raw footage is not included in this public documentation.
