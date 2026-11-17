{
  lib,
  fetchurl,
  runCommand,
  python3,
  root,
}: let
  pack = builtins.fromTOML (builtins.readFile (root + "/pack.toml"));
  resolveDownload = import ./download.nix {inherit lib;};

  safePath = path:
    lib.all (component: !(builtins.elem component ["" "." ".."])) (lib.splitString "/" path);

  checkedFile = file: format: hash: let
    path = root + "/${file}";
  in
    if !(safePath file)
    then throw "Unsafe Packwiz path: ${file}"
    else if builtins.hashFile format path == hash
    then path
    else throw "Packwiz hash mismatch: ${file}";

  indexFile = checkedFile pack.index.file pack.index.hash-format pack.index.hash;
  index = builtins.fromTOML (builtins.readFile indexFile);

  files = map (entry: let
    definition = checkedFile entry.file (entry.hash-format or index.hash-format) entry.hash;
    metafile = entry.metafile or false;
    mod = builtins.fromTOML (builtins.readFile definition);
    directory = builtins.dirOf entry.file;

    download = fetchurl (resolveDownload mod);
  in
    entry
    // {
      inherit definition;
      source =
        if metafile
        then download
        else "${src}/${entry.file}";
      destination =
        if metafile
        then lib.optionalString (directory != ".") "${directory}/" + mod.filename
        else entry.file;
      side =
        if metafile
        then mod.side or "both"
        else "both";
    }
    // lib.optionalAttrs metafile {
      inherit mod;
      url = download.url;

      # Hash each immutable payload once, not again for every pack revision.
      hashes = runCommand "${download.name}-hashes.json" {nativeBuildInputs = [python3];} ''
        python3 - ${download} > "$out" <<'PY'
        import hashlib
        import json
        import sys

        hashes = {name: hashlib.new(name) for name in ("sha1", "sha256", "sha512")}

        with open(sys.argv[1], "rb") as source:
            while chunk := source.read(1024 * 1024):
                for digest in hashes.values():
                    digest.update(chunk)
            result = {name: digest.hexdigest() for name, digest in hashes.items()}
            result["length-bytes"] = str(source.tell())

        print(json.dumps(result))
        PY
      '';
    })
  index.files;

  # Only indexed pack inputs affect assembly, not the flake's entire source tree.
  src = lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.unions ([(root + "/pack.toml") indexFile] ++ map (entry: entry.definition) files);
  };

  destinations = ["pack.toml" "packwiz.json"] ++ map (entry: entry.destination) files;
  rawPaths = map (entry: entry.file) (builtins.filter (entry: !(entry.metafile or false)) files);
in
  assert lib.all (entry:
    safePath entry.destination
    && builtins.elem entry.side ["" "both" "client" "server"]
    && (!(entry.metafile or false) || safePath entry.mod.filename))
  files;
  assert lib.length destinations == lib.length (lib.unique destinations);
  assert lib.all (path: builtins.elem path rawPaths) (pack.options.client-only-overrides or []); {
    inherit pack index files src;
  }
