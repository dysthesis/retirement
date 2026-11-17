{
  runCommand,
  python3,
  sources,
  client,
  server,
}:
runCommand "retirement-modpacks-check" {nativeBuildInputs = [python3];} ''
  cp ${../../scripts/rehash.py} rehash.py
  cp ${../../scripts/test-rehash.py} test-rehash.py
  python3 -B test-rehash.py

  python3 ${./check-modpacks.py} ${sources.src} ${client} ${server}
  touch "$out"
''
