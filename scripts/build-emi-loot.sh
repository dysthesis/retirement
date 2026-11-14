#!/usr/bin/env bash
# Rebuild EMI Loot's immutable async input snapshots with JDK 21; refresh pack metadata separately.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
commit=fce9aa71183d551c4c7864c35ab005b18553c968
jar=emi_loot-0.7.10+1.21+retirement.1+fabric.jar
curl --fail --location "https://codeload.github.com/fzzyhmstrs/EMI_loot/tar.gz/$commit" --output "$work/source.tar.gz"
echo "38e34d10d6687efd24ebfa6bbebd732d1abcea1f8f5683bdba7c4c725bd22e56  $work/source.tar.gz" | sha256sum --check --strict
tar -xzf "$work/source.tar.gz" -C "$work"
source="$work/EMI_loot-$commit"
patch --directory="$source" --strip=1 --batch --fuzz=0 --input="$root/scripts/emi-loot.patch"
curl --fail --location 'https://cdn.modrinth.com/data/fRiHVvU7/versions/on5GT1qh/emi-1.1.24%2B1.21.1%2Bfabric.jar' --output "$work/emi.jar"
echo '2680e7b0a93152d4220afdc30a0452c911dc4b5c9ce1db1b7246c21b777bc2a1945fe97c98c09941d31b7478ae357135a1ef51cd3ba92d08dce35202a830b70d  '"$work/emi.jar" | sha512sum --check --strict
(
    cd "$source"
    bash ./gradlew --no-daemon --max-workers=2 \
        -Pmod_version=0.7.10+1.21+retirement.1 -Penabled_platforms=fabric \
        -PretirementEmi="$work/emi.jar" :fabric:remapJar
    echo "4b5cf82fda589b9cc5f6045edb1fe69af16897839f5cc9a52c0f0990a62e7e48  fabric/build/libs/$jar" | sha256sum --check --strict
)
install -m644 "$source/fabric/build/libs/$jar" "$root/packwiz/mods/$jar"
rm -f -- "$root/packwiz/mods/emi-loot.pw.toml"
