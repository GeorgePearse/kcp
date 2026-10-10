# Video transport pilot — October 10, 2026

96 trials: two edge fixtures, two encodings, TCP/KCP/UDP, four network profiles, two repeats. Four seconds offered per trial at 1080p/10fps; three concurrent trials. This is the separate video-v1 suite, not transport-v2.

## Encoded size

| Clip | H.264 Mbit/s | MJPEG Mbit/s |
| --- | ---: | ---: |
| conveyor | 7.357 | 12.991 |
| bunny | 0.951 | 4.993 |

## Completed / on-time video seconds

Each cell is complete seconds / on-time seconds, out of **8 offered seconds** across two repeats. Completion requires all bytes of an independent one-second segment and a matching SHA-256. On-time means within 1.5s of segment release. The observation cutoff is 7s after run start.

| Clip / encoding | Link, each direction | TCP | KCP | UDP |
| --- | --- | --- | --- | --- |
| bunny-h264 | 20mbps | 8 / 8 | 8 / 8 | 8 / 8 |
| bunny-h264 | 5mbps | 8 / 8 | 8 / 8 | 8 / 8 |
| bunny-h264 | 5mbps_loss1 | 8 / 8 | 8 / 6 | 2 / 2 |
| bunny-h264 | 1mbps | 8 / 6 | 8 / 4 | 8 / 6 |
| bunny-mjpeg | 20mbps | 8 / 8 | 4 / 0 | 8 / 8 |
| bunny-mjpeg | 5mbps | 8 / 6 | 3 / 0 | 8 / 6 |
| bunny-mjpeg | 5mbps_loss1 | 7 / 3 | 3 / 0 | 0 / 0 |
| bunny-mjpeg | 1mbps | 2 / 0 | 2 / 0 | 2 / 0 |
| conveyor-h264 | 20mbps | 8 / 8 | 4 / 0 | 8 / 8 |
| conveyor-h264 | 5mbps | 8 / 0 | 1 / 0 | 6 / 0 |
| conveyor-h264 | 5mbps_loss1 | 5 / 0 | 1 / 0 | 0 / 0 |
| conveyor-h264 | 1mbps | 0 / 0 | 0 / 0 | 0 / 0 |
| conveyor-mjpeg | 20mbps | 8 / 8 | 2 / 0 | 8 / 8 |
| conveyor-mjpeg | 5mbps | 4 / 0 | 2 / 0 | 2 / 0 |
| conveyor-mjpeg | 5mbps_loss1 | 2 / 0 | 0 / 0 | 0 / 0 |
| conveyor-mjpeg | 1mbps | 0 / 0 | 0 / 0 | 0 / 0 |

## Interpretation and limits

The clips are the first four seconds of each fixture: the bunny opening is a smooth, low-detail scene; the conveyor is textured moving material. H.264 reduces the offered bitrate for both at these fixed settings, but compression depends heavily on content. The encoder settings are not matched for perceptual quality. All segments were decoded to ten frames before transfer. No video quality or detector-accuracy evaluation was run.

The UDP metric is conservative: a segment with any missing fragment earns no usable-video credit, even if a specialised player could recover some frames. It is not a claim that UDP-based RTP cannot play video under loss. KCP uses the small-window built-in controller (congestion control on), not a video-tuned configuration. The short test includes startup.

Pre-encoding excludes capture/encode latency and CPU. TCP is unencrypted application-framed transport, not the GCS SDK. No QUIC, ENet, TLS, GStreamer, RTSP/RTP, competing traffic, production device or remote physical link was tested. Netem loss is unseeded; two repeats are exploratory; parallel jobs share the host CPU. Payload receipt and complete-segment delivery are reported separately.

## Validation and provenance

Four focused tests passed (deadline/cutoff, duplicate accounting, partial-payload scoring, and a real KCP library roundtrip). The final capacity smoke completed six trials; TCP/UDP delivered all conveyor segments, while default KCP queued data. All 96 final trials submitted the full schedule, exited cleanly, and validated completed segment hashes. Source hashes match the frozen snapshot; 16 encoded segments each decoded to ten frames.

An initial smoke caught a binding assumption: this KCP revision returns the number of bytes accepted by ikcp_send, not zero. The binding was corrected and tested before the final suite. Failed preliminary outputs remain separate; they are not mixed into these results.

Raw artifacts: `gs://binit-models/analysis-reports/video-transport-v1-20261010/`. Inputs and encoded media are private artifacts, not committed to this public fork. See [README.md](README.md) for reproduction and the full workload contract.
