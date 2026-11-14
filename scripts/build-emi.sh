#!/usr/bin/env bash
# Rebuild EMI's resolved-ingredient repair fix with JDK 21; refresh pack metadata separately.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
source_commit=322171ee1d85cb1809bb7afd23d432b685756247
jar=emi-1.1.24+retirement.1+1.21.1+fabric.jar

git -C "$work" init --quiet
git -C "$work" fetch --quiet --depth=1 https://github.com/emilyploszaj/emi.git "$source_commit"
git -C "$work" checkout --quiet --detach FETCH_HEAD
test "$(git -C "$work" rev-parse HEAD)" = "$source_commit"
git -C "$work" apply "$root/scripts/emi.patch"
(
    cd "$work"
    RELEASE=true ./gradlew --no-daemon --max-workers=2 \
        -Pmod_version=1.1.24+retirement.1 -Penabled_platforms=fabric :fabric:remapJar
    echo "2e1248afda209b8990a76d7d1f4f86942011240c2963ca12cf26575f59886556  fabric/build/libs/$jar" | sha256sum --check --strict
)
install -m644 "$work/fabric/build/libs/$jar" "$root/packwiz/mods/$jar"
rm -f -- "$root/packwiz/mods/emi.pw.toml"
