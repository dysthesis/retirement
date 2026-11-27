"""Client benchmark: collect (side effects) and normalise (raw files -> tables).

collect: fresh server from a cached pregenerated world template, fresh client
instance from the pack (plus optional overlay), Prism Launcher -> gamescope
(headless backend, 1920x1080, real GPU, no window) -> MangoHud (per-frame CSV)
-> Minecraft. The scenario is driven from the server console:
  settle      at START until chunks and LODs near the spot arrive
  stationary  at START, fixed rotation
  movement    absolute teleports along +x at SPEED blocks/s, over terrain the
              client has not loaded (pregenerated on the server)
The client starts with the server and loads while the server starts, so
client_launch precedes server_ready and launch timings include CPU contention
with the server start: they are not comparable with runs before this change.
collect writes raw/ (run, input, override, phase, event, sample tables and
raw logs). normalise reads raw/ and writes all tables to the run directory.
"""

import csv
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import threading
import time

import jfr
import tables as T

# All mutable state lives under WORK. remove() deletes only the three fixed trees.
WORK = Path.home() / ".cache/claude-retirement-scratch/bench"
PRISM = WORK / "prism"
INSTANCE = WORK / "prism/instances/bench"
SERVER = WORK / "server"
TEMPLATE_BUILD = WORK / "template-build"
TEMPLATES = WORK / "templates"
# Durable results, outside the scratch tree; bench.sqlite is derived from RUNS (main.py db).
RUNS = Path.home() / ".local/share/retirement-bench/runs"
DB = Path.home() / ".local/share/retirement-bench/bench.sqlite"
REAL_PRISM = Path.home() / ".local/share/PrismLauncher"
REAL_INSTANCE = REAL_PRISM / "instances/Retirement Home"

PLAYER = "Bench"
PORT = 25611
MANGOHUD_SOCKET = "mangohud-bench"  # abstract unix socket for start/stop logging
SERVER_JVM = ["-Xms6G", "-Xmx10G"]  # 8 GiB fails with OutOfMemoryError while loading level.dat
# Pregenerated square; covers the flight path (x 0..1500, z 0) plus view distance.
PREGEN = {"center_x": 750, "center_z": 0, "radius": 1500}
START = (0.5, 200.0, 0.5, -90.0, 15.0)  # x y z yaw pitch: above terrain, facing +x
SPEED = 25.0  # blocks/s, elytra-like
TP_HZ = 20  # one absolute teleport per server tick

# Run at join so every run has the same light, sky and weather.
WORLD_COMMANDS = ("gamerule doDaylightCycle false", "time set 6000", "gamerule doWeatherCycle false", "weather clear")
# Client options.txt overrides; every other option is the pack's options.txt.
OPTIONS = {
    "enableVsync": "false",  # measure render cost, not display refresh
    "maxFps": "260",  # 260 = "Unlimited"
    "fullscreen": "false",
    "pauseOnLostFocus": "false",  # no pause menu if focus moves
    "onboardAccessibility": "false",  # skip the first-launch accessibility screen
    "tutorialStep": "none",  # no tutorial toasts
    "narrator": "0",
    "skipMultiplayerWarning": "true",
    "joinedFirstServer": "true",  # no social-interactions toast
    "soundCategory_master": "0.0",
}
# instance.cfg overrides on top of the real instance's [General] section.
INSTANCE_CFG = {
    "name": "bench",
    "PreLaunchCommand": "",  # the real one installs the live server's pack over ours
    "PostExitCommand": "",
    "OverrideWindow": "true",
    "LaunchMaximized": "false",
    "MinecraftWinWidth": "1920",
    "MinecraftWinHeight": "1080",
}
# Players import the bootstrap ZIP (nix/bootstrap) and set Java 25 (its README).
# True: the bootstrap's [General] (memory, JvmArgs; --bootstrap) and the --java JDK
# replace the user's real instance.cfg, whose JVM settings are stale.
BOOTSTRAP = True
# prismlauncher.cfg overrides on top of the user's global Prism settings.
# The themes are built in: the user's custom themes are not in the isolated
# root, and a missing theme opens the setup wizard, which blocks the launch.
PRISM_CFG = {"QuitAfterGameStop": "true", "ShowConsole": "false", "ShowConsoleOnError": "false",
             "EnableMangoHud": "false", "WrapperCommand": "", "IgnoreJavaWizard": "true",
             "ApplicationTheme": "system", "IconTheme": "pe_colored"}
