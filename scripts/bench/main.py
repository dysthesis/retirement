#!/usr/bin/env python3
"""Benchmark harness for the Retirement pack (Python stdlib only).

Stages; each reads files and writes files, and can be rerun alone on old runs:
  collect    launch, drive and stop server + headless client; writes RUN/raw/
  normalise  RUN/raw/ -> flat tables RUN/<table>.csv (schema: tables.py)
  reduce     tables -> RUN/phase_metric.csv, RUN/run_metric.csv (analyse.py)
  compare    N runs x M variants -> mean/sd/cv/min/max and delta vs first variant
  db         all run directories -> bench.sqlite (derived; rebuilt whole)
  run        collect + normalise + reduce + compare for one new run
  profile    stack samples of one thread -> method shares per phase and in slow frames

Runs live in ~/.local/share/retirement-bench/runs/<time>-<variant>/; scratch state in
~/.cache/claude-retirement-scratch/bench/.

Examples:
  scripts/bench/main.py run
  scripts/bench/main.py run --variant no-dynfps --overlay ~/overlays/no-dynfps
  scripts/bench/main.py compare ~/.local/share/retirement-bench/runs/*
  scripts/bench/main.py compare --by change_id ~/.local/share/retirement-bench/runs/*-baseline*
  scripts/bench/main.py db && sqlite3 ~/.local/share/retirement-bench/bench.sqlite
  scripts/bench/main.py normalise RUN... ; scripts/bench/main.py reduce RUN...
  scripts/bench/main.py run --variant profiled --jfr       # async-profiler, 1 ms CPU samples
  scripts/bench/main.py profile RUN --thread "Render thread" --top 20
  scripts/bench/main.py profile RUN --callees GameRenderer.renderLevel --phase movement
"""

import argparse
import fcntl
from pathlib import Path
import signal
import sys

sys.dont_write_bytecode = True  # keep the repo free of __pycache__

import analyse  # noqa: E402
import client  # noqa: E402
import tables  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="stage", required=True)
    for name in ("run", "collect"):
        p = sub.add_parser(name, help="client benchmark run")
        p.add_argument("--client-pack", help="client pack dir; default: nix build .#modpack-client")
        p.add_argument("--server-pack", help="server pack dir; default: nix build .#modpack-server")
        p.add_argument("--overlay", help="dir copied over the client minecraft/ dir after the pack")
        p.add_argument("--variant", default="baseline", help="label that compare groups by")
        p.add_argument("--settle", type=float, default=120,
                       help="seconds at the start spot before measuring; FPS still rises for ~90 s after join")
        p.add_argument("--duration", type=float, default=60, help="seconds per measured phase")
        p.add_argument("--timeout", type=float, default=3600, help="abort collect after this many seconds")
        p.add_argument("--heap", type=int, metavar="MIB", help="Prism maximum heap; default: the bootstrap's")
        p.add_argument("--java", default="nixpkgs#jdk25^out", metavar="INSTALLABLE",
                       help="nix installable of the client's full JDK, e.g. nixpkgs#graalvmPackages.graalvm-ce")
        p.add_argument("--jfr", nargs="?", const="async", choices=("async", "jdk"),
                       help="also record raw/client.jfr: async-profiler (default) or the JDK recorder; "
                            "perturbs results")
    for name in ("normalise", "reduce", "compare", "profile"):
        p = sub.add_parser(name)
        p.add_argument("runs", nargs="+", help="run directories")
        if name == "compare":
            p.add_argument("--by", metavar="KEY", help="also group by this provenance key, e.g. change_id")
    p.add_argument("--thread", default="Render thread")
    p.add_argument("--kind", default="jdk.ExecutionSample", help="sample event type (sampler.csv)")
    p.add_argument("--top", type=int, default=15, help="methods per list")
    p.add_argument("--slow-ms", type=float, default=33.0, help="slow frame: frametime_ms above this")
    p.add_argument("--callees", metavar="METHOD_SUBSTR",
                   help="share of samples by direct callee of the leaf-most matching frame")
    p.add_argument("--phase", action="append", help="only this phase (repeatable)")
    sub.add_parser("db", help="rebuild bench.sqlite from every run directory")
    args = parser.parse_args()

    def interrupt(signum, frame):
        raise KeyboardInterrupt(signal.Signals(signum).name)  # unwinds into collect's cleanup
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGHUP, interrupt)

    if args.stage in ("run", "collect"):
        # One benchmark per machine at a time: runs block until the lock is free.
        lock = open(Path.home() / ".cache/claude-retirement-scratch/bench/lock", "w")
        fcntl.flock(lock, fcntl.LOCK_EX)
        run_dir = client.collect(args.variant, args.client_pack, args.server_pack, args.overlay,
                                 args.settle, args.duration, args.timeout, args.jfr, args.heap, args.java)
        print(run_dir)
        if args.stage == "run":
            client.normalise([run_dir])
            analyse.reduce([run_dir])
            analyse.compare([run_dir])
    elif args.stage == "db":
        runs = sorted(p for p in client.RUNS.iterdir() if p.is_dir())
        for p in (p for p in runs if not (p / "run.csv").exists()):
            print(f"skipped (not normalised): {p}", file=sys.stderr)
        tables.index([p for p in runs if (p / "run.csv").exists()], client.DB)
    elif args.stage == "profile":
        analyse.profile(args.runs, args.thread, args.kind, args.top, args.slow_ms, args.callees, args.phase)
    else:
        stage = {"normalise": client.normalise, "reduce": analyse.reduce,
                 "compare": lambda runs: analyse.compare(runs, args.by)}
        stage[args.stage](args.runs)


if __name__ == "__main__":
    main()
