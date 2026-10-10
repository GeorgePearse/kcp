#!/usr/bin/env python3
"""Run real transports through isolated Linux netem routers. Requires root."""
import argparse
import concurrent.futures
import hashlib
import html
import json
import os
from pathlib import Path
import platform
import select
import shutil
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
PROFILES = {
    "clean": ["delay", "2ms"],
    "distant": ["delay", "50ms"],
    "jitter_loss": ["delay", "50ms", "20ms", "distribution", "normal", "loss", "random", "1%"],
    "burst_loss": ["delay", "20ms", "loss", "gemodel", "1%", "25%", "80%", "0%"],
    "constrained": ["delay", "20ms", "rate", "128kbit"],
    "outage": ["delay", "20ms"],
}

def command(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs).stdout

def nscommand(ns, *args):
    return ["ip", "netns", "exec", ns, *map(str, args)]

def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, (len(ordered) * p + 99) // 100 - 1)]

def trial(binary, out, protocol, profile, repeat, count, interval):
    name = f"{profile}-{protocol}-{repeat}"
    folder = out / name
    folder.mkdir()
    prefix = "kb" + uuid.uuid4().hex[:9]
    sender_ns, router_ns, receiver_ns = [prefix + s for s in ("s", "r", "d")]
    namespaces = []
    children = []
    commands = []
    def run(args):
        commands.append(list(map(str, args)))
        return command(args)
    def inside(ns, *args):
        return run(nscommand(ns, *args))
    def impair(tokens):
        for dev in ("left", "right"):
            inside(router_ns, "/sbin/tc", "qdisc", "replace", "dev", dev,
                   "root", "netem", "limit", "10000", *tokens)
    try:
        for ns in (sender_ns, router_ns, receiver_ns):
            run(["ip", "netns", "add", ns]); namespaces.append(ns)
            inside(ns, "ip", "link", "set", "lo", "up")
        for endpoint, router_dev, subnet in ((sender_ns, "left", 10), (receiver_ns, "right", 20)):
            inside(endpoint, "ip", "link", "add", "eth0", "type", "veth", "peer", "name", router_dev)
            inside(endpoint, "ip", "link", "set", router_dev, "netns", router_ns)
            for ns, dev, host in ((endpoint, "eth0", 2), (router_ns, router_dev, 1)):
                inside(ns, "ip", "addr", "add", f"10.203.{subnet}.{host}/24", "dev", dev)
                inside(ns, "ip", "link", "set", dev, "up")
                inside(ns, "/sbin/ethtool", "-K", dev, "tso", "off", "gso", "off", "gro", "off")
            inside(endpoint, "ip", "route", "add", "default", "via", f"10.203.{subnet}.1")
        inside(router_ns, "/sbin/sysctl", "-qw", "net.ipv4.ip_forward=1")
        inside(sender_ns, "/sbin/sysctl", "-qw", "net.ipv4.tcp_congestion_control=cubic")
        # Resolve neighbours and check routing before connection setup or impairment.
        inside(sender_ns, "ping", "-c", "1", "-W", "2", "10.203.20.2")
        args = [binary, protocol, "recv", "10.203.20.2", count, interval]
        with (folder / "receiver.csv").open("w") as output, (folder / "receiver.stderr").open("w") as errors:
            receiver = subprocess.Popen(nscommand(receiver_ns, *args), stdout=output, stderr=errors)
            children.append(receiver)
            wait_until = time.monotonic() + 5
            while not (folder / "receiver.csv").read_text().startswith("READY\n"):
                if receiver.poll() is not None or time.monotonic() > wait_until:
                    raise RuntimeError(f"{name}: receiver failed to start")
                time.sleep(.02)
            args[2] = "send"
            with (folder / "sender.stderr").open("w") as sender_errors:
                sender = subprocess.Popen(nscommand(sender_ns, *args), stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE, stderr=sender_errors, text=True)
                children.append(sender)
                if not select.select([sender.stdout], [], [], 6)[0] or sender.stdout.readline() != "READY\n":
                    raise RuntimeError(f"{name}: sender failed to connect")
                impair(PROFILES[profile])
                def counters():
                    return [json.loads(inside(ns, "ip", "-s", "-j", "link", "show", "eth0"))[0]["stats64"]["tx"]
                            for ns in (sender_ns, receiver_ns)]
                before = counters()
                start = time.monotonic()
                sender.stdin.write("G\n"); sender.stdin.flush()
                events = []
                if profile == "outage":
                    time.sleep(2)
                    impair(["loss", "100%"])
                    events.append({"event": "drop_all", "seconds_after_go": time.monotonic() - start})
                    time.sleep(2)
                    impair(PROFILES[profile])
                    events.append({"event": "restore", "seconds_after_go": time.monotonic() - start})
                sender.wait(timeout=count * interval / 1e6 + 10)
                sender_output = sender.stdout.read()
                (folder / "sender.stdout").write_text("READY\n" + sender_output)
                if sender.returncode or sender_output.strip() != f"SENT {count}":
                    raise RuntimeError(f"{name}: sender failed: {sender_output}")
                # Sender has already serviced retransmissions for a four-second drain.
                after = counters()
                qdisc = {dev: json.loads(inside(router_ns, "/sbin/tc", "-s", "-j", "qdisc", "show", "dev", dev))
                         for dev in ("left", "right")}
                receiver.terminate(); receiver.wait(timeout=3)
                if receiver.returncode != 0:
                    raise RuntimeError(f"{name}: receiver failed payload/order validation")
        rows = []
        for line in (folder / "receiver.csv").read_text().splitlines()[1:]:
            seq, sent, arrived = map(int, line.split(","))
            rows.append([seq, sent, arrived])
        if [r[0] for r in rows] != list(range(len(rows))) or len(rows) > count:
            raise RuntimeError("Non-contiguous received sequence")
        latencies = [(r[2] - r[1]) / 1000 for r in rows]
        if any(x < 0 for x in latencies):
            raise RuntimeError("Clock error")
        result = dict(protocol=protocol, profile=profile, repeat=repeat, offered=count,
                      received=len(rows), within_100ms=sum(x <= 100 for x in latencies),
                      p50_ms=percentile(latencies, 50), p95_ms=percentile(latencies, 95),
                      p99_ms=percentile(latencies, 99), max_ms=max(latencies, default=None),
                      endpoint_tx_bytes=sum(a["bytes"] - b["bytes"] for a, b in zip(after, before)),
                      endpoint_tx_packets=sum(a["packets"] - b["packets"] for a, b in zip(after, before)),
                      netem=PROFILES[profile], events=events, qdisc=qdisc, before=before, after=after,
                      latency_ms=latencies, sequence=[r[0] for r in rows])
        (folder / "result.json").write_text(json.dumps(result, indent=2))
        print(f"{name}: {len(rows)}/{count}, p95={result['p95_ms']} ms, within100ms={result['within_100ms']}", flush=True)
        return result
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    child.kill(); child.wait()
        for ns in reversed(namespaces):
            subprocess.run(["ip", "netns", "del", ns], check=False, capture_output=True)
        (folder / "commands.json").write_text(json.dumps(commands, indent=2))


