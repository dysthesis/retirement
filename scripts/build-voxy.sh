#!/usr/bin/env bash
# Private native NeoForge 1.21.1/Sodium 0.8 build via falling-colud/voxy-forged.
# Upstream forbids redistributing unofficial builds: https://modrinth.com/mod/voxy
# Requires JDK 21. Pack metadata and exports are updated separately after verification.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
source_commit=02589c94a1946014a77f4e87e5298d4f1b7fce60
jar=voxy-1.1.0+retirement.3+neoforge.jar

git -C "$work" init --quiet
git -C "$work" fetch --quiet --depth=1 https://github.com/falling-colud/voxy-forged.git "$source_commit"
git -C "$work" checkout --quiet --detach FETCH_HEAD
test "$(git -C "$work" rev-parse HEAD)" = "$source_commit"
git -C "$work" apply "$root/scripts/voxy.patch"
(
  cd "$work"
  GITHUB_ACTIONS=true ./gradlew --no-daemon --max-workers=2 \
    -Pminecraft_version=1.21.1 -Pneoforge_version=21.1.265 \
    -Pmod_version=1.1.0+retirement.3+neoforge fluidBlockRegression jar
  echo "0f2781db79bec5c5aee3e74a2f685416fb26d306f2f30ba4d9be5980498f19fd  build/libs/$jar" | sha256sum --check --strict
)
install -m644 "$work/build/libs/$jar" "$root/packwiz/mods/$jar"