GAME_ENV = {"ALSOFT_DRIVERS": "null"}  # OpenAL null backend: no audio device needed
# Server overrides; view and simulation distance stay at the shipped defaults.
SERVER_PROPERTIES = {
    "level-seed": "86204277",
    "online-mode": "false",
    "server-port": str(PORT),
    "white-list": "false",
    "max-players": "10",
    "difficulty": "hard",
    "motd": "bench",
    "enable-status": "true",
}
# Written into the server after the pack. BlueMap would otherwise download
# assets and render the world on server threads during the measurement.
SERVER_FILES = {"config/bluemap/core.conf": 'accept-download: false\ndata: "bluemap"\nmetrics: false\n'}
COLLECTED = ("run", "input", "override", "phase", "event", "sample", "provenance")
# Profilers (--jfr); both write raw/client.jfr. async-profiler: CPU-time samples
# of every thread, with native (C, driver) frames. The kernel forbids perf_events
# (perf_event_paranoid=3), so "cpu" uses its ctimer engine: no kernel frames, and
# time a thread spends blocked (e.g. waiting on the GPU) is not sampled.
ASYNC_PROFILER = "start,event=cpu,interval=1ms,jfr,file={raw}/client.jfr"
JDK_JFR = "filename={raw}/client.jfr,settings=profile"  # Java-only stacks; 10/20 ms periods


# ---------------------------------------------------------------- files and processes

def jj(*args):
    return subprocess.run(["jj", "--ignore-working-copy", "--no-pager", "--color=never", *args],
                          check=True, capture_output=True).stdout


def provenance():
    """Source revision of the current directory's jj repo as (key, value): jj snapshots
    the working copy once, here; later reads use that snapshot. diff_sha256 is of
    `jj diff --git` (@ vs @-)."""
    subprocess.run(["jj", "util", "snapshot"], check=True, capture_output=True)
    ids = jj("log", "--no-graph", "-r", "@", "-T", 'change_id ++ " " ++ commit_id ++ " " ++ parents.map(|c| c.commit_id()).join(",")')
    change_id, commit_id, parent = ids.decode().split()
    diff = jj("diff", "--git")
    return [("change_id", change_id), ("commit_id", commit_id), ("parent_commit_id", parent),
            ("diff_sha256", hashlib.sha256(diff).hexdigest()), ("diff_bytes", str(len(diff)))]


def tree_hash(root):
    digest = hashlib.sha256()
    for path in sorted(p for p in Path(root).rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def remove(path):
    """Delete one of the fixed scratch trees; refuse every other path."""
    if path not in (INSTANCE, SERVER, TEMPLATE_BUILD):
        raise ValueError(f"refusing to delete {path}")
    if path.exists():
        subprocess.run(["rm", "-rf", "--one-file-system", "--", str(path)], check=True)


def copy_tree(src, dst):
    """Copy contents of src into dst (reflinks on btrfs; store files become writable)."""
    dst.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "-r", "--reflink=auto", "--no-preserve=mode,ownership", f"{src}/.", str(dst)],
                   check=True)


# Every process collect starts inherits this variable; cleanup finds them by it.
MARKER = b"RETIREMENT_BENCH=1"


