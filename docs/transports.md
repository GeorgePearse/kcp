# KCP, ENet, TCP and UDP

A transport chooses what delivery promises to make, and how to keep those promises when packets arrive late, disappear, or arrive out of order. Wired networks need these decisions too: a congested switch can run out of buffer space even when every cable works perfectly.

## What each option promises

| Option | What the application receives | Where the transport runs |
| --- | --- | --- |
| Plain UDP | Separate datagrams, possibly missing, duplicated or reordered | OS sockets; no built-in delivery recovery |
| KCP over UDP | Reliable, ordered messages in this benchmark | C library driven by the application |
| ENet | Reliable or unreliable messages, with channels; we select one reliable ordered channel | C networking library over UDP |
| TCP | Reliable, ordered bytes; the application defines message boundaries | Usually the OS networking stack |

“Reliable” does not mean delivery is guaranteed before a deadline or through a permanent disconnection. Our reliable variants can still have messages waiting when the measurement window ends.

UDP is the substrate for KCP and ENet in this setup. It is also useful as its own baseline: what latency and delivery do we get without paying for acknowledgements or retries? But it cannot win a reliable-delivery comparison by simply abandoning the difficult messages.

Sources: [UDP specification](https://www.rfc-editor.org/rfc/rfc768), [TCP specification](https://www.rfc-editor.org/rfc/rfc9293.html), [ENet design](http://enet.bespin.org/Features.html), and [KCP source](https://github.com/GeorgePearse/kcp/blob/docs/learning-fork-callout/ikcp.c).

## Why a fast link can deliver a message late

Suppose messages 1, 2 and 3 are sent, but the packet containing message 2 disappears. Plain UDP can deliver 1 and 3 immediately. An ordered reliable transport must recover 2 before exposing 3 in that same ordered sequence. The wait is called head-of-line blocking.

There can also be a queue before the first packet leaves. A congestion window limits outstanding unacknowledged data. If the application produces messages faster than the initial window allows, messages wait at the sender. Our [distant-link experiment](benchmark.md#why-was-kcp-so-slow-on-the-distant-link) demonstrates this.

These controls have different purposes:

- **Reliability:** detect missing data and retransmit it.
- **Flow control:** avoid overrunning the receiver.
- **Congestion control:** avoid overwhelming the network between the endpoints.
- **Pacing:** spread transmissions over time instead of emitting a large burst.

KCP's `nc=1` disables its built-in congestion control; it does not disable all receiver/window limits. A faster isolated run with that setting does not establish fair behavior alongside other traffic.

## Follow a message through this repository

In [the endpoint implementation](https://github.com/GeorgePearse/kcp/blob/docs/learning-fork-callout/benchmarks/network/peer.c), the application submits data through `ikcp_send`. Periodic `ikcp_update` calls advance the protocol. Its output callback sends resulting packets through UDP. The receiver passes incoming packets to `ikcp_input` and obtains delivered messages with `ikcp_recv`.

KCP itself does not own the socket or clock. That separation makes this a useful place to experiment with acknowledgement, window and retransmission behavior.

## Other alternatives worth comparing

| Alternative | Why it is interesting |
| --- | --- |
| [GameNetworkingSockets](https://github.com/ValveSoftware/GameNetworkingSockets) | Reliable/unreliable messages, encryption and connection features for games |
| [QUIC](https://www.rfc-editor.org/rfc/rfc9000.html), such as [quiche](https://github.com/cloudflare/quiche) | Encrypted transport over UDP; independently ordered streams reduce cross-stream delivery blocking |
| [SCTP / usrsctp](https://github.com/sctplab/usrsctp) | Message-oriented transport, multiple streams and ordered/unordered delivery |
| [SRT](https://github.com/Haivision/srt) | Retransmission and latency buffering designed for live media |

These overlap in purpose; they are not wire-compatible replacements. They are not yet measured by this harness.

!!! note "Reading the upstream README"
    The inherited README includes historical performance claims and simplified TCP comparisons. Modern TCP can selectively acknowledge and recover lost data; it does not generally resend every packet after a loss. Use measured configurations rather than a universal “KCP is faster” percentage. See [TCP SACK](https://www.rfc-editor.org/rfc/rfc2018.html) and [RACK loss detection](https://www.rfc-editor.org/rfc/rfc8985.html).
