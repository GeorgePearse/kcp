#!/usr/bin/env python3
"""Compare a candidate with a baseline inside one frozen benchmark run."""
import argparse
import json
from pathlib import Path
from metrics import percentile


def aggregate(rows):
    offered = sum(r['offered'] for r in rows)
    received = sum(r['received'] for r in rows)
    return dict(delivery_percent=100 * received / offered,
                deadline_percent=100 * sum(r['within_100ms'] for r in rows) / offered,
                p95_ms=percentile([x for r in rows for x in r['latency_ms']], 95),
                tx_bytes_per_offered_message=sum(r['endpoint_tx_bytes'] for r in rows) / offered,
                repeats=len(rows), per_repeat_deadline_percent=[100*r['within_100ms']/r['offered'] for r in rows])


def compare(results, baseline, candidate):
    if baseline == candidate:
        raise ValueError('Choose different variants')
    relevant = [r for r in results if r['protocol'] in (baseline, candidate)]
    if any(r['delivery_contract'] != 'reliable ordered' for r in relevant):
        raise ValueError('UDP is a reference, not eligible for reliable-candidate comparisons')
    profiles = sorted({r['profile'] for r in relevant})
    if not profiles:
        raise ValueError('No trials found')
    comparisons = []
    for profile in profiles:
        base = [r for r in relevant if r['profile'] == profile and r['protocol'] == baseline]
        new = [r for r in relevant if r['profile'] == profile and r['protocol'] == candidate]
        identity = lambda rr: sorted((r['repeat'], r['offered'], tuple(r['netem'])) for r in rr)
        if not base or not new or identity(base) != identity(new):
            raise ValueError('Missing or mismatched candidate/baseline trials')
        b, c = aggregate(base), aggregate(new)
        comparisons.append(dict(profile=profile, baseline=b, candidate=c,
                                deadline_change_pp=c['deadline_percent']-b['deadline_percent'],
                                delivery_change_pp=c['delivery_percent']-b['delivery_percent'],
                                tx_ratio=c['tx_bytes_per_offered_message']/b['tx_bytes_per_offered_message']))
    return dict(baseline=baseline, candidate=candidate, decision='review_only', profiles=comparisons,
                note='No automatic promotion or scalar winner. Compare delivery, deadlines, traffic and per-repeat variation. Latency conditions on delivery; random packet-loss sequences differ.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--baseline', default='kcp')
    parser.add_argument('--candidate', required=True)
    args = parser.parse_args()
    metadata = json.loads((args.run / 'metadata.json').read_text())
    if metadata.get('schema_version') != 2:
        parser.error('Only v2 runs have the required delivery accounting')
    print(json.dumps(compare(json.loads((args.run / 'results.json').read_text()), args.baseline, args.candidate), indent=2))
