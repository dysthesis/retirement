#!/usr/bin/env python3
"""Inspect the mod jars of the built client pack (Python stdlib only; run with python3 -I).

Jars are untrusted data: they are only read as zip files, never loaded or executed.
Nested jars (META-INF/jarjar/*.jar and similar) are indexed recursively in memory.

The index is built once per pack and cached as flat CSV tables under
~/.cache/claude-retirement-scratch/jars/index/<pack>/:
  jar(jar_id, outer_jar, inner_path, mod_id, version, sha256)
  class(jar_id, class_name)
  mixin(jar_id, config_file, source, mixin_class, target_class, priority)
  mixin_method(jar_id, mixin_class, method_name, injector_kind, target_method, at_target)

Commands:
  find REGEX                          classes matching REGEX, with jar and mod
  mixins CLASS_REGEX [--method NAME]  mixins that target matching classes (and methods), and
                                      injectors whose @At target is a member of a matching class
  src CLASS [CLASS...]                decompile classes with CFR; prints the .java paths
  index                               build the index only; prints its directory

Examples:
  python3 -I scripts/jars.py find OasisGrassColor
  python3 -I scripts/jars.py mixins 'BlockBehaviour\\$BlockStateBase$' --method canOcclude
  python3 -I scripts/jars.py src xaero.map.MapWriter
"""

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import time
import tomllib
import zipfile

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parent.parent
CACHE = Path.home() / ".cache/claude-retirement-scratch/jars"
CFR = Path("/nix/store/qnb9gam6acrwzfnzaxc3yxfs1mjwh2jr-cfr-0.152/bin/cfr")

SCHEMA = {
    "jar": ("jar_id", "outer_jar", "inner_path", "mod_id", "version", "sha256"),
    "class": ("jar_id", "class_name"),
    # source: where the config is declared (MANIFEST.MF, mods.toml, fabric.mod.json), or glob if it is
    # only found by name; a glob-only config (often another loader's) is usually not applied.
    "mixin": ("jar_id", "config_file", "source", "mixin_class", "target_class", "priority"),
    # at_target: the @At(target=...) members of the injector, space-separated (call sites it hooks).
    "mixin_method": ("jar_id", "mixin_class", "method_name", "injector_kind", "target_method", "at_target"),
}

MIXIN_ANN = "Lorg/spongepowered/asm/mixin/Mixin;"
# Method annotations whose `method` element names target methods. Overwrite targets its own name.
INJECTORS = {
    "Lorg/spongepowered/asm/mixin/injection/" + k + ";": k
    for k in ("Inject", "Redirect", "ModifyArg", "ModifyArgs", "ModifyVariable", "ModifyConstant")
} | {
    "Lcom/llamalad7/mixinextras/injector/" + k + ";": k.rsplit("/", 1)[-1]
    for k in ("ModifyExpressionValue", "ModifyReturnValue", "ModifyReceiver", "WrapWithCondition",
              "v2/WrapWithCondition", "wrapoperation/WrapOperation", "wrapmethod/WrapMethod")
} | {
    "Lorg/spongepowered/asm/mixin/Overwrite;": "Overwrite",
    "Lorg/spongepowered/asm/mixin/gen/Accessor;": "Accessor",
    "Lorg/spongepowered/asm/mixin/gen/Invoker;": "Invoker",
}
# Methods with these annotations are not added to or merged into the target.
NOT_MERGED = {"Lorg/spongepowered/asm/mixin/Shadow;", "Lorg/spongepowered/asm/mixin/Unique;"}


# ---- class file parsing (constant pool, annotations, method names) ----

