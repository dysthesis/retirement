#!/usr/bin/env bash
# Rebuild EMI's native NeoForge resolved-ingredient repair with JDK 21; refresh pack hashes separately.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
source_commit=322171ee1d85cb1809bb7afd23d432b685756247
jar=emi-1.1.24+retirement.1+1.21.1+neoforge.jar

git -C "$work" init --quiet
git -C "$work" fetch --quiet --depth=1 https://github.com/emilyploszaj/emi.git "$source_commit"
git -C "$work" checkout --quiet --detach FETCH_HEAD
test "$(git -C "$work" rev-parse HEAD)" = "$source_commit"
git -C "$work" apply "$root/scripts/emi.patch"
(
    cd "$work"
    RELEASE=true ./gradlew --no-daemon --max-workers=2 \
        -Pmod_version=1.1.24+retirement.1 -Penabled_platforms=neoforge \
        -Pneoforge_version=21.1.265 :neoforge:remapJar
    echo "be2a0a7d474a69a41ae31f0e8247ff6d929c50ccd47b7acc89e332bf6c9d0f2e  neoforge/build/libs/$jar" | sha256sum --check --strict
)
install -m644 "$work/neoforge/build/libs/$jar" "$root/packwiz/mods/$jar"
