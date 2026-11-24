#!/usr/bin/env bash
# Build a private client test artefact without modifying the active pack or server.
set -euo pipefail
if [[ $# != 1 ]]; then
  echo 'Usage: bash scripts/build-create-panel.sh OUTPUT_DIRECTORY' >&2
  exit 2
fi
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p -- "$1"
out="$(cd -- "$1" && pwd)"
case "$out/" in "$root/packwiz/"*) echo 'Use an output directory outside packwiz' >&2; exit 2;; esac
candidate=create-1.21.1-6.0.10-retirement-panel-test.jar
test ! -e "$out/$candidate" && test ! -e "$out/$candidate.sha256"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
commit=ac0c444d9828da3453ae8cc65338e8de063286fb
git -C "$work" init --quiet
git -C "$work" fetch --quiet --depth=1 https://github.com/Creators-of-Create/Create.git "$commit"
git -C "$work" checkout --quiet --detach FETCH_HEAD
test "$(git -C "$work" rev-parse HEAD)" = "$commit"
git -C "$work" apply --check "$root/scripts/create-panel-render-only.patch"
git -C "$work" apply "$root/scripts/create-panel-render-only.patch"
git -C "$work" apply --check "$root/scripts/create-panel-reproducible.patch"
git -C "$work" apply "$root/scripts/create-panel-reproducible.patch"
(
  cd "$work"
  # Keep original release mod version and the bundled dependency versions.
  RELEASE=true ./gradlew --no-daemon --max-workers=2 build
)
jar="$work/build/libs/create-1.21.1-6.0.10.jar"
python3 - "$jar" <<'PY'
import sys,tomllib,zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    if z.testzip() is not None: raise ValueError('Invalid JAR CRC')
    mods=tomllib.loads(z.read('META-INF/neoforge.mods.toml').decode())['mods']
    if not any(m['modId']=='create' and m['version']=='6.0.10' for m in mods):
        raise ValueError('Unexpected mod metadata')
    for cls in ('infrastructure/config/CClient.class','foundation/blockEntity/behaviour/filtering/FilteringRenderer.class'):
        data=z.read('com/simibubi/create/'+cls)
        if not data.startswith(b'\xca\xfe\xba\xbe') or b'factoryPanelItemRenderDistance' not in data:
            raise ValueError('Missing patch: '+cls)
    if not any(n.startswith('META-INF/jarjar/') and n.endswith('.jar') for n in z.namelist()):
        raise ValueError('Expected normal JAR with bundled dependencies')
PY
install -m644 "$jar" "$out/$candidate"
sha256sum "$out/$candidate" > "$out/$candidate.sha256"
echo 'Use a disposable client; replace the original Create JAR. Do not change the dedicated server.'
