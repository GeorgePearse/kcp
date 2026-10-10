#include "ikcp.h"

/* Experimental startup configuration, not a novel congestion algorithm.
 * Keep KCP's built-in ACK/loss responses, but begin with ten segments in flight.
 * Changing incr with cwnd preserves the built-in congestion-avoidance invariant.
 */
int configure_candidate(ikcpcb *kcp) {
    kcp->cwnd = 10;
    kcp->incr = kcp->cwnd * kcp->mss;
    return 0;
}
