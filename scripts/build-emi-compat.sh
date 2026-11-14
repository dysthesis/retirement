#!/usr/bin/env bash
# Private Fabric 1.21.1 builds from MIT-licensed Let's Do EMI Compat 2.0.3.
# Requires JDK 21, curl, patch and tar. Never installs or updates pack jars.
set -euo pipefail
scripts="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
output="${1:?Usage: build-emi-compat.sh OUTPUT_DIRECTORY [letsdo|rechiseled]}"
target="${2:-letsdo}"
case "$target" in
    letsdo|rechiseled) ;;
    *) printf 'Unknown target: %s\n' "$target" >&2; exit 2 ;;
esac
mkdir -p -- "$output"
output="$(realpath -- "$output")"
work="$(mktemp -d "$output/.emi-compat.XXXXXXXXXX")"
trap 'rm -rf -- "$work"' EXIT
commit=5c8dad12f3a996b4eab6483e2761e41243368064
curl --fail --location --retry 3 \
    "https://codeload.github.com/Pandaismyname1/Let-s-Do-EMI-Compat/tar.gz/$commit" \
    --output "$work/source.tar.gz"
printf '%s  %s\n' 5fd4813dbdfd14980908fdecee9018c63164e4c5acade8a2fb22b83956a0cb8a "$work/source.tar.gz" | sha256sum --check --status
tar -xzf "$work/source.tar.gz" --directory "$work"
source="$work/Let-s-Do-EMI-Compat-$commit"
patch --directory="$source" --strip=2 --batch --fuzz=0 --input="$scripts/letsdo-emi.patch"
dependencies="$work/dependencies"
mkdir -p -- "$dependencies"
download() {
    local project="$1" version="$2" file="$3" checksum="$4"
    curl --fail --location --retry 3 \
        "https://cdn.modrinth.com/data/$project/versions/$version/${file//+/%2B}" \
        --output "$dependencies/$file"
    printf '%s  %s\n' "$checksum" "$dependencies/$file" | sha512sum --check --status
}
download fRiHVvU7 on5GT1qh emi-1.1.24+1.21.1+fabric.jar \
    2680e7b0a93152d4220afdc30a0452c911dc4b5c9ce1db1b7246c21b777bc2a1945fe97c98c09941d31b7478ae357135a1ef51cd3ba92d08dce35202a830b70d
if [[ "$target" == letsdo ]]; then
    download lhGA9TYQ Pzc2FP5K architectury-13.0.11-fabric.jar \
        53314eb34890b11ad3c06c6f3ba2d01ae1ca756235ce4f0574e4b0544952a2ab3c628c81b521653d6487d62c5dc3055e06fed6367a3a499bafad909512f0c716
    download 1DWmBJVA r0pP4RB4 letsdo-vinery-fabric-1.5.6.jar \
        b99065c39fead693ff4fac578d89feb60b047cfa30ffb7cef4e81179aab408e4f8c1437e9632cfb7c89e16fd7557890db2f47af69351220ea2d60e23ba672231
    download GyKzAh3l jeZE0Qav letsdo-beachparty-fabric-2.1.5.jar \
        c8548e036590ff418a25b323f582a647add1a3bb1f14ea6a3600259a6ff472744bc73c8a9aa7081742edda4cc55b63ba84705537314671c690383be50e9f48ac
    download Eh11TaTm 43g8sVYA letsdo-herbalbrews-fabric-1.1.4.jar \
        08dc756092b5ffa7bf820761ad43ff4e87cb10b46f4c9fbfe54b4b2dc917c15c5ca98a672ed7f146d956e56b93f3d56d603d307c5b68d5756fca6c9d9f890490
    download ra7o6Sl7 CgcJkvI8 letsdo-meadow-fabric-1.4.10.jar \
        8bed35990616c29a54141b0f93ab5f5c98040f5f0da6a139bcc9b0d4edb68a7b1c996058dfcf49c2a8e1215bb221fce09b787bf1c0d99e416f9353d43221422d
    artifact=emi-letsdo-compat-2.0.3+retirement.2.jar
else
    patch --directory="$source" --strip=2 --batch --fuzz=0 --input="$scripts/rechiseled-emi.patch"
    download B0g2vT6l 7411ZFAs rechiseled-1.2.6-fabric-mc1.21.jar \
        5541c06a62364ecf30118d0e3246d0a4ce3beb5bf835fec86ac4749a6ac3e432ea0a601a88b3a7194ab3bf2d5ba9529a3714898b960cb86c532561f228b2f70a
    download rOUBggPv MJdcUmeo supermartijn642corelib-1.1.26a-fabric-mc1.21.jar \
        cde37b283685a644af967cff9b4ef6473d23ea4f56e882b31d084fd9483d9de950198fdf39a162946dd3da91a6827cf27aa45bca276e34b7706a644ff0599bbe
    download P7dR8mSH 5SwzqWUu fabric-api-0.116.18+1.21.1.jar \
        9f721c253ae2e9823cb548e8ec132c9928f80a65184e9b8dcfc489a8d632df20cbfea1e65ff8a4333bdb295c41fbe2228b43e4d41c7355d42ed4637a785840a1
    (
        cd -- "$dependencies"
        jar --extract --file fabric-api-0.116.18+1.21.1.jar \
            META-INF/jars/fabric-api-base-0.116.18.jar \
            META-INF/jars/fabric-lifecycle-events-v1-0.116.18.jar \
            META-INF/jars/fabric-networking-api-v1-0.116.18.jar
    )
    artifact=emi-rechiseled-1.0.0+retirement.1.jar
fi
(
    cd -- "$source"
    bash ./gradlew --no-daemon --max-workers=2 -PretirementDependencies="$dependencies" checkRecipeSemantics remapJar
    cd -- build/libs
    test -s "$artifact"
    sha256sum --check --strict --ignore-missing "$scripts/emi-compat.sha256"
)
install -m644 -- "$source/build/libs/$artifact" "$output/$artifact"
sha256sum -- "$output/$artifact"
