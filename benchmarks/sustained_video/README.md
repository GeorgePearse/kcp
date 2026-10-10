# Sustained video capacity, version 1

**Question:** what is the highest tested encoded-video bitrate that can run over an impaired network without playback stalls or growing latency?

Hypothesis, fixed before results: achievable stable video bitrate will be lower than nominal link capacity due to headers/recovery and congestion control. Independent losses and burst losses can give different sustainable rates. A byte-delivery percentage alone does not establish streaming stability.

## Fixed stability contract

- Real H.264 video, 1080p, 10fps, one-second independently decodable segments. Five seconds of the conveyor edge fixture are encoded at each requested rate and repeated. Content/encoder are fixed across transports.
- Target bitrate ladder: 0.25, 0.5, 1, 2, 4, 5.5 Mbit/s. x264 CBR with filler and fixed VBV settings; report actual encoded rate including containers, not just requested rate. Quality varies across rates and is not evaluated.
- Send each segment's real encoded bytes paced across one second. Pre-encoded: capture/encode latency excluded. All received segments must match SHA-256; decoded source segments must have ten frames.
- Fixed two-second playout offset: segment i must be complete by t=i+2. Late or missing segments are playback deadline failures. No skipping, rate adaptation or buffer expansion is allowed to manufacture a pass.
- A trial is stable only if **every segment meets that deadline** and mean completion latency of the last ten segments is no more than 250ms above the first ten segments. This tests backlog growth as well as stalls. The observation ends after duration+5 seconds; missing segments still fail.
- The virtual player's minimum accumulated extra stall time is the largest positive deadline overrun, if every segment arrives; if any is missing, report a lower bound at the observation cutoff. It is a deterministic playback model, not a browser/player run. Deadline-failure seconds are media seconds unavailable for scheduled playback, not necessarily seconds of wall-clock stalling.

Screen each bitrate for 30s. For each transport/profile, confirm the highest screened pass and next higher bitrate (or the lowest bitrate if nothing passed) for **two independent 90s runs**. A confirmed pass needs both repeats to pass. Report the highest confirmed tested rate and any failing upper neighbour; never imply a proven continuous maximum. If the screen-selected rate fails confirmation, step down the ladder and test that rate twice until a pass or the bottom. Do not claim untested lower rates pass.

## Network and transport

Both directions: 5 Mbit/s. `loss_jitter`: 40ms delay with 10ms normal jitter and 1% independent loss. `burst_loss`: 20ms delay; Gilbert–Elliott bad-state entry1%, exit25%, loss80% in bad state and0% in good. Queue1000. Real isolated Linux namespace sender/router/receiver, TSO/GSO/GRO disabled.

TCP CUBIC + NODELAY; KCP nodelay(1,10,2,0), windows128, MTU1200, congestion control enabled; UDP no retries. Application messages have <=1140 video payload bytes plus12 bytes of fragment metadata (TCP adds4 bytes of framing). No TLS, RTP, RTSP, GStreamer, QUIC, FEC or adaptive bitrate. A missing UDP fragment invalidates the whole segment: conservative relative to players that conceal damage. This measures this delivery contract, not every possible media protocol.

Default serial execution. Parallel trials share CPU, have separate namespaces/links, and record concurrency. Loss is unseeded; a confirmed finite run is evidence for these settings, not a guarantee for arbitrary bad networks. Encoder work is not concurrent with measurements. The prior four-second video-v1 pilot remains separate and is not evidence of sustained stability.

```sh
sudo python3 benchmarks/sustained_video/run.py \
  --out /var/tmp/sustained-video-new \
  --clip /absolute/path/trash_1080p_10fps.mp4 --jobs 1
```

Dependencies: Linux root for namespaces, Python3, ffmpeg/ffprobe with libx264, cc, iproute2, ethtool, ping. Fresh output directory required. Media stays in output, not the repo. Raw arrivals, all failed trials, source/clip/segment hashes, encoding commands, frame checks and network counters are retained. No production changes or candidate promotion.