def child_env(base=os.environ):
    return {k: v for k, v in base.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")} | {"RETIREMENT_BENCH": "1"}


def own_processes():
    """PIDs of processes that carry MARKER in their environment."""
    found = []
    for entry in Path("/proc").iterdir():
        try:
            if entry.name.isdigit() and MARKER in (entry / "environ").read_bytes().split(b"\0"):
                found.append(int(entry.name))
        except OSError:
            continue
    return found


def signal_all(procs, sig):
    for p in procs:
        try:
            os.killpg(p.pid, sig)
        except ProcessLookupError:
            pass
    for pid in own_processes():
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass


def kill_all(procs, grace=30):
    """TERM, wait, then KILL every process group we started and every process under WORK."""
    signal_all(procs, signal.SIGTERM)
    end = time.time() + grace
    while own_processes() and time.time() < end:
        time.sleep(0.5)
    signal_all(procs, signal.SIGKILL)
    for p in procs:
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            pass
    time.sleep(1)
    left = own_processes()
    if left:
        raise RuntimeError(f"processes still running: {left}")


# A JVM whose main thread died can keep running; treat these log lines as failure.
# The NeoForge early-display error waits for a click in a dialog nobody sees.
# Quick play does not retry a refused connect; the client would wait in a menu.
FATAL = re.compile(r'Exception in thread "main"|java\.lang\.OutOfMemoryError|---- Minecraft Crash Report ----'
                   r"|early-display-errors|!!\[Fatal\]!|Couldn't connect to server")


def read_text(path):
    return path.read_text(errors="replace") if path.exists() else ""


def wait_for(path, pattern, timeout, procs, deadline, watch=()):
    """Poll a log until `pattern` matches; fail on FATAL in it or in `watch` logs,
    or if a started process exits."""
    regex = re.compile(pattern)
    end = min(time.time() + timeout, deadline)
    while time.time() < end:
        if regex.search(read_text(path)):
            return
        for log in (path, *watch):
            if FATAL.search(read_text(log)):
                raise RuntimeError(f"fatal error in {log}")
        dead = [p.args for p in procs if p.poll() is not None]
        if dead:
            raise RuntimeError(f"exited early: {dead}")
        time.sleep(0.5)
    raise TimeoutError(f"no {pattern!r} in {path}")


def start_server(launcher, directory, log):
    # The launcher puts its args before @unix_args.txt, so pass JVM args only (no "nogui").
    return subprocess.Popen([f"{launcher}/bin/minecraft-server", *SERVER_JVM], cwd=directory, env=child_env(),
                            stdin=subprocess.PIPE, stdout=log.open("w"), stderr=subprocess.STDOUT,
                            start_new_session=True, text=True)


def console(proc, *commands):
    for command in commands:
        proc.stdin.write(command + "\n")
    proc.stdin.flush()


def stop_server(proc):
    if proc.poll() is None:
        console(proc, "stop")
        try:
            proc.wait(180)
        except subprocess.TimeoutExpired:
            pass


def write_server_files(directory):
    (directory / "server.properties").write_text("".join(f"{k}={v}\n" for k, v in SERVER_PROPERTIES.items()))
    (directory / "eula.txt").write_text("eula=true\n")
    for rel, text in SERVER_FILES.items():
        (directory / rel).parent.mkdir(parents=True, exist_ok=True)
        (directory / rel).write_text(text)


def template_for(server_pack, launcher, deadline):
    """Pregenerated server directory for this pack and settings, built once."""
    key = hashlib.sha256(json.dumps([tree_hash(server_pack), SERVER_PROPERTIES, SERVER_FILES, PREGEN])
                         .encode()).hexdigest()[:16]
    template = TEMPLATES / key
    if template.exists():
        return template
    remove(TEMPLATE_BUILD)
    copy_tree(server_pack, TEMPLATE_BUILD)
    write_server_files(TEMPLATE_BUILD)
    log = TEMPLATE_BUILD / "pregen.out"
    proc = start_server(launcher, TEMPLATE_BUILD, log)
    try:
        wait_for(log, r"Done \([0-9.]+s\)", 900, [proc], deadline)
        console(proc, "chunky world minecraft:overworld", "chunky shape square",
                f"chunky center {PREGEN['center_x']} {PREGEN['center_z']}",
                f"chunky radius {PREGEN['radius']}", "chunky start")
        wait_for(log, r"\[Chunky\] Task finished for minecraft:overworld", 4 * 3600, [proc], deadline)
        stop_server(proc)
    finally:
        kill_all([proc])
    TEMPLATES.mkdir(parents=True, exist_ok=True)
    TEMPLATE_BUILD.rename(template)
    return template


def ini_general(text):
    """[General] key=value pairs of a Prism .cfg, as a dict."""
    general = text.split("\n[UI]")[0].split("\n", 1)[1]
    return dict(line.partition("=")[::2] for line in general.splitlines() if "=" in line)


def write_ini(path, general):
    path.write_text("[General]\n" + "".join(f"{k}={v}\n" for k, v in general.items()))


def bootstrap_general(path):
    """The bootstrap's instance.cfg [General] (a JSON file), with values as Prism reads them."""
    general = {k: str(v).lower() if isinstance(v, bool) else str(v)
               for k, v in json.loads(Path(path).read_text()).items()}
    return general | {"JvmArgs": f'"{general["JvmArgs"]}"'}  # QSettings splits unquoted values at commas


def java_version(jdk):
    return subprocess.run([f"{jdk}/bin/java", "-version"], capture_output=True, text=True,
                          check=True).stderr.splitlines()[0]


def prepare_prism(raw, client_pack, overlay, jfr, gamescope, mangohud, profiler, bootstrap, jdk=None,
                  heap=None, jvm_args=None):
    """Isolated Prism root with an offline account; shares libraries/assets read-only."""
    PRISM.mkdir(parents=True, exist_ok=True)
    if not (PRISM / "assets").exists():
        (PRISM / "assets").symlink_to(REAL_PRISM / "assets")
    # libraries must be real paths: a symlinked jar resolves to two module-path
    # locations and the NeoForge bootstrap refuses to start.
    for name in ("libraries", "meta"):
        if not (PRISM / name).exists():
            copy_tree(REAL_PRISM / name, PRISM / name)
    # Prism refuses Java 25 for Minecraft 1.21.1 (compatibleJavaMajors [21]) unless told.
    prism_cfg = PRISM_CFG | ({"IgnoreJavaCompatibility": "true"} if jdk else {})
    write_ini(PRISM / "prismlauncher.cfg", ini_general((REAL_PRISM / "prismlauncher.cfg").read_text()) | prism_cfg)
    # Prism launches only if some Microsoft account owns Minecraft (else demo mode
    # or a dialog). It may refresh the copy's tokens; the game itself runs offline
    # as PLAYER (-o), and the server has online-mode=false.
    shutil.copyfile(REAL_PRISM / "accounts.json", PRISM / "accounts.json")
    (PRISM / "accounts.json").chmod(0o600)

    remove(INSTANCE)
    game = INSTANCE / "minecraft"
    copy_tree(client_pack, game)
    if overlay:
        copy_tree(Path(overlay), game)
    shipped = (game / "options.txt").read_text().splitlines()
    options = dict(line.split(":", 1) for line in shipped if ":" in line) | OPTIONS
    (game / "options.txt").write_text("".join(f"{k}:{v}\n" for k, v in options.items()))

    # Wrapper: gamescope headless -> MangoHud -> java. Never on the user's display.
    hud = f"output_folder={raw}/mangohud,control={MANGOHUD_SOCKET},log_interval=0,no_display"
    env = GAME_ENV | {"MANGOHUD_CONFIG": hud}
    (raw / "mangohud").mkdir()
    wrapper = PRISM / "wrap.sh"
    wrapper.write_text(
        f"#!/bin/sh\nunset DISPLAY WAYLAND_DISPLAY\nexec >{raw}/game.out 2>&1\n"
        f"exec env {' '.join(f'{k}={shlex.quote(v)}' for k, v in env.items())} "
        f"{gamescope}/bin/gamescope --backend headless -w 1920 -h 1080 -W 1920 -H 1080 "
        f"-- {mangohud}/bin/mangohud \"$@\"\n")
    wrapper.chmod(0o755)

    instance = dict(INSTANCE_CFG, WrapperCommand=str(wrapper))
    general = ini_general((REAL_INSTANCE / "instance.cfg").read_text())
    if jdk:
        general = bootstrap_general(bootstrap)
        instance = general | instance | {"JavaPath": f"{jdk}/bin/java", "AutomaticJava": "false",
                                         "OverrideJavaLocation": "true", "IgnoreJavaCompatibility": "true"}
    if heap:  # a player's smaller Prism maximum heap
        instance["MaxMemAlloc"] = str(heap)
    if jvm_args:  # replaces the bootstrap's; keep its -Xlog:gc* for the gc tables
        instance["JvmArgs"] = f'"{jvm_args}"'
    if jfr:
        agent = {"async": f"-agentpath:{profiler}/lib/libasyncProfiler.so={ASYNC_PROFILER.format(raw=raw)}",
                 "jdk": f"-XX:StartFlightRecording={JDK_JFR.format(raw=raw)}"}[jfr]
        instance["JvmArgs"] = '"' + instance.get("JvmArgs", general["JvmArgs"]).strip('"') + f' {agent}"'
    write_ini(INSTANCE / "instance.cfg", general | instance)
    shutil.copyfile(REAL_INSTANCE / "mmc-pack.json", INSTANCE / "mmc-pack.json")
    return ([("options.txt", k, v) for k, v in OPTIONS.items()] +
            [("instance.cfg", k, v) for k, v in instance.items()] +
            [("prismlauncher.cfg", k, v) for k, v in prism_cfg.items()] +
            [("env", k, v) for k, v in env.items()])


def client_pid():
    """The java process running inside gamescope (the server's java is not)."""
    for pid in own_processes():
        try:
            argv0 = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[0]
            environ = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
        except OSError:
            continue
        if argv0.endswith(b"/java") and any(e.startswith(b"GAMESCOPE_WAYLAND_DISPLAY=") for e in environ):
            return pid
    raise RuntimeError("client java process not found")


def screenshot(xdotool, pid):
    """Press F2 in the game's own nested Xwayland (gamescope), never the user's display."""
    environ = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    display = next(e.split(b"=", 1)[1].decode() for e in environ if e.startswith(b"DISPLAY="))
    if not any(e.startswith(b"GAMESCOPE_WAYLAND_DISPLAY=") for e in environ) or display in (":0", os.environ.get("DISPLAY")):
        raise RuntimeError(f"refusing to send keys to display {display}")
    env = child_env() | {"DISPLAY": display}
    subprocess.run([f"{xdotool}/bin/xdotool", "key", "F2"], env=env, check=True, timeout=10)
    time.sleep(3)


def status_mib(pid, field):
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith(field + ":"):
            return int(line.split()[1]) / 1024
    raise ValueError(field)


# amdgpu sysfs counters, read by the sampler: metric -> (file, scale). MangoHud
# reads no GPU metrics under headless gamescope. gpu_busy_percent is the
# firmware's own short-window average; VRAM use is of the whole GPU, not only
# the client's.
GPU_FILES = {"gpu_busy_pct": ("gpu_busy_percent", 1), "vram_used_mib": ("mem_info_vram_used", 1 / 2**20)}
SAMPLE_HZ = 10  # GPU counters; client RSS every SAMPLE_HZ-th sample (1 Hz)


def gpu_device():
    """The first DRM card with amdgpu counters (here card1, the only GPU), or None."""
    return next((p.parent for p in sorted(Path("/sys/class/drm").glob("card*/device/gpu_busy_percent"))), None)


def save_raw(raw):
    game = INSTANCE / "minecraft"
    for name in ("logs", "crash-reports", "screenshots"):
        if (game / name).exists():
            copy_tree(game / name, raw / "client" / name)
    for path in game.glob("gc.log*"):
        (raw / "client").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, raw / "client" / path.name)
    for src, dst in ((PRISM / "logs", "prism-logs"), (SERVER / "logs", "server-logs")):
        if src.exists():
            copy_tree(src, raw / dst)


