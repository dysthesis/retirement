#!/usr/bin/env bash
# Rebuild Continuity with its emissive pass skipped for blocks without emissive sprites; refresh pack hashes separately.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
source_commit=2627daf8c2d9c8edfcd363a49419a00cd78c2fdd # Release 3.0.11
version=3.0.11+retirement.1
jar="ContinuityNeoForge-$version+1.21.1.jar"

git -C "$work" init --quiet
git -C "$work" fetch --quiet --depth=1 https://github.com/aspctt/continuity-neoforge.git "$source_commit"
git -C "$work" checkout --quiet --detach FETCH_HEAD
test "$(git -C "$work" rev-parse HEAD)" = "$source_commit"
git -C "$work" apply "$root/scripts/continuity-emissive-scan.patch"
(
  cd "$work"
  ./gradlew --no-daemon --max-workers=2 -Pmod_version="$version" :1.21.1:jar
)
install -m644 "$work/versions/1.21.1/build/libs/$jar" "$root/packwiz/mods/$jar"