def parse_class(data):
    """Return (class_annotations, [(method_name, access, annotations)]) for a class file.

    Annotations are [(type_descriptor, {element: value})]; class literals become dotted names.
    """
    if data[:4] != b"\xca\xfe\xba\xbe":
        raise ValueError("not a class file")
    count = struct.unpack_from(">H", data, 8)[0]
    pool = [None] * count
    pos, i = 10, 1
    while i < count:
        tag = data[pos]
        if tag == 1:
            n = struct.unpack_from(">H", data, pos + 1)[0]
            pool[i] = data[pos + 3:pos + 3 + n].decode("utf-8", "replace")  # modified UTF-8
            pos += 3 + n
        elif tag == 3:
            pool[i] = struct.unpack_from(">i", data, pos + 1)[0]
            pos += 5
        elif tag in (5, 6):
            pos += 9
            i += 1  # long and double take two slots
        elif tag in (4, 9, 10, 11, 12, 17, 18):
            pos += 5
        elif tag in (7, 8, 16, 19, 20):
            pos += 3
        elif tag == 15:
            pos += 4
        else:
            raise ValueError(f"bad constant pool tag {tag}")
        i += 1

    def u2():
        nonlocal pos
        pos += 2
        return struct.unpack_from(">H", data, pos - 2)[0]

    def element():
        nonlocal pos
        tag = chr(data[pos])
        pos += 1
        if tag in "BCDFIJSZs":
            return pool[u2()]
        if tag == "e":
            u2()
            return pool[u2()]
        if tag == "c":
            return descriptor_to_name(pool[u2()])
        if tag == "@":
            return annotation()
        if tag == "[":
            return [element() for _ in range(u2())]
        raise ValueError(f"bad element tag {tag}")

    def annotation():
        kind = pool[u2()]
        return kind, {pool[u2()]: element() for _ in range(u2())}

    def attributes():
        nonlocal pos
        anns = []
        for _ in range(u2()):
            name, length = pool[u2()], struct.unpack_from(">I", data, pos)[0]
            pos += 4
            end = pos + length
            if name in ("RuntimeVisibleAnnotations", "RuntimeInvisibleAnnotations"):
                anns += [annotation() for _ in range(u2())]
            pos = end
        return anns

    pos += 6  # access, this, super
    interfaces = u2()  # read first: `pos += 2 * u2()` would drop u2's own advance
    pos += 2 * interfaces
    for _ in range(u2()):  # fields
        pos += 6
        attributes()
    methods = []
    for _ in range(u2()):
        access, name = u2(), pool[u2()]
        u2()  # descriptor
        methods.append((name, access, attributes()))
    return attributes(), methods


def descriptor_to_name(desc):
    """Lnet/minecraft/Foo$Bar; or net/minecraft/Foo$Bar -> net.minecraft.Foo$Bar."""
    if desc.startswith("L") and desc.endswith(";"):
        desc = desc[1:-1]
    return desc.replace("/", ".")


def as_list(v):
    return v if isinstance(v, list) else [] if v is None else [v]


# ---- index build ----

def manifest_value(manifest, key):
    text = re.sub(r"\r?\n ", "", manifest)  # join continuation lines
    m = re.search(rf"^{key}:\s*(.*)$", text, re.M)
    return m.group(1).strip() if m else ""


def mod_metadata(z, names):
    """Return (mod_id, version, [(mixin_config, source)]) from the manifest, mods.toml or fabric.mod.json."""
    manifest = z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace") if "META-INF/MANIFEST.MF" in names else ""
    configs = [(c.strip(), "MANIFEST.MF") for c in manifest_value(manifest, "MixinConfigs").split(",")]
    mod_id = version = ""
    for toml_name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
        if toml_name in names:
            try:
                meta = tomllib.loads(z.read(toml_name).decode("utf-8", "replace"))
            except tomllib.TOMLDecodeError:
                continue
            mods = meta.get("mods") or [{}]
            mod_id, version = str(mods[0].get("modId", "")), str(mods[0].get("version", ""))
            configs += [(m.get("config", ""), "mods.toml") for m in meta.get("mixins", []) if isinstance(m, dict)]
            break
    if not mod_id and "fabric.mod.json" in names:
        try:
            meta = json.loads(z.read("fabric.mod.json"), strict=False)
            mod_id, version = str(meta.get("id", "")), str(meta.get("version", ""))
            configs += [(m if isinstance(m, str) else m.get("config", ""), "fabric.mod.json") for m in meta.get("mixins", [])]
        except (ValueError, AttributeError):
            pass
    if "${" in version:
        version = manifest_value(manifest, "Implementation-Version") or version
    return mod_id, version, configs


