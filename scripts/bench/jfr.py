"""Minimal JFR (format 2.x) reader: stack-sample events and their stack traces.

A JFR chunk is already normalised: events refer to constant pools (threads,
stack traces, methods, symbols) by key. This reader parses the chunk's own
metadata (type and field layout) generically, so it reads files from both the
JDK recorder and async-profiler. It keeps only the events in SAMPLES and the
pools they refer to. Format reference: jdk.jfr.internal.consumer
(ChunkHeader, MetadataReader, ChunkParser) in the JDK source.
"""

import struct

# Sample event types: JDK recorder (Java code; threads in native methods) and
# async-profiler (cpu/itimer/ctimer samples use jdk.ExecutionSample too).
SAMPLES = ("jdk.ExecutionSample", "jdk.NativeMethodSample", "profiler.WallClockSample")
UNIT_MS = {"ns": 1e-6, "us": 1e-3, "ms": 1.0, "s": 1000.0}  # JDK period strings, e.g. "10 ms"
HEADER = struct.Struct(">4sHHqqqqqqqi")  # 68 bytes
FLOAT, DOUBLE = struct.Struct(">f"), struct.Struct(">d")


class Reader:
    def __init__(self, buf, pos):
        self.buf, self.pos = buf, pos

    def varint(self):
        """LEB128, at most 9 bytes; the 9th byte carries 8 bits. Unsigned."""
        buf, pos = self.buf, self.pos
        b = buf[pos]
        if b < 0x80:
            self.pos = pos + 1
            return b
        value, shift = b & 0x7F, 7
        for pos in range(pos + 1, pos + 8):
            b = buf[pos]
            value |= (b & 0x7F) << shift
            if b < 0x80:
                self.pos = pos + 1
                return value
            shift += 7
        self.pos = pos + 2
        return value | buf[pos + 1] << 56

    def byte(self):
        self.pos += 1
        return self.buf[self.pos - 1]

    def string(self, strings):
        """Encodings: 0 null, 1 empty, 2 pool ref, 3 UTF-8, 4 char array, 5 Latin-1."""
        kind = self.byte()
        if kind == 0:
            return None
        if kind == 1:
            return ""
        if kind == 2:
            return strings.get(self.varint())
        n = self.varint()
        if kind == 4:
            return "".join(chr(self.varint()) for _ in range(n))
        self.pos += n
        return self.buf[self.pos - n:self.pos].decode("utf-8" if kind == 3 else "latin-1", errors="replace")


def element(r, strings):
    """Metadata element tree node: (name, {attribute: value}, [children])."""
    name = strings[r.varint()]
    attrs = {strings[r.varint()]: strings[r.varint()] for _ in range(r.varint())}
    return name, attrs, [element(r, strings) for _ in range(r.varint())]


def read_metadata(r):
    """{class id: (class name, [(field name, field class id, is pool ref, is array)])}."""
    for _ in range(3):  # startTime, duration, metadataId (after size and type)
        r.varint()
    strings = [r.string({}) for _ in range(r.varint())]
    root = element(r, strings)
    classes = {}
    for _, attrs, children in (c for m in root[2] if m[0] == "metadata" for c in m[2]):
        fields = [(f["name"], int(f["class"]), f.get("constantPool") == "true", f.get("dimension") == "1")
                  for name, f, _ in children if name == "field"]
        classes[int(attrs["id"])] = (attrs["name"], fields)
    return classes


def make_value(classes, strings):
    """reader_for(class id) -> read(reader) -> int | float | str | None | {field: value}.

    Pool references stay keys; they are resolved after the whole chunk is read."""
    def read_float(r):
        r.pos += 4
        return FLOAT.unpack_from(r.buf, r.pos - 4)[0]

    def read_double(r):
        r.pos += 8
        return DOUBLE.unpack_from(r.buf, r.pos - 8)[0]

    readers = {"boolean": Reader.byte, "byte": Reader.byte, "char": Reader.varint, "short": Reader.varint,
               "int": Reader.varint, "long": Reader.varint, "float": read_float, "double": read_double,
               "java.lang.String": lambda r: r.string(strings)}

    def reader_for(class_id):
        name, fields = classes[class_id]
        if name not in readers:
            plan = []
            readers[name] = lambda r: {field: read(r) for field, read in plan}
            for field, cls, ref, array in fields:  # filled after registering: types may recurse
                one = Reader.varint if ref else (lambda r, c=cls: reader_for(c)(r))
                plan.append((field, (lambda r, one=one: [one(r) for _ in range(r.varint())]) if array else one))
        return readers[name]
    return reader_for


