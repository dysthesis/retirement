#!/usr/bin/env bash
# Rebuild EMI Loot's native NeoForge immutable async snapshots with JDK 21; refresh pack hashes separately.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
commit=fce9aa71183d551c4c7864c35ab005b18553c968
jar=emi_loot-0.7.10+1.21+retirement.1+neoforge.jar
curl --fail --location "https://codeload.github.com/fzzyhmstrs/EMI_loot/tar.gz/$commit" --output "$work/source.tar.gz"
echo "38e34d10d6687efd24ebfa6bbebd732d1abcea1f8f5683bdba7c4c725bd22e56  $work/source.tar.gz" | sha256sum --check --strict
tar -xzf "$work/source.tar.gz" -C "$work"
source="$work/EMI_loot-$commit"
patch --directory="$source" --strip=1 --batch --fuzz=0 --input="$root/scripts/emi-loot.patch"
# Shared Yarn sources need an intermediary-mapped compile API; only the NeoForge jar is shipped.
curl --fail --location 'https://cdn.modrinth.com/data/fRiHVvU7/versions/on5GT1qh/emi-1.1.24%2B1.21.1%2Bfabric.jar' --output "$work/emi-common.jar"
echo '2680e7b0a93152d4220afdc30a0452c911dc4b5c9ce1db1b7246c21b777bc2a1945fe97c98c09941d31b7478ae357135a1ef51cd3ba92d08dce35202a830b70d  '"$work/emi-common.jar" | sha512sum --check --strict
curl --fail --location 'https://cdn.modrinth.com/data/fRiHVvU7/versions/5sIPA1To/emi-1.1.24%2B1.21.1%2Bneoforge.jar' --output "$work/emi.jar"
echo 'f4c45ed686fe617311d6debadcb6ace5963e66f8cfe0cfed398231f081f87407070efc7a73c8b695d158f1d87a97180737b9107a46771e77df2bc9a7dc715ebd  '"$work/emi.jar" | sha512sum --check --strict
(
  cd "$source"
  bash ./gradlew --no-daemon --max-workers=2 \
    -Pmod_version=0.7.10+1.21+retirement.1 -Penabled_platforms=neoforge \
    -PretirementEmiCommon="$work/emi-common.jar" -PretirementEmi="$work/emi.jar" :neoforge:remapJar
  echo "1a47f1e71921a8b7d5e4e28314e3141ea05d405a227f6244c85b2b357a50c4c0  neoforge/build/libs/$jar" | sha256sum --check --strict
)
install -m644 "$source/neoforge/build/libs/$jar" "$root/packwiz/mods/$jar"