def collect(*, variant, client_pack, server_pack, overlay, settle, duration, timeout, jfr, heap, java,
            jvm_args, server_launcher, bootstrap, prism, gamescope, mangohud, xdotool, async_profiler):
    t0 = time.time()
    run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + variant
    raw = RUNS / run_id / "raw"
    raw.mkdir(parents=True)
    deadline = t0 + timeout
    rows = {name: [] for name in COLLECTED}
    rows["run"].append((run_id, variant, t0))

    def event(kind, value=""):
        rows["event"].append((run_id, time.time() - t0, kind, value))
        print(f"[{time.time() - t0:7.1f}s] {kind} {value}", flush=True)

    event("collect_start")
    rows["provenance"] = [(run_id, k, v) for k, v in provenance()]
    if rows["provenance"][-1][2] != "0":  # diff_bytes
        event("warning", "jj diff of @ is not empty: the run's source is not a commit alone")
    kill_all([])  # leftovers of an earlier harness that was SIGKILLed
    # MangoHud, async-profiler and Prism's GLFW are loaded into the game's JVM, so
    # they need a glibc no newer than the JDK's: take all from one nixpkgs (the nix app).
    client_pack, server_pack = Path(client_pack), Path(server_pack)
    profiler = async_profiler if jfr == "async" else None
    jdk = java if BOOTSTRAP else None  # a full JDK: the client needs its AWT libraries
    template = template_for(server_pack, server_launcher, deadline)
    for role, path in [("client_pack", client_pack), ("server_pack", server_pack)] + \
                      ([("client_overlay", Path(overlay))] if overlay else []):
        rows["input"].append((run_id, role, str(path), tree_hash(path)))
    rows["input"] += [(run_id, "world_template", str(template), template.name),
                      (run_id, "gamescope", str(gamescope), ""), (run_id, "mangohud", str(mangohud), ""),
                      (run_id, "prism", str(prism), "")]
    rows["input"] += [(run_id, "async_profiler", str(profiler), "")] if profiler else []
    rows["input"] += [(run_id, "java", f"{jdk}/bin/java", "")] if jdk else []
    overrides = [("server.properties", k, v) for k, v in SERVER_PROPERTIES.items()]
    overrides += [("server_file", k, v) for k, v in SERVER_FILES.items()]
    overrides += [("server_console", c, "") for c in WORLD_COMMANDS]
    overrides += [("java", "version", java_version(jdk))] if jdk else []
    overrides += prepare_prism(raw, client_pack, overlay, jfr, gamescope, mangohud, profiler, bootstrap, jdk, heap,
                               jvm_args)
    rows["override"] = [(run_id, *o) for o in overrides]

    remove(SERVER)
    copy_tree(template, SERVER)
    procs = []
    stop = threading.Event()
    env = child_env() | {"QT_QPA_PLATFORM": "offscreen"}  # Prism's own UI never reaches a display

    try:
        server = start_server(server_launcher, SERVER, raw / "server.out")
        procs.append(server)
        # Client and server start together. In 87 sequential runs (2026-11-26/27) the
        # client took >= 68 s from launch to its connect, the server <= 46 s to "Done";
        # it listens >= 6.5 s before "Done". A connect that comes too early fails the run (FATAL).
        event("client_launch")
        procs.append(subprocess.Popen(
            [f"{prism}/bin/prismlauncher", "-d", str(PRISM), "-l", "bench", "-o", PLAYER, "-s", f"127.0.0.1:{PORT}"],
            cwd=PRISM, env=env, stdout=(raw / "prism.out").open("w"), stderr=subprocess.STDOUT,
            start_new_session=True))
        wait_for(raw / "server.out", r"Done \([0-9.]+s\)", 900, procs, deadline)
        event("server_ready")
        wait_for(raw / "server.out", rf"{PLAYER} joined the game", 900, procs, deadline, [raw / "game.out"])
        event("player_join")
        pid = client_pid()

        gpu = gpu_device()
        rows["input"] += [(run_id, "gpu_sysfs", str(gpu.resolve()), "")] if gpu else []

        def sample():
            tick = 0
            while not stop.wait(1 / SAMPLE_HZ):
                tick += 1
                now = time.time() - t0
                for metric, (name, scale) in GPU_FILES.items() if gpu else ():
                    try:
                        rows["sample"].append((run_id, now, metric, int((gpu / name).read_text()) * scale))
                    except (OSError, ValueError):
                        pass
                if tick % SAMPLE_HZ == 0:
                    try:
                        rows["sample"].append((run_id, now, "client_rss_mib", status_mib(pid, "VmRSS")))
                    except (OSError, ValueError):  # gone, or a zombie without VmRSS
                        return
        threading.Thread(target=sample, daemon=True).start()

        x, y, z, yaw, pitch = START
        console(server, *WORLD_COMMANDS, f"gamemode spectator {PLAYER}", f"tp {PLAYER} {x} {y} {z} {yaw} {pitch}")
        hud = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        hud.connect("\0" + MANGOHUD_SOCKET)
        hud.sendall(b":logging=1;")
        event("mangohud_log_start")

        def phase(name, seconds, step=lambda dt: None):
            start = time.time()
            while time.time() < start + seconds:
                if time.time() > deadline or any(p.poll() is not None for p in procs):
                    raise RuntimeError(f"aborted in phase {name}")
                step(time.time() - start)
                time.sleep(1 / TP_HZ)
            rows["phase"].append((run_id, name, start - t0, time.time() - t0))
            event("phase_end", name)

        phase("settle", settle)
        phase("stationary", duration)
        phase("movement", duration,
              lambda dt: console(server, f"tp {PLAYER} {x + SPEED * dt:.3f} {y} {z} {yaw} {pitch}"))
        hud.sendall(b":logging=0;")
        event("mangohud_log_stop")
        rows["sample"].append((run_id, time.time() - t0, "client_hwm_mib", status_mib(pid, "VmHWM")))
        if jdk:  # live set after a full GC; after the measured phases, so it perturbs none
            histo = subprocess.run([f"{jdk}/bin/jcmd", str(pid), "GC.class_histogram"],
                                   capture_output=True, text=True, timeout=120).stdout.split()
            rows["sample"].append((run_id, time.time() - t0, "client_live_heap_mib",
                                   int(histo[histo.index("Total") + 2]) / 2**20))
        hud.close()  # MangoHud stops on the next frame; jcmd and the 3 s screenshot precede SIGTERM
        screenshot(xdotool, pid)
        event("screenshot")
        os.kill(pid, signal.SIGTERM)
        console(server, "stop")  # the two stop in parallel; neither needs the other
        end = time.time() + 90
        while Path(f"/proc/{pid}").exists() and time.time() < end:
            time.sleep(0.5)
        event("client_stopped")  # Prism itself stays up; kill_all stops it
        try:
            server.wait(180)
        except subprocess.TimeoutExpired:
            pass
        event("server_stopped")
    finally:
        stop.set()
        kill_all(procs)
        save_raw(raw)
        event("collect_end")
        for name in COLLECTED:
            T.write(raw / f"{name}.csv", name, T.from_rows(name, rows[name]))
    return RUNS / run_id


