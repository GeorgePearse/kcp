# Stable video capacity on bad networks

The question is **how much video we can continuously carry without stalling playback**, not how many bytes eventually arrive. This benchmark sweeps video bitrate and confirms the highest passing rates with longer runs.

[Explore sustainable bitrate results](reports/sustained-video-v1.html){ .md-button .md-button--primary }

## What “stable” means

The virtual player has a fixed **two-second playout offset**. Every one-second video segment must be complete by its scheduled playback time. We also reject a run if mean delivery latency grows by more than 250ms between the first ten and last ten segments, even if the buffer has not yet run dry.

No skipped segments, adaptive bitrate or ever-growing buffer can turn a failure into a pass. The report shows deadline failures, accumulated extra stall time and delivery latency over time. Missing segments produce a lower bound on stall time at the observation cutoff.

## Find a capacity bound

1. Encode actual conveyor footage at six requested H.264 rates: 0.25, 0.5, 1, 2, 4 and 5.5 Mbit/s.
2. Screen each rate for **30 seconds** with TCP, KCP and plain UDP on each network profile.
3. Test the highest screened pass and next higher rate in **two independent 90-second runs**.
4. If the selected rate fails confirmation, step down and test the next lower rate twice.
5. Report the highest confirmed actual bitrate and any tested failing upper neighbour.

Actual encoded rates include segment/container overhead and differ from encoder targets. A result is a tested bound, not proof of an exact continuous maximum or a guarantee for arbitrary outages.

## The bad networks

Both directions have a **5 Mbit/s** limit and a 1,000-packet queue:

| Profile | Additional impairment, each direction |
| --- | --- |
| Loss and jitter | 40ms delay, 10ms normal jitter, 1% independent random loss |
| Burst loss | 20ms delay; Gilbert–Elliott bad-state entry1%, exit25%, bad-state loss80%, good-state loss0% |

Real sender/receiver processes run in separate Linux namespaces through a netem router. Random loss is unseeded. This exploratory run uses three concurrent isolated trials on one host.

## Video and transport contract

The five-second conveyor edge fixture is encoded into independently decodable one-second H.264 segments at 1080p/10fps, then repeated. Each source segment is decoded and frame-counted before testing. Every received segment must match its SHA-256 before it can be played. The entire offered timeline stays in the denominator.

TCP uses CUBIC and NODELAY. KCP uses built-in congestion control and128-segment windows; these are baseline settings, not a video-tuned controller. UDP has fragment metadata but no recovery or FEC. Requiring complete segments is more conservative than players that conceal packet damage or recover partial frames.

Media is pre-encoded. This measures transport and a deterministic playback model; it does not run a live GStreamer/RTP/RTSP player or include capture/encoding time. Lower bitrates can reduce visual quality, which this benchmark does not evaluate. QUIC, TLS, production GCS and physical WAN links are not tested here.

## Measured capacity bounds

The completed run contains **36 × 30-second screens and 20 × 90-second confirmations**: 48 minutes of offered video across 56 trials. Every confirmed rate below passed both long repeats.

| Network | Transport | Highest confirmed actual video bitrate | Higher tested failure |
| --- | --- | ---: | ---: |
| loss_jitter | tcp | 0.581 Mbit/s | 1.152 Mbit/s |
| loss_jitter | kcp | 0.295 Mbit/s | 0.581 Mbit/s |
| loss_jitter | udp | None demonstrated | 0.295 Mbit/s (lowest tested) |
| burst_loss | tcp | None demonstrated | 0.295 Mbit/s (lowest tested) |
| burst_loss | kcp | None demonstrated | 0.295 Mbit/s (lowest tested) |
| burst_loss | udp | None demonstrated | 0.295 Mbit/s (lowest tested) |

On the loss/jitter link, TCP passed at **0.581 Mbit/s** and KCP at **0.295 Mbit/s**. At1.152 Mbit/s, one TCP confirmation delivered all90 segments by their deadlines but still failed because mean latency grew by344ms. Byte delivery or a short run would miss that warning sign.

No transport demonstrated a stable rate on the burst-loss profile at the tested rates, down to0.295 Mbit/s. This does not establish that a lower rate, different buffer budget, FEC or another transport configuration cannot work.

## Evidence and reproduction

See the [frozen benchmark contract](https://github.com/GeorgePearse/kcp/blob/docs/learning-fork-callout/benchmarks/sustained_video/README.md) and [results ledger](https://github.com/GeorgePearse/kcp/blob/docs/learning-fork-callout/benchmarks/sustained_video/RESULTS.md). All failed trials, arrival records, network counters and source/segment hashes are retained. Raw footage is not in this public site.

The [earlier four-second payload pilot](video-payload-pilot.md) is retained separately. It measured short-run delivery and codec sizes; it does **not** establish sustainable streaming capacity.