def index_jar(data, outer, inner, tables, warn):
    jar_id = len(tables["jar"])
    where = "!".join(filter(None, (outer, inner)))
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    nameset = set(names)
    mod_id, version, configs = mod_metadata(z, nameset)
    tables["jar"].append((jar_id, outer, inner, mod_id, version, hashlib.sha256(data).hexdigest()))
    tables["class"] += [(jar_id, n[:-6].replace("/", ".")) for n in names
                        if n.endswith(".class") and not n.startswith("META-INF/versions/")]
    globbed = [(n, "glob") for n in names if "/" not in n and n.endswith(".json") and "mixin" in n.lower()]
    sources = {}
    for c, source in configs + globbed:
        sources.setdefault(c, source)
    seen = set()  # a mixin class listed in several configs gets its methods indexed once
    for cfg_name, source in sources.items():
        if not cfg_name or cfg_name not in nameset:
            continue
        try:
            text = z.read(cfg_name).decode("utf-8", "replace")
            text = re.sub(r"(?m)^\s*//.*$", "", text)  # Mixin reads configs with lenient Gson:
            text = re.sub(r",(\s*[}\]])", r"\1", text)  # allow line comments and trailing commas
            cfg = json.loads(text, strict=False)
        except ValueError as e:
            warn(f"{where}!{cfg_name}: {e}")
            continue
        if not isinstance(cfg, dict) or "package" not in cfg:
            continue
        default_priority = cfg.get("priority", 1000)
        for short in dict.fromkeys(as_list(cfg.get("mixins")) + as_list(cfg.get("client")) + as_list(cfg.get("server"))):
            mixin = f"{cfg['package']}.{short}"
            path = mixin.replace(".", "/") + ".class"
            if path not in nameset:
                warn(f"{where}: {cfg_name} names missing {mixin}")
                continue
            try:
                class_anns, methods = parse_class(z.read(path))
            except (ValueError, IndexError, struct.error) as e:
                warn(f"{where}!{path}: {e}")
                continue
            ann = next((v for k, v in class_anns if k == MIXIN_ANN), {})
            targets = as_list(ann.get("value")) + [descriptor_to_name(t) for t in as_list(ann.get("targets"))]
            priority = ann.get("priority", default_priority)
            tables["mixin"] += [(jar_id, cfg_name, source, mixin, t, priority) for t in targets]
            if mixin in seen:
                continue
            seen.add(mixin)
            for name, access, anns in methods:
                kinds = [(INJECTORS[k], v) for k, v in anns if k in INJECTORS]
                for kind, values in kinds:
                    method_values = [name] if kind in ("Overwrite", "Accessor", "Invoker") else as_list(values.get("method"))
                    ats = " ".join(a[1].get("target", "") for a in as_list(values.get("at")) if isinstance(a, tuple))
                    tables["mixin_method"] += [(jar_id, mixin, name, kind, m, ats.strip()) for m in method_values]
                # An unannotated method is added to the target, or replaces a target method of the same signature.
                if not kinds and not any(k in NOT_MERGED for k, _ in anns) and not access & 0x1000 \
                        and name not in ("<init>", "<clinit>") and not name.startswith("lambda$"):
                    tables["mixin_method"].append((jar_id, mixin, name, "merge", name, ""))
    for n in names:
        if n.endswith(".jar"):
            try:
                index_jar(z.read(n), outer, f"{inner}!{n}" if inner else n, tables, warn)
            except (zipfile.BadZipFile, OSError) as e:
                warn(f"{where}!{n}: {e}")


