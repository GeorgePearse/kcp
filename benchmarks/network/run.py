#!/usr/bin/env python3
"""Run real transports through isolated Linux netem routers. Requires root."""
import argparse
import concurrent.futures
import hashlib
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
BENCH = Path(__file__).resolve().parent
SUITE = json.loads((BENCH / "suite.json").read_text())
PROFILES = {name: item["netem"] for name, item in SUITE["profiles"].items()}
BUILTINS = ["udp", "kcp", "kcp_nocc", "enet", "tcp"]
from metrics import summarize_rows


def command(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs).stdout

def nscommand(ns, *args):
    return ["ip", "netns", "exec", ns, *map(str, args)]

def trial(binary, peer_protocol, out, protocol, profile, repeat, count, interval):
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
        args = [binary, peer_protocol, "recv", "10.203.20.2", count, interval]
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
                                          stdout=subprocess.PIPE, stderr=sender_errors, text=True,
                                          env={**os.environ, "KCP_TRACE": str(folder / "kcp-trace.csv")})
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
                if sender.returncode or not sender_output.startswith("START ") or sender_output.splitlines()[-1] != f"SENT {count}":
                    raise RuntimeError(f"{name}: sender failed: {sender_output}")
                start_us = int(sender_output.splitlines()[0].split()[1])
                # Score a fixed sender-clock cutoff even if collection runs slightly later.
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
        metrics = summarize_rows(rows, count, interval, start_us, SUITE["drain_us"],
                                 SUITE["deadline_ms"], reliable=protocol != "udp")
        result = dict(protocol=protocol, peer_protocol=peer_protocol, profile=profile, repeat=repeat,
                      delivery_contract="best-effort datagrams" if protocol == "udp" else "reliable ordered",
                      **metrics,
                      endpoint_tx_bytes=sum(a["bytes"] - b["bytes"] for a, b in zip(after, before)),
                      endpoint_tx_packets=sum(a["packets"] - b["packets"] for a, b in zip(after, before)),
                      netem=PROFILES[profile], events=events, qdisc=qdisc, before=before, after=after,
                      start_us=start_us)
        (folder / "result.json").write_text(json.dumps(result, indent=2))
        print(f"{name}: {metrics['received']}/{count}, p95={result['p95_ms']} ms, within100ms={result['within_100ms']}", flush=True)
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
    page = (BENCH / "report.html").read_text()
    (out / "report.html").write_text(page.replace("__DATA__", data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--count", type=int, default=SUITE["count"])
    parser.add_argument("--interval-us", type=int, default=SUITE["interval_us"])
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--split", choices=["development", "validation", "correctness"], default="development")
    parser.add_argument("--profiles", nargs="+", choices=PROFILES)
    parser.add_argument("--protocols", nargs="+", choices=BUILTINS, default=BUILTINS)
    registry = json.loads((BENCH / "candidates/registry.json").read_text())
    parser.add_argument("--candidates", nargs="+", choices=registry, default=[])
    parser.add_argument("--list", action="store_true", help="List baseline and experimental variants without running")
    args = parser.parse_args()
    if args.list:
        print(json.dumps({"baselines": BUILTINS, "candidates": registry}, indent=2)); return
    if os.geteuid() != 0:
        parser.error("Run with sudo: network namespace creation needs root")
    if not args.out:
        parser.error("--out is required")
    if not 1 <= args.count <= 100000 or args.jobs < 1 or args.repeats < 1 or args.interval_us < 1000:
        parser.error("Invalid count/jobs/repeats/interval")
    profiles = args.profiles or [p for p, spec in SUITE["profiles"].items() if spec["split"] == args.split]
    if len(profiles) != len(set(profiles)) or len(args.protocols) != len(set(args.protocols)) or len(args.candidates) != len(set(args.candidates)):
        parser.error("Duplicate selections would overwrite trial artifacts")
    if "outage" in profiles and args.count * args.interval_us < 5000000:
        parser.error("The outage profile requires at least five seconds of offered messages")
    if SUITE["message_bytes"] != 256 or SUITE["drain_us"] != 4000000 or SUITE["deadline_ms"] != 100 or SUITE["queue_limit"] != 10000:
        parser.error("This harness supports only the v2 message size/drain/deadline/queue contract")
    for source, expected in SUITE["baseline_sha256"].items():
        if hashlib.sha256((ROOT / source).read_bytes()).hexdigest() != expected:
            parser.error("Baseline source changed. Put experiments in candidates/ or deliberately version the suite.")
    for tool in ("ip", "ping", "/sbin/tc", "/sbin/ethtool", "/usr/bin/cc"):
        if not shutil.which(tool):
            parser.error(f"Missing tool: {tool}")
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    sources = ["ikcp.c", "ikcp.h"] + [str(p.relative_to(ROOT)) for p in BENCH.rglob("*")
              if p.is_file() and p.suffix in {".c", ".py", ".json", ".html"} and "__pycache__" not in p.parts]
    source_hashes = {}
    for source in sources:
        destination = out / "source" / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / source).read_bytes())
        source_hashes[source] = hashlib.sha256(destination.read_bytes()).hexdigest()
    frozen = out / "source"
    frozen_bench = frozen / "benchmarks/network"
    build_commands = []
    def compile_peer(name, candidate=None):
        obj = out / (name + ".o")
        binary = out / name
        cmd = ["/usr/bin/cc", "-O2", "-Wall", "-Wextra", "-Werror", "-I", frozen]
        if candidate:
            cmd += ["-DKCP_CANDIDATE"]
        cmd += ["-c", frozen_bench / "peer.c", "-o", obj]
        build_commands.append(list(map(str, cmd))); command(cmd)
        objects = [obj]
        if candidate:
            candidate_obj = out / (name + "-candidate.o")
            cmd = ["/usr/bin/cc", "-O2", "-Wall", "-Wextra", "-Werror", "-I", frozen,
                   "-c", frozen_bench / candidate["source"], "-o", candidate_obj]
            build_commands.append(list(map(str, cmd))); command(cmd)
            objects.append(candidate_obj)
        cmd = ["/usr/bin/cc", "-O2", "-I", frozen, *objects, frozen / "ikcp.c", "-lenet", "-o", binary]
        build_commands.append(list(map(str, cmd))); command(cmd)
        return binary
    baseline = compile_peer("peer")
    variants = {p: (baseline, p) for p in args.protocols}
    for name in args.candidates:
        variants[name] = (compile_peer(name, registry[name]), "kcp_candidate")
    metadata = dict(schema_version=2, suite=SUITE, suite_sha256=source_hashes["benchmarks/network/suite.json"],
                    kernel=platform.uname()._asdict(), count=args.count, interval_us=args.interval_us,
                    repeats=args.repeats, jobs=args.jobs, profiles=profiles, protocols=list(variants),
                    split=args.split if not args.profiles else "custom", random_loss="unseeded",
                    candidates={name: registry[name] for name in args.candidates},
                    enet=command(["pkg-config", "--modversion", "libenet"]).strip(),
                    tc=command(["/sbin/tc", "-V"]).strip(),
                    compiler=command(["/usr/bin/cc", "--version"]).splitlines()[0],
                    commit=command(["git", "-C", ROOT, "rev-parse", "HEAD"]).strip(),
                    source_sha256=source_hashes, build_commands=build_commands)
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2))
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(trial, binary, peer_protocol, out, protocol, profile, repeat, args.count, args.interval_us)
                   for repeat in range(1, args.repeats + 1) for profile in profiles
                   for protocol, (binary, peer_protocol) in variants.items()]
        try:
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
                (out / "results.json").write_text(json.dumps(results, indent=2))
        except BaseException:
            for future in futures:
                future.cancel()
            raise
    results.sort(key=lambda r: (r["profile"], r["protocol"], r["repeat"]))
    report(out, results, metadata)
    from compare import compare
    for candidate in args.candidates:
        if "kcp" in variants:
            (out / (candidate + "-comparison.json")).write_text(json.dumps(compare(results, "kcp", candidate), indent=2))
    print(out / "report.html", flush=True)

if __name__ == "__main__":
    main()
