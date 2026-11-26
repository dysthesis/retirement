"""reduce: tables -> phase_metric/run_metric. compare: N runs x M variants -> table.

A reducer is one function: dict of tables -> list of metric rows. To add one,
write it and append it to PHASE_REDUCERS (rows: run_id, phase, metric, value)
or RUN_REDUCERS (rows: run_id, metric, value). profile: stack samples -> table.
"""

import bisect
import collections
import itertools
import hashlib
import math
import statistics
import sys

import tables as T

INPUTS = ("run", "phase", "event", "sample", "frame", "gc_pause", "gc_cycle")


def frame_metrics(t):
    rows = []
    ft = t["frame"]["frametime_ms"]
    for (run_id, phase), idx in T.within(t["frame"], t["phase"]).items():
        s = sorted(ft[i] for i in idx)
        p99, p999 = T.quantile(s, 0.99), T.quantile(s, 0.999)
        values = {
            "frames": len(s),
            "mean_fps": 1000 * len(s) / sum(s),
            "median_ms": T.quantile(s, 0.5),
            "p99_ms": p99,
            "p999_ms": p999,
            "low1_fps": 1000 / p99,  # "1% low" defined as 1000 / p99 frame time
            "low01_fps": 1000 / p999,
            "max_ms": s[-1],
            "over33ms_n": sum(x > 33.3 for x in s),
            "over50ms_n": sum(x > 50 for x in s),
        }
        rows += [(run_id, phase, k, float(v)) for k, v in values.items() if s]
    return rows


def gc_metrics(t):
    """Per phase and GC kind ("pause" or "stall"): count, total (0 if none), max."""
    rows = []
    gc = t["gc_pause"]
    for (run_id, phase), idx in T.within(gc, t["phase"]).items():
        kinds = T.group(T.take(gc, idx), "kind")
        for kind in ("pause", "stall"):
            ms = [gc["pause_ms"][idx[i]] for i in kinds.get((kind,), [])]
            rows += [(run_id, phase, f"gc_{kind}_n", float(len(ms))),
                     (run_id, phase, f"gc_{kind}_total_ms", float(sum(ms)))]
            rows += [(run_id, phase, f"gc_{kind}_max_ms", max(ms))] if ms else []
    return rows


def gc_cycle_metrics(t):
    """Per phase, from ZGC cycles that end in it: cycles per minute by kind, heap
    after GC, the share of phase time with a cycle running (concurrent GC threads
    compete with the game for CPU), and the allocation rate. The rate is the heap
    growth from the end of one cycle to the start of the next, over the gaps
    between cycles (both ends in the phase); it assumes the same rate while a
    cycle runs. Cycles that overlap (minor during major) give no gap."""
    rows = []
    gc, ph = t["gc_cycle"], t["phase"]
    cycles = {key: sorted(idx, key=gc["t"].__getitem__) for key, idx in T.group(gc, "run_id").items()}
    for j, (run_id, phase, a, b) in enumerate(zip(*(ph[c] for c in ("run_id", "phase", "t_start", "t_end")))):
        idx = cycles.get((run_id,), [])
        ends = [gc["t"][i] for i in idx]
        inside = idx[bisect.bisect_left(ends, a):bisect.bisect_left(ends, b)]
        for kind in ("minor", "major"):
            n = sum(gc["kind"][i] == kind for i in inside)
            rows.append((run_id, phase, f"gc_{kind}_per_min", 60 * n / (b - a)))
        after = [gc["heap_after_mib"][i] for i in inside]
        if after:
            rows += [(run_id, phase, "gc_heap_after_mean_mib", statistics.fmean(after)),
                     (run_id, phase, "gc_heap_after_max_mib", max(after))]
        starts, stops = merge((max(a, gc["t"][i] - gc["duration_s"][i]), min(b, gc["t"][i])) for i in idx
                              if gc["t"][i] > a and gc["t"][i] - gc["duration_s"][i] < b)
        rows.append((run_id, phase, "gc_active_pct", 100 * sum(map(float.__sub__, stops, starts)) / (b - a)))
        grown = gaps = 0.0
        for i, k in zip(idx, idx[1:]):
            start = gc["t"][k] - gc["duration_s"][k]
            if a <= gc["t"][i] < start < b:
                grown += gc["heap_before_mib"][k] - gc["heap_after_mib"][i]
                gaps += start - gc["t"][i]
        if gaps:
            rows.append((run_id, phase, "gc_alloc_mib_s", grown / gaps))
    return rows