def build_index(pack, out):
    tables = {k: [] for k in SCHEMA}
    warnings = []
    start = time.monotonic()
    for jar in sorted((pack / "mods").glob("*.jar")):
        try:
            index_jar(jar.read_bytes(), jar.name, "", tables, warnings.append)
        except (zipfile.BadZipFile, OSError) as e:
            warnings.append(f"{jar.name}: {e}")
    tmp = out.with_name(out.name + ".tmp")
    tmp.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        with open(tmp / f"{name}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(SCHEMA[name])
            w.writerows(rows)
    (tmp / "warnings.txt").write_text("".join(w + "\n" for w in warnings))
    tmp.rename(out)
    print(f"indexed {pack} in {time.monotonic() - start:.1f} s: "
          + ", ".join(f"{len(v)} {k}" for k, v in tables.items())
          + f"; {len(warnings)} warnings in {out}/warnings.txt", file=sys.stderr)


def load_index(pack):
    """Return {table: [tuple]} for the pack, building the index first if needed."""
    listing = "".join(f"{p.name}\0{p.stat().st_size}\0{p.stat().st_mtime_ns}\n" for p in sorted((pack / "mods").glob("*.jar")))
    out = CACHE / "index" / f"{pack.name}-{hashlib.sha256((repr(SCHEMA) + listing).encode()).hexdigest()[:12]}"
    if not out.is_dir():
        build_index(pack, out)
    tables = {}
    for name in SCHEMA:
        with open(out / f"{name}.csv", newline="") as f:
            rows = csv.reader(f)
            next(rows)
            tables[name] = [tuple(int(v) if c == "jar_id" else v for c, v in zip(SCHEMA[name], r)) for r in rows]
    tables["dir"] = out
    return tables


def default_pack():
    out = subprocess.run(["nix", "build", ".#modpack-client", "--no-link", "--print-out-paths"],
                         cwd=REPO, check=True, capture_output=True, text=True).stdout
    return Path(out.split()[0])


# ---- queries: pure functions over tables ----

def jar_label(jar):
    _, outer, inner, mod_id, version, _ = jar
    return f"{mod_id or '?'} {version} {outer}" + (f"!{inner}" if inner else "")


def find(t, pattern):
    rx = re.compile(pattern)
    return [(c, jar_label(t["jar"][j])) for j, c in t["class"] if rx.search(c)]


def bare_method(target):
    """Lnet/foo/Bar;canOcclude()Z, canOcclude()Z or canOcclude*  ->  canOcclude."""
    return re.sub(r"^L[^;]*;", "", target).split("(")[0].split(":")[0].rstrip("*")


def mixins(t, class_pattern, method=None):
    """Return [(target_class, priority, jar_label, config, mixin_class, [(kind, method_name, target_method)])]."""
    rx = re.compile(class_pattern)
    hooks = {}
    for j, mixin, name, kind, target, _ in t["mixin_method"]:
        if method is None or re.fullmatch(method, bare_method(target)):
            hooks.setdefault((j, mixin), []).append((kind, name, target))
    rows = [(target, int(prio), jar_label(t["jar"][j]), f"{cfg} ({source})", mixin, hooks.get((j, mixin), []))
            for j, cfg, source, mixin, target, prio in t["mixin"] if rx.search(target)]
    if method is not None:
        rows = [r for r in rows if r[5]]
    return sorted(rows, key=lambda r: (r[0], r[1], r[2], r[4]))


def call_sites(t, class_pattern, method=None):
    """Return [(at_target, jar_label, mixin_class, kind, method_name, target_method, mixin_targets)] for
    injectors whose @At target member belongs to a class matching class_pattern (and method, if given)."""
    rx = re.compile(class_pattern)
    targets = {}
    for j, _, _, mixin, target, _ in t["mixin"]:
        targets.setdefault((j, mixin), set()).add(target)
    rows = []
    for j, mixin, name, kind, target, ats in t["mixin_method"]:
        for at in ats.split():
            owner = re.match(r"L([^;]*);", at)
            if owner and rx.search(descriptor_to_name(owner.group(1))) \
                    and (method is None or re.fullmatch(method, bare_method(at))):
                rows.append((at, jar_label(t["jar"][j]), mixin, kind, name, target,
                             " ".join(sorted(targets.get((j, mixin), ())))))
    return sorted(set(rows))


def class_locations(t, name):
    """Return the jar rows that contain class `name` (dotted or slashed)."""
    name = name.replace("/", ".").removesuffix(".class")
    return [t["jar"][j] for j, c in t["class"] if c == name]


def read_jar_bytes(pack, jar):
    data = (pack / "mods" / jar[1]).read_bytes()
    for part in jar[2].split("!") if jar[2] else []:
        data = zipfile.ZipFile(io.BytesIO(data)).read(part)
    return data


def cfr_path():
    if CFR.exists():
        return CFR
    out = subprocess.run(["nix", "build", "nixpkgs#cfr", "--no-link", "--print-out-paths"],
                         check=True, capture_output=True, text=True).stdout
    return Path(out.split()[0]) / "bin/cfr"


def decompile(t, pack, names):
    """Decompile each class (with its inner classes) from every jar that holds it; return .java paths."""
    paths = []
    cfr = cfr_path()
    for name in names:
        jars = class_locations(t, name)
        if not jars:
            print(f"{name}: not found", file=sys.stderr)
        for jar in jars:
            out = CACHE / "src" / t["dir"].name / f"{jar[3] or Path(jar[1]).stem}-{jar[0]}"
            entry = name.replace(".", "/").removesuffix("/class").split("$")[0]  # decompile the outer class
            with tempfile.TemporaryDirectory(dir=CACHE) as tmp:
                data = read_jar_bytes(pack, jar)
                z = zipfile.ZipFile(io.BytesIO(data))
                files = []
                for n in z.namelist():
                    if n == entry + ".class" or (n.startswith(entry + "$") and n.endswith(".class")):
                        p = Path(tmp, "classes", n)
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_bytes(z.read(n))
                        files.append(str(p))
                classpath = Path(tmp, "jar.jar")
                classpath.write_bytes(data)
                subprocess.run([str(cfr), *files, "--outputdir", str(out), "--extraclasspath", str(classpath),
                                "--silent", "true"], check=True, stdout=subprocess.DEVNULL)
            paths.append((out / (entry + ".java"), jar_label(jar)))
    return paths


# ---- command line ----

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pack", type=Path, help="pack directory with mods/ (default: nix build .#modpack-client)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("index")
    sub.add_parser("find").add_argument("regex")
    m = sub.add_parser("mixins")
    m.add_argument("class_regex")
    m.add_argument("--method", help="regex that must fully match the bare target method name")
    sub.add_parser("src").add_argument("classes", nargs="+")
    a = p.parse_args()

    pack = (a.pack or default_pack()).resolve()
    CACHE.mkdir(parents=True, exist_ok=True)
    t = load_index(pack)
    if a.cmd == "index":
        print(t["dir"])
    elif a.cmd == "find":
        for cls, jar in find(t, a.regex):
            print(f"{cls}\t{jar}")
    elif a.cmd == "mixins":
        for target, prio, jar, cfg, mixin, hooks in mixins(t, a.class_regex, a.method):
            print(f"{target}\tpriority={prio}\t{jar}\t{cfg}\t{mixin}")
            for kind, name, method in hooks:
                print(f"    {kind}\t{method}\t-> {name}")
        for at, jar, mixin, kind, name, method, hosts in call_sites(t, a.class_regex, a.method):
            print(f"at {at}\t{jar}\t{mixin}\n    {kind}\t{hosts}::{method}\t-> {name}")
    elif a.cmd == "src":
        for path, jar in decompile(t, pack, a.classes):
            print(f"{path}\t{jar}")


if __name__ == "__main__":
    main()