# ---------------------------------------------------------------- normalise

def mangohud_frames(run_id, raw, log_stops):
    """MangoHud CSV: 2 system-info lines, then a header; elapsed = ns since its log start.

    MangoHud starts logging up to ~20 s after the socket command (while the
    client is still joining), but stops on the next frame. So the last row is
    aligned with the mangohud_log_stop event."""
    files = sorted(f for f in (raw / "mangohud").glob("*.csv") if not f.name.endswith("_summary.csv"))
    rows = []
    for path, t_stop in zip(files, sorted(log_stops), strict=True):
        with path.open(newline="") as handle:
            data = list(csv.DictReader(handle.readlines()[2:]))
        last = int(data[-1]["elapsed"])
        rows += [(run_id, t_stop - (last - int(r["elapsed"])) / 1e9, float(r["frametime"])) for r in data]
    return rows


# -Xlog decorations time,uptime,level,tags, e.g.
# [2026-11-26T12:00:00.123+1100][12.345s][info][gc,phases   ] GC(3) Y: Pause Mark Start 0.010ms
# ZGC: "Allocation Stall (Render thread) 1.234ms"; the thread is captured for stalls only.
GC_LINE = re.compile(r"^\[([^\]]+)\]\[[^\]]*\]\[[^\]]*\]\[gc[^\]]*\].*?\b(Pause|Allocation Stall)\b"
                     r"(?: \(([^)]*)\))?.*?([0-9.]+)ms\s*$")
