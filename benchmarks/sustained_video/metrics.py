"""The fixed playback contract; bytes alone never earn a stability pass."""
def score(arrivals,manifest,start):
    duration=len(manifest);cutoff=start+duration+5
    completions={}
    for row in arrivals:
        if 'complete' in row and row['time']<=cutoff:
            assert row['complete'] not in completions
            completions[row['complete']]=row['time']-start
    latencies=[completions[i]-i if i in completions else None for i in range(duration)]
    ontime=sum(x is not None and x<=2 for x in latencies)
    complete=len(completions)
    growth=None
    if complete==duration:
        growth=(sum(latencies[-10:])/10-sum(latencies[:10])/10)*1000
    overruns=[max(0,(x if x is not None else duration+5-i)-2) for i,x in enumerate(latencies)]
    stable=ontime==duration and growth is not None and growth<=250
    offered=sum(s['size'] for s in manifest)
    return {'duration_s':duration,'offered_bytes':offered,'encoded_mbps':offered*8/duration/1e6,
            'received_payload_bytes':sum(x['bytes'] for x in arrivals if 'bytes' in x and not x['duplicate'] and x['time']<=cutoff),
            'complete_seconds':complete,'ontime_seconds':ontime,'deadline_failure_seconds':duration-ontime,
            'lag_growth_ms':growth,'completion_latency_ms':[None if x is None else x*1000 for x in latencies],
            'minimum_extra_stall_s':max(overruns),'stall_is_lower_bound':complete<duration,'stable':stable}
