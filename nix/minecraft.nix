{
  self,
  inputs,
  ...
}: {
  flake.nixosModules.default = {
    pkgs,
    lib,
    ...
  }: let
    modpack = pkgs.fetchPackwizModpack {
      src = "${self}/packwiz";
      packHash = "sha256-D49JViyqUZXgUsyJS5LjbfLZAgb5bIr2kmD6hLL2U4c=";
    };
  in {
    imports = [
      inputs.nix-minecraft.nixosModules.minecraft-servers
    ];

    nixpkgs.overlays = [
      inputs.nix-minecraft.overlay
    ];

    services.minecraft-servers = {
      enable = true;
      eula = true;

      servers.retirement = {
        enable = true;
        autoStart = true;
        openFirewall = true;

        package = pkgs.fabricServers.fabric-1_21_1;

        jvmOpts = "-Xms8G -Xmx10G";

        serverProperties = {
          server-port = 25565;
          max-players = 10;
          motd = "<INSERT MOTD HERE>";
          difficulty = "hard";
          white-list = true;
        };

        symlinks =
          {mods = "${modpack}/mods";}
          # Fetch at build time for offline startup; leave onnx-cache writable.
          // lib.mapAttrs' (name: hash:
            lib.nameValuePair "terrain-diffusion-models/${name}" (pkgs.fetchurl {
              url = "https://huggingface.co/xandergos/terrain-diffusion-30m-onnx/resolve/ad2df557eca5645f588766101cf3bc3682455c3e/${name}";
              inherit hash;
            })) {
            "base_model.onnx" = "sha256-VD3niPc9CkASaFyQgln2FWARAqrOR1GuzOxkFUuhRcA=";
            "coarse_model.onnx" = "sha256-1soVshsuNdXllKmsekJJojdlkMCtK1tJoebi0DNFAAg=";
            "decoder_model.onnx" = "sha256-ZHOuR8puxNdD0w/k9dOB/kFYiZcU7/CbdiAFvb3vaME=";
            "pipeline_data.json" = "sha256-4xMsPvDGXYYTYV+SeP/iO72TY93Nh/HMbxhFa8ye/lw=";
            "world_pipeline_config.json" = "sha256-xg8LdNiTF+ZM/GI/v92CjxtbLlCqdQIKxAARAzgYU70=";
          };
      };
    };
  };
}
