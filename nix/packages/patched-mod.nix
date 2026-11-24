# Build the private JAR as a flat fixed-output derivation. Only this stage
# needs network access; normal pack assembly uses its verified store output.
{
  lib,
  runCommand,
  jdk21,
  gitMinimal,
  python3,
  unzip,
  cacert,
  stdenvNoCC,
  kind,
  sha256,
}: let
  definitions = {
    voxy = {
      script = "build-voxy-memory.sh";
      jar = "voxy-1.1.0+retirement.4+neoforge.jar";
      files = [
        ../../scripts/build-voxy-memory.sh
        ../../scripts/build-voxy.sh
        ../../scripts/voxy.patch
        ../../scripts/voxy-memory.patch
        ../../scripts/promote-voxy-memory.py
      ];
    };
    create = {
      script = "build-create-panel.sh";
      jar = "create-1.21.1-6.0.10-retirement-panel-test.jar";
      files = [
        ../../scripts/build-create-panel.sh
        ../../scripts/create-panel-render-only.patch
        ../../scripts/create-panel-reproducible.patch
      ];
    };
  };
  definition = definitions.${kind};
  source = lib.fileset.toSource {
    root = ../..;
    fileset = lib.fileset.unions definition.files;
  };
  # A fixed-output store path otherwise ignores changes to build inputs.
  # Force a fresh path when any build source or relevant tool changes.
  fingerprint = builtins.substring 0 20 (builtins.hashString "sha256" (builtins.unsafeDiscardStringContext (lib.concatStringsSep ":" [
    (toString source)
    (builtins.hashFile "sha256" ./patched-mod.nix)
    jdk21.drvPath
    gitMinimal.drvPath
    python3.drvPath
    unzip.drvPath
    cacert.drvPath
    stdenvNoCC.drvPath
  ])));
in
  assert sha256 == null || builtins.match "[0-9a-f]{64}" sha256 != null;
    runCommand "retirement-${kind}-${fingerprint}.jar" {
      nativeBuildInputs = [jdk21 gitMinimal python3 unzip cacert];
      outputHashMode = "flat";
      outputHashAlgo = "sha256";
      outputHash = if sha256 == null then lib.fakeHash else sha256;
      # The builder must fetch Gradle/Maven dependencies, not disable the sandbox
      # for the whole pack. No credentials or user Gradle caches are required.
      preferLocalBuild = false;
      allowSubstitutes = true;
    } ''
      export HOME="$TMPDIR/home"
      export GRADLE_USER_HOME="$TMPDIR/gradle"
      export JAVA_HOME=${jdk21}
      export GIT_CONFIG_NOSYSTEM=1
      export GIT_CONFIG_GLOBAL=/dev/null
      export SSL_CERT_FILE=${cacert}/etc/ssl/certs/ca-bundle.crt
      export GIT_SSL_CAINFO="$SSL_CERT_FILE"
      export TZ=UTC
      mkdir -p "$HOME" "$GRADLE_USER_HOME"
      cat > "$GRADLE_USER_HOME/gradle.properties" <<'EOF'
      org.gradle.java.installations.auto-download=false
      org.gradle.java.installations.auto-detect=false
      org.gradle.java.installations.paths=${jdk21}
      EOF
      bash ${source}/scripts/${definition.script} "$TMPDIR/candidate"
      test -f "$TMPDIR/candidate/${definition.jar}"
      install -m644 "$TMPDIR/candidate/${definition.jar}" "$out"
    ''
