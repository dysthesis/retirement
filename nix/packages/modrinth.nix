# Modrinth pack with server-side stuff included, mainly for testing
{
  self,
  runCommand,
  packwiz,
  cacert,
  python3,
  ...
}:
runCommand "retirement-${builtins.hashFile "sha256" ../../packwiz/pack.toml}.mrpack" {
  nativeBuildInputs = [packwiz python3];

  outputHashMode = "flat";
  outputHashAlgo = "sha256";
  outputHash = "sha256-Qa0M/4mWwqlTvrpYsL40ih/amU2JKurgSqhSwLS9HYw=";

  SSL_CERT_FILE = "${cacert}/etc/ssl/certs/ca-bundle.crt";
} ''
    export HOME="$TMPDIR"

    cp -r ${self}/packwiz ./packwiz
    chmod -R u+w ./packwiz

    cd packwiz

    python3 - <<'PY'
  from pathlib import Path

  for path in Path(".").rglob("*.pw.toml"):
      original = path.read_text()
      updated = original.replace(
          'side = "server"',
          'side = "both"',
      )
      if updated != original:
          path.write_text(updated)
  PY

    packwiz \
      --cache "$TMPDIR/packwiz-cache" \
      modrinth export \
      --output "$out"
''