def report(out, results, metadata):
    # All assets/data are embedded so this report works offline.
    data = json.dumps(dict(results=results, metadata=metadata)).replace("<", "\\u003c")
    page = '''<!doctype html><meta charset="utf-8"><title>KCP / ENet / TCP network experiment</title>
<style>body{font:16px system-ui;max-width:1150px;margin:35px auto;padding:0 20px;color:#182335}h1{font-size:30px}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{text-align:left;padding:9px;border-bottom:1px solid #ddd}select{font:inherit;padding:8px}svg{width:100%;border:1px solid #ddd}pre{white-space:pre-wrap;background:#f3f5f8;padding:16px}.note{background:#eef3ff;padding:15px}small{color:#526075}</style>
<h1>Same messages, degraded networks</h1>
<p>Real KCP, ENet and TCP sender/receiver processes, routed through isolated Linux network namespaces.</p>
<p class="note">Exploratory local pilot, not a universal ranking. Each run offers 256-byte messages at 100/s, followed by a 4-second drain. Latency starts at the scheduled send time and ends at application delivery; it includes sender backpressure. Connections are established before impairment. All received payloads and sequence order are checked.</p>
<label>Network profile: <select id="profile"></select></label><div id="settings"></div><div id="summary"></div>
<h2>Delivery latency over the run</h2><p>Blue: KCP · Orange: ENet · Green: TCP. One line per repeat. X: scheduled send time; Y: one-way application delivery latency.</p><svg id="chart" viewBox="0 0 1000 360"></svg>
<h2>How to interpret this</h2><p>Deadline success uses all offered messages as the denominator. Latency percentiles include only delivered messages, pooled across repeats. Missing messages did not arrive within the bounded observation window; this does not prove permanent loss. TX bytes are combined endpoint interface counters after connection setup, including retransmissions, ACKs and link headers; these are not physical-wire bandwidth measurements.</p>
<p>KCP: nodelay=1, interval=10ms, fastresend=2, congestion control enabled, windows=128, MTU=1200. ENet: one reliable ordered channel, MTU=1200, default reliability/congestion settings. TCP: CUBIC, TCP_NODELAY, fixed 256-byte message framing. Encryption is absent for all three. Every process uses a 1ms service loop. Offloads TSO/GSO/GRO are disabled on all test interfaces.</p>
<p>Profiles apply independently on both router egress interfaces. Delay values are per direction, so 50ms gives approximately 100ms RTT before queueing. The 128kbit/s profile is deliberately below the 204.8kbit/s application load. Burst loss uses a two-state Gilbert–Elliott model. The outage drops packets for approximately two seconds, starting two seconds after GO; exact transitions are recorded per run. Random trials are unseeded; repeat parameters are reproducible, packet loss sequences are not. No real Wi-Fi or cellular traces are used.</p>
<details><summary>Environment and provenance</summary><pre id="metadata"></pre></details>
<script>const DATA=__DATA__;const results=DATA.results;const colors={kcp:'#2468df',enet:'#d66b12',tcp:'#148257'};
const select=document.querySelector('#profile');for(const p of [...new Set(results.map(r=>r.profile))])select.add(new Option(p,p));
function percentile(a,p){a=[...a].sort((a,b)=>a-b);return a.length?a[Math.ceil(a.length*p)-1]:null}function fmt(x){return x===null?'—':x.toFixed(1)}
function draw(){const rows=results.filter(r=>r.profile===select.value);document.querySelector('#settings').textContent='Router egress: netem limit 10000 '+rows[0].netem.join(' ');
let t='<table><tr><th>Transport</th><th>Runs</th><th>Delivered / offered</th><th>Within 100ms</th><th>p50 ms</th><th>p95 ms</th><th>p99 ms</th><th>TX / payload bytes</th></tr>';
for(const p of ['kcp','enet','tcp']){const rr=rows.filter(r=>r.protocol===p);if(!rr.length)continue;const a=rr.flatMap(r=>r.latency_ms),sum=k=>rr.reduce((s,r)=>s+r[k],0);t+=`<tr><td>${p}</td><td>${rr.length}</td><td>${sum('received')} / ${sum('offered')}</td><td>${(100*sum('within_100ms')/sum('offered')).toFixed(1)}%</td><td>${fmt(percentile(a,.5))}</td><td>${fmt(percentile(a,.95))}</td><td>${fmt(percentile(a,.99))}</td><td>${(sum('endpoint_tx_bytes')/(sum('offered')*256)).toFixed(2)}×</td></tr>`}document.querySelector('#summary').innerHTML=t+'</table>';
const maxY=Math.max(10,...rows.map(r=>r.max_ms||0))*1.08,maxX=DATA.metadata.count*DATA.metadata.interval_us/1e6;let svg='';for(let i=0;i<=4;i++){const y=320-i*75;svg+=`<line x1="65" y1="${y}" x2="975" y2="${y}" stroke="#ddd"/><text x="5" y="${y}" font-size="12">${(i*maxY/4).toFixed(0)} ms</text><text x="${65+i*910/4}" y="348" font-size="12">${(i*maxX/4).toFixed(1)} s</text>`}for(const r of rows){const points=r.latency_ms.map((v,i)=>`${65+910*r.sequence[i]*DATA.metadata.interval_us/1e6/maxX},${320-300*v/maxY}`).join(' ');svg+=`<polyline points="${points}" fill="none" stroke="${colors[r.protocol]}" stroke-width="1.4" opacity=".65"/>`}document.querySelector('#chart').innerHTML=svg;}
select.onchange=draw;draw();document.querySelector('#metadata').textContent=JSON.stringify(DATA.metadata,null,2);</script>'''
    (out / "report.html").write_text(page.replace("__DATA__", data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--profiles", nargs="+", choices=PROFILES, default=list(PROFILES))
    parser.add_argument("--protocols", nargs="+", choices=["kcp", "enet", "tcp"], default=["kcp", "enet", "tcp"])
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run with sudo: network namespace creation needs root")
    if not 1 <= args.count <= 100000 or args.jobs < 1 or args.repeats < 1:
        parser.error("Invalid count/jobs/repeats")
    if "outage" in args.profiles and args.count < 500:
        parser.error("The outage profile requires at least 500 messages")
    for tool in ("ip", "ping", "/sbin/tc", "/sbin/ethtool", "/usr/bin/cc"):
        if not shutil.which(tool):
            parser.error(f"Missing tool: {tool}")
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    binary = out / "peer"
    command(["/usr/bin/cc", "-O2", "-Wall", "-Wextra", "-Werror", "-I", ROOT, "-c", ROOT / "benchmarks/network/peer.c", "-o", out / "peer.o"])
    command(["/usr/bin/cc", "-O2", "-I", ROOT, out / "peer.o", ROOT / "ikcp.c", "-lenet", "-o", binary])
    sources = ["ikcp.c", "ikcp.h", "benchmarks/network/peer.c", "benchmarks/network/run.py"]
    metadata = dict(kernel=platform.uname()._asdict(), count=args.count, interval_us=10000,
                    repeats=args.repeats, jobs=args.jobs, profiles=args.profiles, protocols=args.protocols,
                    enet=command(["pkg-config", "--modversion", "libenet"]).strip(),
                    tc=command(["/sbin/tc", "-V"]).strip(),
                    compiler=command(["/usr/bin/cc", "--version"]).splitlines()[0],
                    commit=command(["git", "-C", ROOT, "rev-parse", "HEAD"]).strip(),
                    source_sha256={s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest() for s in sources})
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2))
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(trial, binary, out, protocol, profile, repeat, args.count, 10000)
                   for repeat in range(1, args.repeats + 1) for profile in args.profiles for protocol in args.protocols]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            (out / "results.json").write_text(json.dumps(results, indent=2))
    results.sort(key=lambda r: (r["profile"], r["protocol"], r["repeat"]))
    report(out, results, metadata)
    print(out / "report.html", flush=True)

if __name__ == "__main__":
    main()
