# Changelog

## Unreleased

- The mic button is read only on a DualSense, the lights are the LED files the pad has, and the battery is the pad's own power supply (any HID driver), ready for other pads.
- Controls are named by where they sit (south, east, west, north; select, start, home), so a config reads the same for any controller. The DualSense names (cross, circle, square, triangle, create, options, ps) still work in a config; `map --json` lists the place names.

## 0.1.0: first public version

- A PS5 DualSense drives Hyprland 0.56+ (Lua config): windows, workspaces, screens, herdr, dictation, an on-screen map, game mode, lightbar.
- A config file (`~/.config/hypr-gamepad/config.toml`) sets the integrations, herdr's keys and the layout; `setups/` holds shared setups.
- MIT license, issue forms for bugs, feedback and "Share your setup".