def chunks(buf):
    pos = 0
    while pos < len(buf):
        magic, major, _, size, _, meta, start_ns, _, start_ticks, tps, features = HEADER.unpack_from(buf, pos)
        if magic != b"FLR\0" or major != 2 or not features & 1:
            raise ValueError(f"unsupported JFR chunk at {pos}: {magic} v{major} features {features}")
        yield pos, size, meta, start_ns, start_ticks, tps
        pos += size


def samples(path):
    """[(epoch s, thread name, event type, (frame, ...) leaf first)], {event type: (engine, period ms)}.

    engine is async-profiler's (ctimer, perf, itimer, wall) or "jdk" for the JDK
    recorder, which samples only some threads per period.

    A frame is (method, frame type), method = "class.name" (for native frames
    the class is the library, e.g. "libGLX_nvidia.so.0.glXSwapBuffers")."""
    buf = open(path, "rb").read()
    out, samplers = [], {}
    for start, size, meta, start_ns, start_ticks, tps in chunks(buf):
        r = Reader(buf, start + meta)
        r.varint(), r.varint()  # size, type 0
        classes = read_metadata(r)
        by_name = {name: cid for cid, (name, _) in classes.items()}
        strings = {}
        pools = {}  # class id -> {key: value}
        value = make_value(classes, strings)
        wanted = {by_name[n]: n for n in SAMPLES if n in by_name}
        setting = by_name.get("jdk.ActiveSetting")
        events = []
        pos = start + HEADER.size
        while pos < start + size:
            r = Reader(buf, pos)
            n, kind = r.varint(), r.varint()
            if kind == 1:  # checkpoint: startTime, duration, delta, typeMask, pools
                r.varint(), r.varint(), r.varint(), r.byte()
                for _ in range(r.varint()):
                    cid = r.varint()
                    pool = pools.setdefault(cid, {})
                    read = value(cid)
                    for _ in range(r.varint()):
                        key = r.varint()
                        pool[key] = read(r)
                    if classes[cid][0] == "java.lang.String":
                        strings.update(pool)
            elif kind in wanted or kind == setting:
                events.append((kind, value(kind)(r)))
            pos += n

        def pooled(type_name, key):
            return pools.get(by_name.get(type_name), {}).get(key)

        def method_name(key):
            m = pooled("jdk.types.Method", key) or {}
            cls = pooled("java.lang.Class", m.get("type")) or {}
            sym = (pooled("jdk.types.Symbol", cls.get("name")) or {}).get("string") or "?"
            name = (pooled("jdk.types.Symbol", m.get("name")) or {}).get("string") or "?"
            return sym.replace("/", ".") + "." + name

        settings = [ev for kind, ev in events if kind == setting]
        if "profiler.Log" in by_name:  # async-profiler: its own option names; intervals in ns
            opt = {ev["name"]: ev["value"] or "" for ev in settings}
            for name, kind, engine in (("interval", "jdk.ExecutionSample", opt.get("engine", "?")),
                                       ("wall", "profiler.WallClockSample", "wall")):
                if opt.get(name, "").isdigit() and int(opt[name]) > 0:
                    samplers[kind] = (engine, int(opt[name]) / 1e6)
        for ev in settings:
            number, _, unit = (ev["value"] or "").partition(" ")
            if ev["name"] == "period" and ev["id"] in wanted and unit in UNIT_MS:
                samplers[wanted[ev["id"]]] = ("jdk", float(number) * UNIT_MS[unit])

        threads, stacks, methods = {}, {}, {}
        for kind, ev in events:
            if kind == setting:
                continue
            tkey, skey = ev.get("sampledThread"), ev.get("stackTrace")
            if tkey not in threads:
                th = pooled("java.lang.Thread", tkey) or {}
                threads[tkey] = th.get("javaName") or th.get("osName") or "?"
            if skey not in stacks:
                trace = pooled("jdk.types.StackTrace", skey) or {"frames": []}
                frames = []
                for f in trace["frames"]:
                    if f["method"] not in methods:
                        methods[f["method"]] = method_name(f["method"])
                    ftype = (pooled("jdk.types.FrameType", f.get("type")) or {}).get("description") or "?"
                    frames.append((methods[f["method"]], ftype))
                stacks[skey] = tuple(frames)
            epoch = (start_ns + (ev["startTime"] - start_ticks) * 1e9 / tps) / 1e9
            out.append((epoch, threads[tkey], wanted[kind], stacks[skey]))
    return out, samplers