# (metric, from event, to event): first occurrence of each, per run.
INTERVALS = (
    ("launch_to_menu_s", "client_launch", "client_menu"),
    ("launch_to_world_s", "client_launch", "player_join"),
    ("collect_wall_s", "collect_start", "collect_end"),
)


def interval_metrics(t):
    ev = t["event"]
    first = {key: min(ev["t"][i] for i in idx) for key, idx in T.group(ev, "run_id", "kind").items()}
    return [(run_id, metric, first[(run_id, b)] - first[(run_id, a)])
            for (run_id,) in T.group(t["run"], "run_id")
            for metric, a, b in INTERVALS
            if (run_id, a) in first and (run_id, b) in first]


def sample_metrics(t):
    """Per phase and sampled metric (GPU busy, VRAM, RSS): mean and p95."""
    rows = []
    s = t["sample"]
    for (run_id, phase), idx in T.within(s, t["phase"]).items():
        for (metric,), sub in T.group(T.take(s, idx), "metric").items():
            v = sorted(s["value"][idx[i]] for i in sub)
            rows += [(run_id, phase, f"{metric}_mean", statistics.fmean(v)),
                     (run_id, phase, f"{metric}_p95", T.quantile(v, 0.95))]
    return rows


def sample_peaks(t):
    s = t["sample"]
    return [(run_id, f"peak_{metric}", max(s["value"][i] for i in idx))
            for (run_id, metric), idx in T.group(s, "run_id", "metric").items()]


PHASE_REDUCERS = [frame_metrics, gc_metrics, gc_cycle_metrics, sample_metrics]
RUN_REDUCERS = [interval_metrics, sample_peaks]


def reduce(run_dirs):
    t = {name: T.load(run_dirs, name) for name in INPUTS}
    T.save(run_dirs, "phase_metric", T.from_rows("phase_metric", [r for f in PHASE_REDUCERS for r in f(t)]))
    T.save(run_dirs, "run_metric", T.from_rows("run_metric", [r for f in RUN_REDUCERS for r in f(t)]))


# Metric name suffix -> +1 if higher is better, -1 if lower is better, 0 for no direction
# (GPU busy). Longest match wins; metrics without a match (frames, collect_wall_s) and
# 0 get no verdict.
DIRECTION = {"_fps": 1, "_ms": -1, "_n": -1, "_mib": -1, "_mib_s": -1, "_pct": -1, "_per_min": -1,
             "_mib_mean": -1, "_mib_p95": -1, "_pct_mean": 0, "_pct_p95": 0, "gpu_busy_pct": 0,
             "launch_to_menu_s": -1, "launch_to_world_s": -1}
# Two-sided 95% Student t quantiles; interpolated linearly in 1/df.
T975 = ((1, 12.706), (2, 4.303), (3, 3.182), (4, 2.776), (5, 2.571), (6, 2.447), (7, 2.365), (8, 2.306),
        (9, 2.262), (10, 2.228), (12, 2.179), (15, 2.131), (20, 2.086), (30, 2.042), (60, 2.000),
        (120, 1.980), (math.inf, 1.960))


def contrast(metric, base, values):
    """Variant vs base, runs as the unit: (difference of means, Welch 95% CI low, high,
    exact two-sided permutation p, minimum achievable p, verdict).

    The verdict uses the CI: "better"/"worse" if it excludes 0, else "n.s." (also
    with fewer than 2 runs on a side, where there is no CI). The
    permutation p is exact over all relabellings of the pooled runs; with 3 vs 3
    there are 20, so p >= 0.1 and it alone can never reach 0.05."""
    n1, n2 = len(base), len(values)
    diff = statistics.fmean(values) - statistics.fmean(base)
    a, b = (statistics.variance(base) / n1, statistics.variance(values) / n2) if min(n1, n2) > 1 else (0, 0)
    if min(n1, n2) < 2:
        half = math.nan
    elif a + b > 0:
        df = (a + b) ** 2 / (a * a / (n1 - 1) + b * b / (n2 - 1))
        (d0, t0), (d1, t1) = next((lo, hi) for lo, hi in zip(T975, T975[1:]) if df <= hi[0])
        w = (1 / d0 - 1 / df) / (1 / d0 - 1 / d1) if df > d0 else 0.0
        half = (t0 + (t1 - t0) * w) * math.sqrt(a + b)
    else:
        half = 0.0
    pooled, total = base + values, sum(base) + sum(values)
    labels = list(itertools.combinations(range(n1 + n2), n2))
    extreme = sum(abs(sum(pooled[i] for i in c) / n2 - (total - sum(pooled[i] for i in c)) / n1)
                  >= abs(diff) - 1e-9 * (1 + abs(diff)) for c in labels)
    sign = next((d for suffix, d in sorted(DIRECTION.items(), key=lambda kv: -len(kv[0]))
                 if metric.endswith(suffix)), 0)
    lo, hi = diff - half, diff + half
    verdict = "n.s." if not (lo > 0 or hi < 0) else ("better" if (diff > 0) == (sign > 0) else "worse")
    return diff, lo, hi, extreme / len(labels), (1 + (n1 == n2)) / len(labels), verdict if sign else ""


