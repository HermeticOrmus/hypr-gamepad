# Setups

A setup is one folder: the `config.toml` someone runs, and a `README.md` that says what it is for.

- Controller: the pad, and how it is connected (Bluetooth, USB, a dongle).
- Read as: the line `hypr-gamepad status` prints for it, and any `[buttons]` or `[axes]` lines `hypr-gamepad learn` gave.
- Desktop: the Hyprland setup around it (Omarchy, a plain Hyprland, a TV from the couch).
- Tools: what `[talk]`, `[jump]`, `[board]` and `[ideas]` call, and where to get them.

To use one, copy its `config.toml` to `~/.config/hypr-gamepad/config.toml` and drop the sections for tools you do not have. `hypr-gamepad check` says if anything in it does not fit your desk.

To add yours, open a ["Share your setup" issue](https://github.com/HermeticOrmus/hypr-gamepad/issues/new?template=share-setup.yml), or a pull request with a new folder here. Leave out anything private: host names, paths to your own tools, people's names.

| Setup | Controller | Desktop |
|---|---|---|
| [hermeticormus-dualsense](hermeticormus-dualsense/) | DualSense, Bluetooth | Omarchy, herdr with Alt chords, voice-flow |
