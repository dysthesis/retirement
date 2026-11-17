{lib}: mod: let
  download = mod.download;
  mode = download.mode or "url";
  fileID = mod.update.curseforge.file-id;
  fileDirectory = "${toString (builtins.div fileID 1000)}/${toString (lib.mod fileID 1000)}";
in {
  name = mod.filename;
  outputHashAlgo = download.hash-format;
  outputHash = download.hash;

  url =
    if builtins.elem mode ["" "url"]
    then download.url
    else if mode == "metadata:curseforge"
    then "https://mediafilez.forgecdn.net/files/${fileDirectory}/${lib.escapeURL mod.filename}"
    else throw "Unsupported Packwiz download mode: ${mode}";
}