GC_KIND = {"Pause": "pause", "Allocation Stall": "stall"}
# ZGC, at the end of each cycle (M = MiB):
# [...][gc          ] GC(86) Minor Collection (Allocation Rate) 11530M(94%)->6396M(52%) 0.291s
GC_CYCLE = re.compile(r"^\[([^\]]+)\]\[[^\]]*\]\[[^\]]*\]\[gc\s*\] GC\(\d+\) (Minor|Major) Collection \((.*)\) "
                      r"(\d+)M\(\d+%\)->(\d+)M\(\d+%\) ([0-9.]+)s\s*$")


def gc_lines(raw, t0, pattern):
    """(t, match) for every client gc.log line that matches."""
    for path in sorted((raw / "client").glob("gc.log*")):
        for m in filter(None, map(pattern.match, path.read_text(errors="replace").splitlines())):
            yield datetime.datetime.strptime(m[1], "%Y-%m-%dT%H:%M:%S.%f%z").timestamp() - t0, m


def gc_pauses(run_id, raw, t0):
    return [(run_id, t, float(m[4]), GC_KIND[m[2]], m[3] if m[2] == "Allocation Stall" else "")
            for t, m in gc_lines(raw, t0, GC_LINE)]


def gc_cycles(run_id, raw, t0):
    return [(run_id, t, m[2].lower(), m[3], float(m[4]), float(m[5]), float(m[6]))
            for t, m in gc_lines(raw, t0, GC_CYCLE)]


