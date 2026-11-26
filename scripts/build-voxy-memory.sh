#!/usr/bin/env bash
# Experimental private build, separate from the existing pinned production build.
set -euo pipefail
if [[ $# != 1 ]]; then
  echo 'Usage: bash scripts/build-voxy-memory.sh OUTPUT_DIRECTORY' >&2
  exit 2
fi
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p -- "$1"
out="$(cd -- "$1" && pwd)"
case "$out/" in "$root/packwiz/"*) echo 'Use an output directory outside packwiz' >&2; exit 2;; esac
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
source_commit=02589c94a1946014a77f4e87e5298d4f1b7fce60
version=1.1.0+retirement.4+neoforge
jar="voxy-$version.jar"
test ! -e "$out/$jar" && test ! -e "$out/$jar.sha256"
# Fail if this repository changed its upstream Voxy source pin.
grep -Fxq "source_commit=$source_commit" "$root/scripts/build-voxy.sh"
git -C "$work" init --quiet
git -C "$work" fetch --quiet --depth=1 https://github.com/falling-colud/voxy-forged.git "$source_commit"
git -C "$work" checkout --quiet --detach FETCH_HEAD
test "$(git -C "$work" rev-parse HEAD)" = "$source_commit"
git -C "$work" apply --check "$root/scripts/voxy.patch"
git -C "$work" apply "$root/scripts/voxy.patch"
python3 "$root/scripts/materialize-source-patch.py" "$work" "$root/scripts/voxy-memory.patch"
(
  cd "$work"
  GITHUB_ACTIONS=true ./gradlew --no-daemon --max-workers=2 \
    -Pminecraft_version=1.21.1 -Pneoforge_version=21.1.265 \
    -Pmod_version="$version" fluidBlockRegression jar
  test -f "build/libs/$jar"
)
# NeoForge keeps nested jars in heap for the whole session. Drop RocksDB natives
# for platforms Minecraft cannot run on (musl, 32-bit, ppc64le, s390x, riscv64).
python3 - "$work/build/libs/$jar" <<'EOF'
import io, re, sys, zipfile
keep = re.compile(r"librocksdbjni-(linux64\.so|linux-aarch64\.so|osx-.*\.jnilib|win64\.dll)$")
def repack(data, edit):
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            body = edit(info.filename, src.read(info))
            if body is not None:
                dst.writestr(info, body)
    return out.getvalue()
natives = lambda name, body: body if not name.startswith("librocksdbjni-") or keep.match(name) else None
outer = lambda name, body: repack(body, natives) if re.fullmatch(r"META-INF/jarjar/rocksdbjni-[^/]+\.jar", name) else body
path = sys.argv[1]
data = repack(open(path, "rb").read(), outer)
open(path, "wb").write(data)
EOF
# Validate mod metadata, cache classes and the new settings before leaving a candidate.
python3 "$root/scripts/promote-voxy-memory.py" --check-jar "$work/build/libs/$jar"
digest="$(sha256sum "$work/build/libs/$jar" | cut -d ' ' -f 1)"
# An optional committed pin permits later exact rebuild verification.
if [[ -f "$root/scripts/voxy-memory.sha256" ]]; then
  test "$digest" = "$(cat "$root/scripts/voxy-memory.sha256")"
fi
install -m644 "$work/build/libs/$jar" "$out/$jar"
printf '%s\n' "$digest" > "$out/$jar.sha256"
printf 'Candidate: %s\nSHA-256: %s\n' "$out/$jar" "$digest"
echo 'Test in a disposable client. Rebuild in a second directory and compare hashes before promotion.'
