#!/usr/bin/env bash
# Private build of https://github.com/MCRcortex/voxy via m3t4f1v3's 1.21.1/Sodium 0.8 backport.
# Upstream forbids redistributing unofficial builds: https://modrinth.com/mod/voxy
# Requires JDK 21, git, sha256sum and packwiz; no existing mod is updated.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT

git -C "$work" init --quiet
git -C "$work" fetch --quiet --depth=1 https://github.com/m3t4f1v3/voxy.git ff9b80ac96b030b21af3e868c1255e0ca9737ec7
git -C "$work" checkout --quiet --detach FETCH_HEAD
git -C "$work" apply "$root/scripts/voxy.patch"
(
    cd "$work"
    # Override the backport's unresolved properties merge without changing the pack.
    GITHUB_ACTIONS=true ./gradlew --no-daemon --max-workers=2 \
        -Pminecraft_version=1.21.1 -Ploader_version=0.20.1 \
        -Pfabric_api_version=0.116.17+1.21.1 \
        -Pmod_version=0.2.15-beta+retirement.1 remapJar
    # Fail closed on compiler/dependency drift before replacing the tested binary.
    echo 'ab34ed4e4862269e34488274eea19be479b7a15f0bdb0148af67ec809f93aa95  build/libs/voxy-0.2.15-beta+retirement.1.jar' | sha256sum --check
)
install -m644 "$work/build/libs/voxy-0.2.15-beta+retirement.1.jar" "$root/packwiz/mods/voxy-0.2.15-beta+retirement.1.jar"
cd "$root/packwiz"
packwiz refresh
packwiz modrinth export
