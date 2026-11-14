{
  self,
  runCommand,
  packwiz,
  cacert,
  ...
}:
runCommand "retirement.mrpack" {
  nativeBuildInputs = [packwiz];

  outputHashMode = "flat";
  outputHashAlgo = "sha256";
  outputHash = "sha256-gt58PVnk1XIoY6P5RuBu0izsRnsgWD75Hl4qZwSW/ws=";

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