# Client log line -> event kind. "Connecting to" is the quick-play connect that
# follows the end of resource loading, i.e. when the main menu would appear.
CLIENT_MARKERS = {"client_menu": re.compile(r"Connecting to 127\.0\.0\.1")}
LOG_STAMP = re.compile(r"^\[(\d\d\w{3}\d{4} \d\d:\d\d:\d\d\.\d{3})\]")


def client_events(run_id, raw, t0):
    rows = []
    path = raw / "client/logs/latest.log"
    lines = path.read_text(errors="replace").splitlines() if path.exists() else []
    for line in lines:
        stamp = LOG_STAMP.match(line)
        for kind in (k for k, pattern in CLIENT_MARKERS.items() if stamp and pattern.search(line)):
            wall = datetime.datetime.strptime(stamp[1], "%d%b%Y %H:%M:%S.%f").timestamp()
            rows.append((run_id, wall - t0, kind, ""))
    return rows


def profile_tables(run_id, raw, t0):
    """raw/client.jfr -> stack_sample, stack_frame (call tree), stack_method, sampler rows."""
    path = raw / "client.jfr"
    found, samplers = jfr.samples(path) if path.exists() else ([], {})
    nodes, leaves, methods, frames, rows = {}, {}, {}, [], []
    for epoch, thread, kind, stack in found:
        if stack not in leaves:
            node = -1
            for frame in reversed(stack):  # root first
                method_id = methods.setdefault(frame, len(methods))
                key = (node, method_id)
                if key not in nodes:
                    nodes[key] = len(nodes)
                    frames.append((run_id, nodes[key], node, method_id))
                node = nodes[key]
            leaves[stack] = node
        rows.append((run_id, epoch - t0, thread, kind, leaves[stack]))
    return (rows, frames, [(run_id, i, *frame) for frame, i in methods.items()],
            [(run_id, kind, *s) for kind, s in samplers.items()])


def normalise(run_dirs):
    for d in map(Path, run_dirs):
        raw = d / "raw"
        t = {name: T.read(raw / f"{name}.csv", name) for name in COLLECTED}
        run_id, t0 = t["run"]["run_id"][0], t["run"]["t0"][0]
        ev = t["event"]
        stops = [ev["t"][i] for i in T.group(ev, "kind").get(("mangohud_log_stop",), [])]
        t["event"] = T.concat("event", [ev, T.from_rows("event", client_events(run_id, raw, t0))])
        t["frame"] = T.from_rows("frame", mangohud_frames(run_id, raw, stops))
        t["gc_pause"] = T.from_rows("gc_pause", gc_pauses(run_id, raw, t0))
        t["gc_cycle"] = T.from_rows("gc_cycle", gc_cycles(run_id, raw, t0))
        for name, rows in zip(("stack_sample", "stack_frame", "stack_method", "sampler"), profile_tables(run_id, raw, t0)):
            t[name] = T.from_rows(name, rows)
        for name, table in t.items():
            T.write(d / f"{name}.csv", name, table)
