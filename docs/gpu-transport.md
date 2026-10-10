# From GPU tensors to network packets

Distributed GPU communication still faces loss, congestion and delayed packets. Specialised hardware changes where much of the work happens; it does not make those problems disappear.

## Three different decisions

| Layer | Question | Examples |
| --- | --- | --- |
| Collective algorithm | Which GPU sends which tensor chunks to whom? | Ring/tree all-reduce, all-gather, all-to-all |
| Transport | How are chunks delivered and losses recovered? | TCP; reliable RDMA over InfiniBand or RoCE |
| Interconnect | How do bits travel between devices? | NVLink, PCIe, Ethernet, InfiniBand |

NCCL coordinates collective communication on NVIDIA GPUs. For example, all-reduce can sum contributions from multiple GPUs and return the result to each participant. Operations are enqueued on CUDA streams: the application must respect completion and memory-ordering requirements before using results. [NCCL documentation](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/index.html)

## Inside a server

Where topology and peer access support it, GPUs can access each other's memory over NVLink or PCIe. NVSwitch provides switching for NVLink-connected GPUs; it is different from an Ethernet switch. Some larger systems extend NVLink connectivity across a rack, so the server boundary is not a universal dividing line. [NVIDIA NVLink](https://www.nvidia.com/en-us/data-center/nvlink/)

## Across a network

A common high-performance path is GPUDirect RDMA:

```text
GPU A memory → RDMA network card → switches → RDMA network card → GPU B memory
```

The network adapter can read or write GPU memory without staging the payload in CPU memory. The CPU/driver still helps establish mappings and connections and may submit communication work. “Direct” does not mean packets bypass switches or that CPU involvement is always zero. [GPUDirect RDMA documentation](https://docs.nvidia.com/cuda/gpudirect-rdma/)

Where direct GPU memory access or RDMA is unavailable, communication may use host-memory staging and TCP sockets. The actual path depends on topology, drivers, network plugins and configuration; an advertised GPU model alone does not establish which path a job uses. [NCCL troubleshooting](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/troubleshooting.html)

## InfiniBand, RoCE and UDP

**InfiniBand** is a specialised networking architecture with RDMA support. **RoCE** means RDMA over Converged Ethernet. RoCEv2 wraps its RDMA transport packets in UDP/IP, allowing routing across IP networks.

UDP is the envelope. A reliable RDMA connection adds its own sequencing, acknowledgements and recovery; it does not ask training code to accept missing tensor bytes. RDMA also has unreliable modes, so “RDMA” alone is not a delivery guarantee. [NVIDIA RoCE documentation](https://networking-docs.nvidia.com/mlnxofedswum/24010331/rdma-over-converged-ethernet-roce) and [RDMA transport modes](https://docs.nvidia.com/rdma-aware-networks-programming-user-manual-1-7.pdf)

This resembles KCP-over-UDP at one level: both can add reliability above UDP. The implementation and application interface differ substantially. KCP is software driven by the application; an RDMA adapter can perform transport processing and direct memory placement in hardware.

## Why congestion matters on a wired cluster

Imagine many GPUs finishing computation together and sending to one destination. The receiver's link has a finite rate. Switch queues grow when incoming traffic exceeds outgoing capacity, even with perfect cables. A large queue increases latency; exhausted buffers can cause drops.

A collective can be delayed by one slow participant or transfer. That makes communication scheduling, topology, congestion control and tail latency relevant to overall compute utilisation. Our [network hardware chapter](hardware.md) follows the feedback loop that tells senders to slow down.

!!! note "Scope of our experiment"
    Our socket/netem benchmark explores reliability, queues and deadlines. It does not emulate RDMA adapter internals, NVLink, switch credit systems or GPU memory synchronisation. Its KCP rankings cannot be transferred directly to a GPU cluster.
