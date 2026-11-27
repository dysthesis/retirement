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

The nix app (nix/packages/bench.nix) sets every tool and pack path from the
flake, so it runs the working copy's packs. Run it from the working copy: the
run's provenance is the jj revision of the current directory. A --java JDK
needs a GC root (--out-link) and the flake's nixpkgs (--inputs-from .): MangoHud
and GLFW, loaded into its JVM, need a glibc no newer than its own.

Examples:
  nix run .#bench -- run
  nix run .#bench -- run --variant no-dynfps --overlay ~/overlays/no-dynfps
  nix run .#bench -- collect --variant graalvm --heap 8192 --jvm-args "-XX:+UseG1GC -Xlog:gc*:file=gc.log:time,uptime,level,tags" \
      --java $(nix build --inputs-from . --print-out-paths --out-link /tmp/bench-graalvm \
                 nixpkgs#graalvmPackages.graalvm-ce)
  nix run .#bench -- compare ~/.local/share/retirement-bench/runs/*
  nix run .#bench -- compare --by change_id ~/.local/share/retirement-bench/runs/*-baseline*
  nix run .#bench -- db && sqlite3 ~/.local/share/retirement-bench/bench.sqlite
  nix run .#bench -- normalise RUN... ; nix run .#bench -- reduce RUN...
  nix run .#bench -- run --variant profiled --jfr       # async-profiler, 1 ms CPU samples
  nix run .#bench -- profile RUN --thread "Render thread" --top 20
  nix run .#bench -- profile RUN --callees GameRenderer.renderLevel --phase movement
"""

import argparse
import fcntl
import os
from pathlib import Path
import signal
import sys

sys.dont_write_bytecode = True  # keep the repo free of __pycache__

import analyse  # noqa: E402
import client  # noqa: E402
import tables  # noqa: E402

TOOLS = (
    ("--client-pack", "BENCH_CLIENT_PACK", "client pack dir"),
    ("--server-pack", "BENCH_SERVER_PACK", "server pack dir"),
    ("--server-launcher", "BENCH_SERVER_LAUNCHER", "NeoForge server package, with bin/minecraft-server"),
    ("--bootstrap", "BENCH_BOOTSTRAP", "JSON of the bootstrap instance.cfg [General]"),
    ("--java", "BENCH_JAVA", "full JDK dir of the client, e.g. a GraalVM"),
    ("--prism", "BENCH_PRISM", "Prism Launcher package, with bin/prismlauncher"),
    ("--gamescope", "BENCH_GAMESCOPE", "gamescope package"),
    ("--mangohud", "BENCH_MANGOHUD", "MangoHud package"),
    ("--xdotool", "BENCH_XDOTOOL", "xdotool package"),
    ("--async-profiler", "BENCH_ASYNC_PROFILER", "async-profiler package, for --jfr async"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="stage", required=True)
    for name in ("run", "collect"):
        p = sub.add_parser(name, help="client benchmark run")
        p.add_argument("--overlay", help="dir copied over the client minecraft/ dir after the pack")
        p.add_argument("--variant", default="baseline", help="label that compare groups by")
        # 60 runs with Voxy, no shaders (2026-11-26/27): the 10 s rolling median FPS stays
        # within 5% of the stationary median from 116 s after join (median); in 16 runs
        # never in the 120 s. Stationary 2nd half is 2.7% faster than 1st (median).
        p.add_argument("--settle", type=float, default=120,
                       help="seconds at the start spot before measuring; FPS still rises at 120 s after join")
        p.add_argument("--duration", type=float, default=60, help="seconds per measured phase")
        p.add_argument("--timeout", type=float, default=3600, help="abort collect after this many seconds")
        p.add_argument("--heap", type=int, metavar="MIB", help="Prism maximum heap; default: the bootstrap's")
        p.add_argument("--jvm-args", metavar="ARGS", help="replace the bootstrap's JVM arguments (GC choice, flags)")
        p.add_argument("--jfr", nargs="?", const="async", choices=("async", "jdk"),
                       help="also record raw/client.jfr: async-profiler (default) or the JDK recorder; "
                            "perturbs results")
        # Store paths from the nix app (nix/packages/bench.nix); a flag replaces one.
        for flag, env, what in TOOLS:
            p.add_argument(flag, metavar="PATH", default=os.environ.get(env),
                           required=env not in os.environ and flag != "--async-profiler",
                           help=f"{what}; default: ${env}")
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
    if args.stage in ("run", "collect") and args.jfr == "async" and not args.async_profiler:
        parser.error("--jfr async needs --async-profiler or $BENCH_ASYNC_PROFILER")

    def interrupt(signum, frame):
        raise KeyboardInterrupt(signal.Signals(signum).name)  # unwinds into collect's cleanup
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGHUP, interrupt)

    if args.stage in ("run", "collect"):
        # One benchmark per machine at a time: runs block until the lock is free.
        lock = open(Path.home() / ".cache/claude-retirement-scratch/bench/lock", "w")
        fcntl.flock(lock, fcntl.LOCK_EX)
        run_dir = client.collect(**{k: v for k, v in vars(args).items() if k != "stage"})
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
