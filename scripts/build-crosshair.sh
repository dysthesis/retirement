#!/usr/bin/env bash
# Native MIT-licensed Crosshair Addons 2.2.2 / WalksyLib 2.0.5 for NeoForge 21.1.265.
# Requires JDK 21, git and patch. Stages both jars; never edits a launcher or pack index.
# Both artifacts are client-only; preserve that side when importing the raw jars.
set -euo pipefail
scripts="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
output="${1:?Usage: build-crosshair.sh OUTPUT_DIRECTORY}"
mkdir -p -- "$output"
output="$(realpath -- "$output")"
work="$(mktemp -d "$output/.crosshair.XXXXXXXXXX")"
trap 'rm -rf -- "$work"' EXIT
fetch() {
  local repository="$1" commit="$2" directory="$3"
  git -C "$work" init --quiet "$directory"
  git -C "$work/$directory" fetch --quiet --depth=1 "https://github.com/Walksy/$repository.git" "$commit"
  git -C "$work/$directory" checkout --quiet --detach FETCH_HEAD
  test "$(git -C "$work/$directory" rev-parse HEAD)" = "$commit"
}
fetch CrosshairAddons-PublicVersion e5356375bccd7e0ed75ba6d0e46218e0e43c04b7 CrosshairAddons
fetch WalksyLib 60f7de55a14e29fc0a258ff1354f17ed98c47eb5 WalksyLib
patch --directory="$work" --strip=1 --batch --fuzz=0 --input="$scripts/crosshair.patch"
(
  cd -- "$work/WalksyLib"
  java -classpath "$work/CrosshairAddons/gradle/wrapper/gradle-wrapper.jar" \
    org.gradle.wrapper.GradleWrapperMain --no-daemon --max-workers=2 \
    -Pwalksylib.versions=1.21-1.21.1 -Pwalksylib.loaders=neoforge \
    -Pmod_version=2.0.5+retirement.1 collectJars
)
(
  cd -- "$work/CrosshairAddons"
  java -classpath "$work/CrosshairAddons/gradle/wrapper/gradle-wrapper.jar" \
    org.gradle.wrapper.GradleWrapperMain --no-daemon --max-workers=2 \
    -Pcrosshairaddons.versions=1.21-1.21.1 -Pcrosshairaddons.loaders=neoforge \
    -Pmod_version=2.2.2+retirement.1 -Pwalksylib.neoforge.version=2.0.5+retirement.1 \
    :neoforge-1.21-1.21.1:checkBlitSpriteContract collectJars
)
library=WalksyLib-2.0.5+retirement.1+1.21-1.21.1-neoforge.jar
crosshair=CrosshairAddons-2.2.2+retirement.1+1.21-1.21.1-neoforge.jar
printf '%s  %s\n' \
  42b2799424f0a8c2ccbec634e6e477ad42dba0387b8c9de83795f0d885af7130 "$work/WalksyLib/build/libs/$library" \
  81d7d64f69b9ac07fccf45811efc355b1bb9df81c052d956ba73b9412091588a "$work/CrosshairAddons/build/libs/$crosshair" |
  sha256sum --check --strict
install -m644 -- "$work/WalksyLib/build/libs/$library" "$output/$library"
install -m644 -- "$work/CrosshairAddons/build/libs/$crosshair" "$output/$crosshair"
sha256sum -- "$output/$library" "$output/$crosshair"
