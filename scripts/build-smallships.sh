#!/usr/bin/env bash
# Private lifecycle repair of the All Rights Reserved Small Ships 2.0.2 native build.
# Requires JDK 21, Python 3, curl, patch and tar. Stages a jar; never edits a launcher or pack index.
set -euo pipefail
scripts="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
output="${1:?Usage: build-smallships.sh OUTPUT_DIRECTORY}"
mkdir -p -- "$output"
output="$(realpath -- "$output")"
work="$(mktemp -d "$output/.smallships.XXXXXXXXXX")"
trap 'rm -rf -- "$work"' EXIT
commit=4bfb8680a3fecd8c7e71506b941a79c51c49dffb
curl --fail --location --retry 3 \
  "https://codeload.github.com/talhanation/smallships/tar.gz/$commit" \
  --output "$work/source.tar.gz"
printf '%s  %s\n' f00f9feb944df2974ce6b9b751a0a7de3f7bcbd5bf8b35dcdac498ccca304530 "$work/source.tar.gz" | sha256sum --check --strict
tar -xzf "$work/source.tar.gz" --directory "$work"
source="$work/smallships-$commit"
patch --directory="$source" --strip=1 --batch --fuzz=0 --input="$scripts/smallships.patch"
(
  cd -- "$source"
  bash ./gradlew --no-daemon --max-workers=2 \
    -Pneoforge_version=21.1.265 -Pmod_version=2.0.2+retirement.1 :neoforge:remapJar
)
artifact=smallships-neoforge-1.21.1-2.0.2+retirement.1.jar
curl --fail --location --retry 3 \
  "https://cdn.modrinth.com/data/rGWEHQrP/versions/2iLK0Wz6/smallships-neoforge-1.21.1-2.0.2.jar" \
  --output "$work/release.jar"
printf '%s  %s\n' 3ca7ec4a9f6800a5e9f90cb273e8495c5919c2d9a0707160a1d4391fa11c5525e3f76038f877023929d3e3104b3df79e8afc1138de0f7df64530649cb3b76d20 "$work/release.jar" | sha512sum --check --strict
python3 "$scripts/repack-smallships.py" "$work/release.jar" "$source/neoforge/build/libs/$artifact" "$work/$artifact"
printf '%s  %s\n' db608f190a063baa4b9afd49daed52f8bb04f0876578180148a41aa39ae02658 "$work/$artifact" | sha256sum --check --strict
install -m644 -- "$work/$artifact" "$output/$artifact"
sha256sum -- "$output/$artifact"
