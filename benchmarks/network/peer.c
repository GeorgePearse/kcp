#define _POSIX_C_SOURCE 200809L
#include <arpa/inet.h>
#include <enet/enet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/tcp.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
#include "ikcp.h"

#define SIZE 256
#define PORT 19090
#define MAX_MESSAGES 100000
static volatile sig_atomic_t running = 1;
static int fd = -1, sender, tcp_mode, enet_mode, udp_mode, message_count;
#ifdef KCP_CANDIDATE
int configure_candidate(ikcpcb *kcp);
#endif
static struct sockaddr_in remote;
static uint64_t received;
static uint64_t now_us(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000000 + t.tv_nsec / 1000;
}
static void die(const char *s) { perror(s); exit(1); }
static void stop(int sig) { (void)sig; running = 0; }
static void nonblock(int s) {
    int flags = fcntl(s, F_GETFL, 0);
    if (flags < 0 || fcntl(s, F_SETFL, flags | O_NONBLOCK) < 0) die("fcntl");
}
static int output(const char *buf, int len, ikcpcb *kcp, void *user) {
    (void)kcp; (void)user;
    if (sendto(fd, buf, len, 0, (struct sockaddr *)&remote, sizeof(remote)) != len)
        die("sendto");
    return 0;
}
static void receive_message(const unsigned char *buf, size_t len) {
    uint64_t seq, sent;
    if (len != SIZE) { fprintf(stderr, "Invalid message length\n"); exit(1); }
    memcpy(&seq, buf, 8); memcpy(&sent, buf + 8, 8);
    if (seq >= (uint64_t)message_count) { fprintf(stderr, "Sequence out of range\n"); exit(1); }
    if (!udp_mode && seq != received++) { fprintf(stderr, "Ordering/duplicate violation\n"); exit(1); }
    for (size_t i = 16; i < SIZE; i++) {
        if (buf[i] != (unsigned char)(seq + i)) {
            fprintf(stderr, "Payload mismatch\n"); exit(1);
        }
    }
    printf("%llu,%llu,%llu\n", (unsigned long long)seq,
           (unsigned long long)sent, (unsigned long long)now_us());
}
int main(int argc, char **argv) {
    if (argc != 6) {
        fprintf(stderr, "usage: peer kcp|kcp_nocc|kcp_candidate|udp|enet|tcp send|recv receiver_ip count interval_us\n");
        return 2;
    }
    sender = !strcmp(argv[2], "send");
    tcp_mode = !strcmp(argv[1], "tcp"); enet_mode = !strcmp(argv[1], "enet");
    udp_mode = !strcmp(argv[1], "udp");
    if ((!tcp_mode && !enet_mode && !udp_mode && strcmp(argv[1], "kcp") &&
         strcmp(argv[1], "kcp_nocc") && strcmp(argv[1], "kcp_candidate")) ||
        (!sender && strcmp(argv[2], "recv"))) return 2;
    int count = atoi(argv[4]), interval = atoi(argv[5]);
    if (count <= 0 || count > MAX_MESSAGES || interval < 1000) return 2;
    message_count = count;
    setvbuf(stdout, NULL, _IOLBF, 0);
    signal(SIGTERM, stop); signal(SIGINT, stop); signal(SIGPIPE, SIG_IGN);
    remote.sin_family = AF_INET; remote.sin_port = htons(PORT);
    if (inet_pton(AF_INET, argv[3], &remote.sin_addr) != 1) return 2;
    ENetHost *host = NULL; ENetPeer *peer = NULL; ikcpcb *kcp = NULL;
    if (enet_mode) {
        if (enet_initialize()) return 1;
        ENetAddress address = {ENET_HOST_ANY, PORT};
        host = enet_host_create(sender ? NULL : &address, 1, 1, 0, 0);
        if (!host) { fprintf(stderr, "enet_host_create failed\n"); return 1; }
        host->mtu = 1200;
        if (sender) {
            enet_address_set_host(&address, argv[3]);
            peer = enet_host_connect(host, &address, 1, 0);
            ENetEvent event;
            if (!peer || enet_host_service(host, &event, 5000) <= 0 ||
                event.type != ENET_EVENT_TYPE_CONNECT) {
                fprintf(stderr, "ENet connection failed\n"); return 1;
            }
        }
    } else {
        fd = socket(AF_INET, tcp_mode ? SOCK_STREAM : SOCK_DGRAM, 0);
        if (fd < 0) die("socket");
        if (sender && tcp_mode) {
            if (connect(fd, (struct sockaddr *)&remote, sizeof(remote))) die("connect");
        } else if (!sender) {
            struct sockaddr_in local = remote; local.sin_addr.s_addr = INADDR_ANY;
            int yes = 1; setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
            if (bind(fd, (struct sockaddr *)&local, sizeof(local))) die("bind");
            if (tcp_mode) {
                if (listen(fd, 1)) die("listen");
                puts("READY");
                int connected = accept(fd, NULL, NULL);
                if (connected < 0) die("accept");
                close(fd); fd = connected;
            }
        }
        nonblock(fd);
        if (tcp_mode) {
            int yes = 1;
            if (setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &yes, sizeof(yes))) die("TCP_NODELAY");
        } else if (!udp_mode) {
            kcp = ikcp_create(0x12345678, NULL);
            if (!kcp) return 1;
            ikcp_setoutput(kcp, output); ikcp_setmtu(kcp, 1200);
            ikcp_wndsize(kcp, 128, 128);
            ikcp_nodelay(kcp, 1, 10, 2, !strcmp(argv[1], "kcp_nocc"));
            if (!strcmp(argv[1], "kcp_candidate")) {
#ifdef KCP_CANDIDATE
                if (configure_candidate(kcp) < 0) return 1;
#else
                fprintf(stderr, "No candidate linked\n"); return 2;
#endif
            }
        }
    }
    if (sender || !tcp_mode) puts("READY");
    if (sender && getchar() != 'G') return 1;
    unsigned char *queue = calloc((size_t)count, SIZE);
    if (!queue) die("calloc");
    size_t queued = 0, written = 0, accumulated = 0;
    unsigned char stream[SIZE], buffer[65536];
    uint64_t start = now_us(), deadline = start + (uint64_t)count * interval + 4000000;
    if (sender) printf("START %llu\n", (unsigned long long)start);
    const char *trace_path = getenv("KCP_TRACE");
    FILE *trace = sender && kcp && trace_path ? fopen(trace_path, "w") : NULL;
    if (sender && kcp && trace_path && !trace) die("trace fopen");
    if (trace) fprintf(trace, "elapsed_ms,cwnd,queued_segments,inflight_segments,srtt_ms,rto_ms,timeout_retransmits\n");
    uint64_t next_trace = start;
    int generated = 0;
    while (running && (!sender || now_us() < deadline)) {
        uint64_t now = now_us();
        while (sender && generated < count && now >= start + (uint64_t)generated * interval) {
            unsigned char *msg = queue + (size_t)generated * SIZE;
            uint64_t seq = (uint64_t)generated, scheduled = start + seq * interval;
            memcpy(msg, &seq, 8); memcpy(msg + 8, &scheduled, 8);
            for (size_t i = 16; i < SIZE; i++) msg[i] = (unsigned char)(seq + i);
            if (enet_mode) {
                ENetPacket *packet = enet_packet_create(msg, SIZE, ENET_PACKET_FLAG_RELIABLE);
                if (!packet || enet_peer_send(peer, 0, packet)) return 1;
            } else if (udp_mode) {
                output((char *)msg, SIZE, NULL, NULL);
            } else if (!tcp_mode && ikcp_send(kcp, (char *)msg, SIZE) < 0) return 1;
            generated++; queued += SIZE;
        }
        if (enet_mode) {
            ENetEvent event; int result;
            while ((result = enet_host_service(host, &event, 0)) > 0) {
                if (event.type == ENET_EVENT_TYPE_RECEIVE) {
                    if (!sender) receive_message(event.packet->data, event.packet->dataLength);
                    enet_packet_destroy(event.packet);
                } else if (event.type == ENET_EVENT_TYPE_DISCONNECT) {
                    fprintf(stderr, "Unexpected disconnect\n"); return 1;
                }
            }
            if (result < 0) return 1;
            enet_host_flush(host);
        } else if (tcp_mode) {
            if (sender && written < queued) {
                ssize_t n = send(fd, queue + written, queued - written, 0);
                if (n > 0) written += (size_t)n;
                else if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) die("send");
            }
            if (!sender) {
                ssize_t n = recv(fd, stream + accumulated, SIZE - accumulated, 0);
                if (n > 0) {
                    accumulated += (size_t)n;
                    if (accumulated == SIZE) { receive_message(stream, SIZE); accumulated = 0; }
                    continue;
                }
                if (n == 0) break;
                if (errno != EAGAIN && errno != EWOULDBLOCK) die("recv");
            }
        } else {
            ssize_t n;
            socklen_t len = sizeof(remote);
            while ((n = recvfrom(fd, buffer, sizeof(buffer), 0,
                                  (struct sockaddr *)&remote, &len)) >= 0) {
                if (udp_mode) {
                    if (!sender) receive_message(buffer, (size_t)n);
                } else if (ikcp_input(kcp, (char *)buffer, n) < 0) return 1;
            }
            if (errno != EAGAIN && errno != EWOULDBLOCK) die("recvfrom");
            if (kcp) {
                ikcp_update(kcp, (IUINT32)(now_us() / 1000));
                while ((n = ikcp_recv(kcp, (char *)buffer, sizeof(buffer))) >= 0)
                    if (!sender) receive_message(buffer, (size_t)n);
                if (trace && now >= next_trace) {
                    fprintf(trace, "%llu,%u,%u,%u,%d,%d,%u\n",
                            (unsigned long long)((now - start) / 1000), kcp->cwnd,
                            kcp->nsnd_que, kcp->nsnd_buf, kcp->rx_srtt, kcp->rx_rto, kcp->xmit);
                    next_trace = now + 10000;
                }
            }
        }
        struct timespec pause = {0, 1000000}; nanosleep(&pause, NULL);
    }
    if (sender) printf("SENT %d\n", generated);
    if (trace) fclose(trace);
    free(queue);
    if (kcp) ikcp_release(kcp);
    if (host) { enet_host_destroy(host); enet_deinitialize(); }
    if (fd >= 0) close(fd);
    return 0;
}
