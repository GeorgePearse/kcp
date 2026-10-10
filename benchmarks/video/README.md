# Video payload transport pilot

Hypothesis, recorded before running: inter-frame H.264 coding will fit more video into a constrained link than independently coded JPEG frames; packet loss will make best-effort UDP's useful delivery much lower than its received byte count when a segment needs many datagrams. TCP/KCP may recover complete segments but miss playback deadlines.

This is a separate `video-v1` evaluator, not the small-message transport-v2 workload. It sends actual encoded video in four independently decodable one-second Matroska segments. Each segment is split into <=1200-byte application messages with sequence/fragment metadata. The same message framing and byte pacing is used for TCP, KCP and UDP. Segment bytes must match SHA-256 before receiving credit. Encoded segments are decoded and counted before transmission; identical received bytes therefore reproduce the verified source segment.

The source clip is trimmed to four seconds, 1920x1080, 10fps. H.264 uses libx264 veryfast CRF23, no B frames, with each segment independently encoded. MJPEG uses quality 4. These are fixed encoder settings, **not matched perceptual quality**. This is segmented transfer, not an RTSP/RTP, GStreamer, browser, QUIC or production GCS benchmark. Pre-encoding excludes encode CPU and capture latency.

Each segment becomes available at t=0,1,2,3 and its packets are paced across that second. It is on time if complete by its release time +1.5 seconds. Observation ends at t=7 (four seconds offered plus three seconds drain). Late arrivals are retained but not credited beyond cutoff. Report completed video seconds, on-time seconds, unique payload received, and endpoint TX bytes including ACKs/retries. Partial/corrupt segments receive no usable-video credit; no decoder concealment or partially recoverable frames are counted. This deliberately conservative metric suits independently decodable segments, not every streaming player.

Profiles, per direction: 20ms delay at 20Mbit/s (capacity control), 20ms delay at 1Mbit/s, 20ms at 5Mbit/s, and 20ms at 5Mbit/s with 1% independent random loss. Queue limit1000. Isolated sender/router/receiver namespaces; TSO/GSO/GRO off; TCP CUBIC + NODELAY; KCP nodelay(1,10,2,0), windows128, MTU1200, builtin congestion control on. No encryption. UDP has no retries; sequence/fragment framing is application metadata only. Baseline KCP sources remain unchanged. Two repeats are exploratory; netem loss is unseeded. Default jobs1; any concurrency is recorded.

```sh
sudo python3 benchmarks/video/run.py --out /var/tmp/video-pilot \
  --clip conveyor=/absolute/path/trash_1080p_10fps.mp4 \
  --clip bunny=/absolute/path/bbb_1080p_30fps.mp4 --jobs 1
```

Requires Linux root, Python3, ffmpeg/ffprobe with libx264/MJPEG, cc, iproute2, ethtool and ping. Output retains source hashes/snapshot, encoder commands, segment hashes, raw arrival records, network commands/counters, JSON results and a standalone interactive report. Input videos and encoded media are kept locally in the output, not committed or published. New output directory required. Network namespaces are not a security sandbox for arbitrary candidate code.
