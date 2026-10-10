# The hardware that handles GPU networking

The main pieces are **RDMA-capable network adapters in the servers** and **switches connecting those adapters**. The adapters handle transport endpoints and memory access. The switches forward packets and help control congestion.

## What would you actually find in a rack?

| Component | Example | Job |
| --- | --- | --- |
| RDMA network adapter | NVIDIA/Mellanox ConnectX | Move data between memory and the network; process RDMA transport |
| Ethernet switch | NVIDIA Spectrum or another suitable data-centre Ethernet switch | Forward Ethernet traffic and provide queue/congestion controls for RoCE |
| InfiniBand switch | NVIDIA Quantum | Forward InfiniBand traffic with its fabric mechanisms |
| DPU | NVIDIA BlueField | Combine networking acceleration with programmable processing for infrastructure services |
| GPU interconnect switch | NVSwitch | Connect GPUs over NVLink; a separate role from Ethernet/InfiniBand networking |

An InfiniBand adapter is often called an **HCA**, or host channel adapter. A RoCE adapter is often called an **RNIC**, an RDMA network interface controller. “SuperNIC” is vendor terminology for adapters aimed at accelerated computing; it is not a separate wire protocol. A DPU is not required for basic RDMA.

Product references: [ConnectX adapters](https://www.nvidia.com/en-eu/networking/infiniband-adapters/), [Spectrum Ethernet](https://www.nvidia.com/en-us/networking/ethernet/), [Quantum InfiniBand](https://www.nvidia.com/en-us/networking/infiniband/), [BlueField](https://www.nvidia.com/en-us/networking/products/data-processing-unit/), [NVLink/NVSwitch](https://www.nvidia.com/en-us/data-center/nvlink/). These are examples, not requirements or a purchasing recommendation; features vary by device and generation.

## Follow one RDMA write

Suppose GPU A has a tensor to place in GPU B's memory.

1. **Prepare memory.** Software registers/maps the buffers and grants the adapter access. The receiver supplies an authorised destination address and access key.
2. **Submit work.** Software places a descriptor on a send queue: source, destination and length. A notification, often called a doorbell, tells the adapter to process queued work.
3. **Make packets.** The adapter reads source memory using DMA, divides the transfer into packets and adds transport headers and sequence information.
4. **Deliver and recover.** On a reliable connection, adapters track acknowledgements and retry missing data. A permanent failure eventually produces an error, not guaranteed delivery.
5. **Place data.** The receiving adapter checks permissions and writes into the registered destination. Completion records report work status; the application still needs the correct synchronisation before using the data.

The associated send/receive queues are called a **queue pair**. A **completion queue** reports completed operations. These let software submit transfers rather than process every packet itself. [NVIDIA RDMA programming manual](https://docs.nvidia.com/rdma-aware-networks-programming-user-manual-1-7.pdf)

With GPUDirect RDMA, those buffers can be in GPU memory, subject to supported topology and mappings. Bypassing CPU payload copies does not remove memory-ordering requirements. [GPUDirect RDMA](https://docs.nvidia.com/cuda/gpudirect-rdma/)

## What makes the adapter different from a normal network card?

Ordinary NICs already offload jobs such as checksums and segmentation. An RDMA adapter additionally maintains transport and memory-access state: queues, registered memory permissions, sequence numbers, acknowledgements and retransmission machinery. Dedicated logic, firmware and sometimes programmable processors do work that a conventional socket transport would largely perform in the host networking stack.

The advantage is reduced CPU work and fewer payload copies at high data rates. It does not eliminate protocol overhead, finite buffers or contention. [ConnectX architecture and capabilities](https://docs.nvidia.com/nvidia-connectx-6-infiniband-ethernet-adapter-cards-user-manual.pdf)

## How switches and cards cooperate on congestion

For a common RoCE congestion-control design, the loop looks like this:

```text
Switch queue grows
        ↓
Switch marks passing packets: congestion experienced (ECN)
        ↓
Receiver adapter sends a congestion notification (CNP)
        ↓
Sender adapter reduces its sending rate
        ↓
Queue drains; sender later probes for available capacity
```

**DCQCN** is one algorithm for adjusting the sender's rate using that feedback. This is a control algorithm with parameters and tradeoffs, even though it runs on a network device.

**Priority Flow Control (PFC)** is a different mechanism: a congested device can ask its immediate upstream neighbour to temporarily pause a traffic priority. It can prevent buffer overflow but can also spread stalls upstream. It is not end-to-end retransmission or a substitute for a good congestion controller. RoCE deployments differ; PFC is not universally required by the protocol. [RoCE congestion controls](https://docs.nvidia.com/networking-ethernet-software/cumulus-linux-59/Layer-1-and-Switch-Ports/Quality-of-Service/RDMA-over-Converged-Ethernet-RoCE/) and [NVIDIA deployment without PFC](https://enterprise-support.nvidia.com/s/article/howto-configure-resilient-roce-end-to-end-using-connectx-4-and-spectrum--no-qos-x)

InfiniBand uses link-level credits to keep a transmitter within the next hop's advertised buffering capacity. It also has end-to-end congestion controls. Such flow control avoids certain drops, but blocked links and congestion can still delay useful work. [InfiniBand architecture overview](https://network.nvidia.com/pdf/whitepapers/IB_Intro_WP_190.pdf)

## Can we experiment with these algorithms?

Yes, but the available control points depend on hardware. Some NVIDIA devices expose programmable congestion-control infrastructure, including algorithms based on explicit congestion feedback and round-trip-time measurements. This is more constrained than compiling an arbitrary C library on the host. [NVIDIA congestion-control infrastructure](https://networking-docs.nvidia.com/doca/archive/3-5-0/congestion-control-infrastructure)

For this repository, the practical progression is to study sender/receiver control algorithms, add multi-sender workloads, then test suitable candidates on real RDMA equipment. Evidence should include total exchange completion time, queue/congestion counters, retries and fairness. None of that hardware validation has been performed here yet.
