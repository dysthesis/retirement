#!/usr/bin/env bash
# Private build of https://github.com/MCRcortex/voxy via m3t4f1v3's 1.21.1/Sodium 0.8 backport.
# Upstream forbids redistributing unofficial builds: https://modrinth.com/mod/voxy
# Requires JDK 21. Pack metadata and exports are updated separately after verification.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
source_commit=ff9b80ac96b030b21af3e868c1255e0ca9737ec7
jar=voxy-0.2.15-beta+retirement.2.jar

git -C "$work" init --quiet
git -C "$work" fetch --quiet --depth=1 https://github.com/m3t4f1v3/voxy.git "$source_commit"
git -C "$work" checkout --quiet --detach FETCH_HEAD
test "$(git -C "$work" rev-parse HEAD)" = "$source_commit"
git -C "$work" apply "$root/scripts/voxy.patch"
(
    cd "$work"
    # Override the backport's unresolved properties merge without changing the pack.
    GITHUB_ACTIONS=true ./gradlew --no-daemon --max-workers=2 \
        -Pminecraft_version=1.21.1 -Ploader_version=0.20.1 \
        -Pfabric_api_version=0.116.17+1.21.1 \
        -Pmod_version=0.2.15-beta+retirement.2 fluidBlockRegression remapJar
    # Fail closed on compiler/dependency drift before replacing the tested binary.
    echo "a596f26321701d7a10dcfb306a5784aecf27b484b4d29e72c71d4b0310d17118  build/libs/$jar" | sha256sum --check --strict
)
install -m644 "$work/build/libs/$jar" "$root/packwiz/mods/$jar"
rm -f -- "$root/packwiz/mods/voxy-0.2.15-beta+retirement.1.jar"
