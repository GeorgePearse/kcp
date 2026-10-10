# Transport algorithm learning loop. Use a fresh output directory for each run.
default:
    @just --list

candidates:
    python3 benchmarks/network/run.py --list

test:
    python3 -m unittest discover -s benchmarks/network -p 'test_*.py'

smoke OUT:
    sudo python3 benchmarks/network/run.py --out {{quote(OUT)}} --profiles clean --count 50 --repeats 1 --candidates kcp_iw10
    PEER_BINARY={{quote(OUT)}}/peer python3 -m unittest discover -s benchmarks/network -p 'test_*.py'

benchmark OUT CANDIDATE="kcp_iw10":
    sudo python3 benchmarks/network/run.py --out {{quote(OUT)}} --candidates {{quote(CANDIDATE)}}

validate OUT CANDIDATE="kcp_iw10":
    sudo python3 benchmarks/network/run.py --out {{quote(OUT)}} --split validation --candidates {{quote(CANDIDATE)}}

compare OUT CANDIDATE:
    python3 benchmarks/network/compare.py {{quote(OUT)}} --candidate {{quote(CANDIDATE)}}
