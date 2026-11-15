#!/usr/bin/env bash
# Private native NeoForge 1.21.1 builds from MIT-licensed Let's Do EMI Compat 2.0.3.
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
download fRiHVvU7 5sIPA1To emi-1.1.24+1.21.1+neoforge.jar \
    f4c45ed686fe617311d6debadcb6ace5963e66f8cfe0cfed398231f081f87407070efc7a73c8b695d158f1d87a97180737b9107a46771e77df2bc9a7dc715ebd
if [[ "$target" == letsdo ]]; then
    download lhGA9TYQ 1IiqEQGl architectury-13.0.11-neoforge.jar \
        d9f7c3bb8162577dfb461ffdf04bd6a3563c7586934a0e2a744c14421beffb8286f0d88d4c758317003f20f99fe8072a39b9d675af061e036970d36db36027f0
    download 1DWmBJVA NmoLFrhq letsdo-vinery-neoforge-1.5.6.jar \
        51c31c756de0f54a91f28c4d072925e0793ae70aefde2d23ea7ca3c5b7050ce04cc1885531ea459d1ea6adefb05d7c37616e3c9102f0fea50234f04043f6b970
    download GyKzAh3l HN4rzKRl letsdo-beachparty-neoforge-2.1.5.jar \
        b992f87e638c3642816046b44bec1a3f41df01c61204bcedf3fee5ee7b229f64c0d327fcb3fbb758c7ded5b9d50da6b1a310ea23dcfbba8177022e8f9468ef36
    download Eh11TaTm kGYbyn9P letsdo-herbalbrews-neoforge-1.1.4.jar \
        281bac102511bf7753371ab7ed488d6990dfb0caae0f216b931d3a05c74adfbe28330910e76d7eea0268f0a7d64997a7c0d7d9b3fc9efb43d9711487f36b4989
    download ra7o6Sl7 7lmxOKYR letsdo-meadow-neoforge-1.4.10.jar \
        6f13b65eb9b1305c376af1409466946972830210a591f074d82c858d112de8c0f6fd420727f23b7c3c388b2192d90cd88c343e60e33403846f56e6309b50e40d
    artifact=emi-letsdo-compat-2.0.3+retirement.3+neoforge.jar
else
    patch --directory="$source" --strip=2 --batch --fuzz=0 --input="$scripts/rechiseled-emi.patch"
    download B0g2vT6l 6muGRqvu rechiseled-1.2.6-neoforge-mc1.21.jar \
        fc7556e42439e526edddafdbde108cd1326fd5742d75ae73fe9519f57af18b75cd2861053247b65fa3acd9c58e186bc540496d1e7095a3206b401d9459958e34
    download rOUBggPv sLRKmslC supermartijn642corelib-1.1.26a-neoforge-mc1.21.jar \
        e90a1f1a2a4b1b095b6692e82b3f1bbf3aafa5653fa80759ac4243385ac1d10605b8713107847a9d0f5e8e4da161009aa3380ae20ca8f70784abfaa85e868492
    artifact=emi-rechiseled-1.0.0+retirement.3+neoforge.jar
fi
(
    cd -- "$source"
    bash ./gradlew --no-daemon --max-workers=2 -PretirementDependencies="$dependencies" checkRecipeSemantics jar
    cd -- build/libs
    test -s "$artifact"
    sha256sum --check --strict --ignore-missing "$scripts/emi-compat.sha256"
)
install -m644 -- "$source/build/libs/$artifact" "$output/$artifact"
sha256sum -- "$output/$artifact"