EMPTY_DIFF = hashlib.sha256(b"").hexdigest()


def compare(run_dirs, by=None):
    """Per (variant, phase, metric): n, mean, sd, cv%, min, max, delta% of mean vs first
    variant, and contrast() vs the first variant. by: a provenance key (e.g. change_id);
    the group is then "variant@value" ("?" for runs without that key)."""
    runs = T.load(run_dirs, "run")
    prov = T.load(run_dirs, "provenance")
    value = {(r, k): v for r, k, v in zip(prov["run_id"], prov["key"], prov["value"])}
    for run_id in runs["run_id"]:
        if value.get((run_id, "diff_sha256"), EMPTY_DIFF) != EMPTY_DIFF:
            print(f"warning: {run_id}: jj diff of @ was not empty at collect", file=sys.stderr)
    variant_of = {r: v + (f"@{value.get((r, by), '?')}" if by else "") for r, v in zip(runs["run_id"], runs["variant"])}
    order = list(dict.fromkeys(variant_of.values()))
    pm = T.load(run_dirs, "phase_metric")
    rm = T.load(run_dirs, "run_metric")
    rm["phase"] = ["run"] * len(rm["run_id"])  # run-level metrics shown as phase "run"
    m = {col: pm[col] + rm[col] for col in pm}
    m["variant"] = [variant_of[r] for r in m["run_id"]]
    stats = {}
    for (phase, metric, variant), idx in T.group(m, "phase", "metric", "variant").items():
        v = [m["value"][i] for i in idx]
        sd = statistics.stdev(v) if len(v) > 1 else math.nan
        stats[(phase, metric, variant)] = (len(v), statistics.fmean(v), sd, min(v), max(v), v)
    print("\t".join(("phase", "metric", "variant", "n", "mean", "sd", "cv%", "min", "max", "delta%",
                     "diff", "ci95_lo", "ci95_hi", "perm_p", "min_p", "verdict")))
    for (phase, metric, variant), (n, mean, sd, lo, hi, v) in sorted(
            stats.items(), key=lambda kv: (kv[0][0], kv[0][1], order.index(kv[0][2]))):
        base = stats.get((phase, metric, order[0]), (0, math.nan, 0, 0, 0, []))
        cv = 100 * sd / mean if mean else math.nan
        delta = 100 * (mean - base[1]) / base[1] if base[1] else math.nan
        test = contrast(metric, base[5], v) if variant != order[0] and base[5] else ()
        print("\t".join([phase, metric, variant, str(n)] +
                        [f"{x:.4g}" for x in (mean, sd, cv, lo, hi)] + [f"{delta:+.1f}"] +
                        [f"{x:.4g}" for x in test[:5]] + list(test[5:])))


NATIVE = ("Native", "C++", "Kernel")  # JFR frame types of code outside the JVM's Java


def merge(intervals):
    """Union of [start, end] intervals as sorted, disjoint (starts, ends)."""
    starts, ends = [], []
    for a, b in sorted(intervals):
        if ends and a <= ends[-1]:
            ends[-1] = max(ends[-1], b)
        else:
            starts.append(a)
            ends.append(b)
    return starts, ends


