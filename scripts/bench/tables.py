"""Shared base: the table schema and whole-table operations.

A table is a dict of equal-length column lists. Each table is one CSV file per
run directory. Rows are keyed by run_id. No table stores derived or nested data:
a frame belongs to a phase because its t is inside that phase row's
[t_start, t_end). t is seconds since the run's t0 (epoch seconds, in run.csv).

A gc_cycle's t is its end; it ran over [t - duration_s, t]. gc_pause.thread is
the stalled thread of an allocation stall, "" for a pause.

Profiles: a stack_sample is one sample of one thread by one sampler (kind, a JFR
event type). Its stack is the path from its frame_id to the root (parent_id -1)
through stack_frame, a call tree: each frame_id is one call path, so prefixes
shared by many stacks are stored once. stack_method names each method_id. A sample stands for period_ms of the
thread's time (CPU time for the async-profiler engines; see analyse.profile).
"""

import bisect
import csv
import math
from pathlib import Path

# The single interface between stages: table -> ordered (column, type).
SCHEMA = {
    "run": (("run_id", str), ("variant", str), ("t0", float)),
    "input": (("run_id", str), ("role", str), ("path", str), ("sha256", str)),
    "provenance": (("run_id", str), ("key", str), ("value", str)),
    "override": (("run_id", str), ("target", str), ("key", str), ("value", str)),
    "phase": (("run_id", str), ("phase", str), ("t_start", float), ("t_end", float)),
    "event": (("run_id", str), ("t", float), ("kind", str), ("value", str)),
    "sample": (("run_id", str), ("t", float), ("metric", str), ("value", float)),
    "frame": (("run_id", str), ("t", float), ("frametime_ms", float)),
    "gc_pause": (("run_id", str), ("t", float), ("pause_ms", float), ("kind", str), ("thread", str)),
    "gc_cycle": (("run_id", str), ("t", float), ("kind", str), ("cause", str),
                 ("heap_before_mib", float), ("heap_after_mib", float), ("duration_s", float)),
    "stack_sample": (("run_id", str), ("t", float), ("thread", str), ("kind", str), ("frame_id", int)),
    "stack_frame": (("run_id", str), ("frame_id", int), ("parent_id", int), ("method_id", int)),
    "stack_method": (("run_id", str), ("method_id", int), ("method", str), ("frame_type", str)),
    "sampler": (("run_id", str), ("kind", str), ("engine", str), ("period_ms", float)),
    "phase_metric": (("run_id", str), ("phase", str), ("metric", str), ("value", float)),
    "run_metric": (("run_id", str), ("metric", str), ("value", float)),
}


def empty(name):
    return {col: [] for col, _ in SCHEMA[name]}


def from_rows(name, rows):
    table = empty(name)
    for row in rows:
        for (col, _), value in zip(SCHEMA[name], row, strict=True):
            table[col].append(value)
    return table


def take(table, indices):
    return {col: [values[i] for i in indices] for col, values in table.items()}


def concat(name, tables):
    out = empty(name)
    for table in tables:
        for col in out:
            out[col].extend(table[col])
    return out


def read(path, name):
    table = empty(name)
    if Path(path).exists():
        with open(path, newline="") as handle:
            for row in csv.DictReader(handle):
                for col, kind in SCHEMA[name]:
                    table[col].append(kind(row[col]))
    return table


def write(path, name, table):
    cols = [col for col, _ in SCHEMA[name]]
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(cols)
        writer.writerows(zip(*(table[col] for col in cols)))


def load(run_dirs, name):
    """One table over many runs."""
    return concat(name, [read(Path(d) / f"{name}.csv", name) for d in run_dirs])


def save(run_dirs, name, table):
    """Split a many-run table back into one file per run directory."""
    rows = group(table, "run_id")
    for d in map(Path, run_dirs):
        write(d / f"{name}.csv", name, take(table, rows.get((d.name,), [])))


def group(table, *cols):
    """{(key values...): [row indices]}, in first-seen order."""
    groups = {}
    for i, key in enumerate(zip(*(table[c] for c in cols))):
        groups.setdefault(key, []).append(i)
    return groups


def within(table, phase):
    """Join rows to phases by time range: {(run_id, phase): [row indices]}."""
    out = {}
    phases = group(phase, "run_id")
    for (run_id,), rows in group(table, "run_id").items():
        rows.sort(key=table["t"].__getitem__)
        ts = [table["t"][i] for i in rows]
        for j in phases.get((run_id,), []):
            lo = bisect.bisect_left(ts, phase["t_start"][j])
            hi = bisect.bisect_left(ts, phase["t_end"][j])
            out[(run_id, phase["phase"][j])] = rows[lo:hi]
    return out


def quantile(sorted_values, q):
    """Linear interpolation between closest ranks (numpy's default)."""
    if not sorted_values:
        return math.nan
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


SQL_TYPE = {str: "TEXT", float: "REAL", int: "INTEGER"}


def index(run_dirs, path):
    """Rebuild an SQLite copy of every table of these runs at path: derived, so
    dropped and rebuilt whole. Written to path.tmp, then renamed over path."""
    import sqlite3
    tmp = Path(f"{path}.tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    for name, cols in SCHEMA.items():
        db.execute(f"CREATE TABLE {name} ({', '.join(f'{c} {SQL_TYPE[k]}' for c, k in cols)})")
        db.execute(f"CREATE INDEX {name}_run_id ON {name} (run_id)")
        table = load(run_dirs, name)
        db.executemany(f"INSERT INTO {name} VALUES ({', '.join('?' * len(cols))})",
                       zip(*(table[c] for c, _ in cols)))
    db.commit()
    db.close()
    tmp.rename(path)
