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
  outputHash = "sha256-qVsTF8SE0e33IMlPVBEohSOG13+SdeG0/xL36b2sKF0=";

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