def profile(run_dirs, thread="Render thread", kind="jdk.ExecutionSample", top=15, slow_ms=33.0,
            callees=None, phases=None):
    """Per run, phase and scope (all samples; samples inside frames > slow_ms):
    inclusive and self share of each method in one thread's stack samples.
    With callees (a method name substring): instead, the share of the thread's
    samples by the direct callee of the leaf-most matching frame of each stack
    ("(self)" if that frame is the leaf). phases limits the phases printed.

    A frame's interval is [t - frametime_ms/1000, t]. ms/s is sampled thread
    time per second of scope (phase length, or total slow-frame time): for the
    async-profiler CPU engines that is CPU ms/s; time the thread is blocked is
    not sampled. The JDK recorder samples only some threads per period, so its
    ms/s is not shown."""
    t = {name: T.load(run_dirs, name) for name in ("phase", "frame", "stack_sample", "stack_frame", "stack_method", "sampler")}
    ss, sf, sm, fr = t["stack_sample"], t["stack_frame"], t["stack_method"], t["frame"]
    ss = T.take(ss, [i for i, key in enumerate(zip(ss["thread"], ss["kind"])) if key == (thread, kind)])
    names = {key: (sm["method"][i], sm["frame_type"][i])
             for i, key in enumerate(zip(sm["run_id"], sm["method_id"]))}
    tree = {}  # run_id -> (parent ids, methods, frame types), indexed by frame_id
    for (run_id,), idx in T.group(sf, "run_id").items():
        idx.sort(key=sf["frame_id"].__getitem__)
        named = [names[(run_id, sf["method_id"][i])] for i in idx]
        tree[run_id] = ([sf["parent_id"][i] for i in idx], [m for m, _ in named], [f for _, f in named])
    period = {(r, k): (e, p) for r, k, e, p in zip(*(t["sampler"][c] for c in ("run_id", "kind", "engine", "period_ms")))}
    slow = {(run_id,): merge((fr["t"][i] - fr["frametime_ms"][i] / 1000, fr["t"][i])
                             for i in idx if fr["frametime_ms"][i] > slow_ms)
            for (run_id,), idx in T.group(fr, "run_id").items()}
    slow_s = {key: sum(fr["frametime_ms"][i] for i in idx if fr["frametime_ms"][i] > slow_ms) / 1000
              for key, idx in T.within(fr, t["phase"]).items()}
    span = {(r, p): b - a for r, p, a, b in zip(*(t["phase"][c] for c in ("run_id", "phase", "t_start", "t_end")))}

    def in_slow(i):
        starts, ends = slow.get((ss["run_id"][i],), ([], []))
        j = bisect.bisect_right(starts, ss["t"][i]) - 1
        return j >= 0 and ss["t"][i] <= ends[j]

    print("\t".join(("run_id", "phase", "scope", "rank", "incl%", "self%", "incl_ms/s", "self_ms/s", "method")))
    for (run_id, phase), idx in T.within(ss, t["phase"]).items():
        parent, method, frame_type = tree.get(run_id, ([], [], []))
        engine, period_ms = period.get((run_id, kind), ("?", math.nan))
        if phases and phase not in phases:
            continue
        for scope, rows, seconds in (("all", idx, span[(run_id, phase)]),
                                     (f"slow>{slow_ms:g}ms", [i for i in idx if in_slow(i)],
                                      slow_s.get((run_id, phase), 0.0))):
            leaves = collections.Counter(ss["frame_id"][i] for i in rows)
            incl, self_, under, native = collections.Counter(), collections.Counter(), collections.Counter(), 0
            for leaf, n in leaves.items():
                path, node, child, found = set(), leaf, None, False
                while node >= 0:
                    path.add(method[node])
                    if callees and not found and callees in method[node]:
                        under[method[child] if child is not None else "(self)"] += n
                        found = True
                    child, node = node, parent[node]
                for m in path:
                    incl[m] += n
                if leaf >= 0:
                    self_[method[leaf]] += n
                    native += n * (frame_type[leaf] in NATIVE)
            n = len(rows)
            ms = (lambda c: f"{c * period_ms / seconds:.1f}") if engine != "jdk" and seconds else (lambda c: "")
            pct = (lambda c: f"{100 * c / n:.1f}") if n else (lambda c: "")
            print("\t".join((run_id, phase, scope, "total", "100.0" if n else "", pct(native), ms(n), ms(native),
                             f"[{n} samples, {seconds:.1f} s, {engine} {period_ms:g} ms; self% = native leaf]")))
            if callees:
                hit = sum(under.values())
                print("\t".join((run_id, phase, scope, "under", pct(hit), "", ms(hit), "", callees)))
                for m, c in under.most_common(top):
                    print("\t".join((run_id, phase, scope, "callee", pct(c), "", ms(c), "", m)))
                continue
            for by, counter in (("self", self_), ("incl", incl)):
                for m, _ in counter.most_common(top):
                    print("\t".join((run_id, phase, scope, by, pct(incl[m]), pct(self_[m]),
                                     ms(incl[m]), ms(self_[m]), m)))
