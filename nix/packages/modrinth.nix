{
  self,
  runCommand,
  packwiz,
  cacert,
  ...
}:
runCommand "retirement-${builtins.hashFile "sha256" ../../packwiz/pack.toml}.mrpack" {
  nativeBuildInputs = [packwiz];

  outputHashMode = "flat";
  outputHashAlgo = "sha256";
  outputHash = "sha256-g8XZNOJv1++PV0V4YSFUv1lsdLH3qTIYCam9TwzxSgo=";

  SSL_CERT_FILE = "${cacert}/etc/ssl/certs/ca-bundle.crt";
} ''
  export HOME="$TMPDIR"

  cp -r ${self}/packwiz ./packwiz
  chmod -R u+w ./packwiz

  cd packwiz

  packwiz \
    --cache "$TMPDIR/packwiz-cache" \
    modrinth export \
    --output "$out"
''
