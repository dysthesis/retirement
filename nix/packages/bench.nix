# Client benchmark harness (scripts/bench) with every tool and artefact as a store path.
# One nixpkgs for all of them: MangoHud, async-profiler and GLFW load into the JVM,
# so Prism, Java, MangoHud and gamescope must share a glibc.
{
  python3,
  writeShellScriptBin,
  writeText,
  prismlauncher,
  gamescope,
  mangohud,
  xdotool,
  async-profiler,
  jdk25,
  clientPack,
  serverPack,
  serverLauncher,
  bootstrapGeneral,
}: let
  # Add Python libraries here; the harness itself is stdlib only.
  python = python3.withPackages (ps: []);
in
  writeShellScriptBin "bench" ''
    export BENCH_PRISM=${prismlauncher}
    export BENCH_GAMESCOPE=${gamescope}
    export BENCH_MANGOHUD=${mangohud}
    export BENCH_XDOTOOL=${xdotool}
    export BENCH_ASYNC_PROFILER=${async-profiler}
    export BENCH_JAVA=${jdk25}
    export BENCH_CLIENT_PACK=${clientPack}
    export BENCH_SERVER_PACK=${serverPack}
    export BENCH_SERVER_LAUNCHER=${serverLauncher}
    export BENCH_BOOTSTRAP=${writeText "bench-bootstrap-general.json" (builtins.toJSON bootstrapGeneral)}
    exec ${python}/bin/python3 ${../../scripts/bench}/main.py "$@"
  ''
