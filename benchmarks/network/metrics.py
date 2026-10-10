"""Independent delivery accounting shared by reports and candidate comparisons."""

def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, (len(ordered) * p + 99) // 100 - 1)]


def summarize_rows(rows, count, interval_us, start_us, drain_us, deadline_ms, reliable):
    """Count each offered message once, allowing UDP duplicates and reordering.

    Latency is scored from the sender's schedule, not a candidate-controlled
    receive timestamp. Late arrivals remain in raw CSV but miss the window.
    """
    seen = set()
    delivered = []
    duplicates = reordered = late = 0
    highest = -1
    cutoff = start_us + count * interval_us + drain_us
    for index, (seq, sent, arrived) in enumerate(rows):
        if not 0 <= seq < count or sent != start_us + seq * interval_us or arrived < sent:
            raise ValueError("Invalid sequence or timestamp")
        if reliable and seq != index:
            raise ValueError("Reliable delivery was duplicated or reordered")
        if arrived > cutoff:
            late += 1
            continue
        if seq in seen:
            duplicates += 1
            continue
        seen.add(seq)
        if seq < highest:
            reordered += 1
        highest = max(highest, seq)
        delivered.append((seq, (arrived - sent) / 1000))
    latencies = [latency for _, latency in delivered]
    return dict(offered=count, received=len(seen), missing=count-len(seen),
                duplicate_arrivals=duplicates, reordered_unique=reordered,
                arrivals_after_window=late, raw_arrivals=len(rows),
                within_100ms=sum(x <= deadline_ms for x in latencies),
                p50_ms=percentile(latencies, 50), p95_ms=percentile(latencies, 95),
                p99_ms=percentile(latencies, 99), max_ms=max(latencies, default=None),
                latency_ms=latencies, sequence=[seq for seq, _ in delivered])
