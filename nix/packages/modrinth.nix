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
  outputHash = "sha256-zxRN8ZpssG9ZGn3Jm80nUKpg29eDXM2daw/lb81HpiU=";

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
