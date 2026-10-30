# Changelog

## Unreleased

- Docs: the README covers any controller, `learn` and the names per family; `docs/herdr.md` has herdr's prefix-free keys and agents and workspaces on the left stick; `setups/README.md` says how to share a setup.
- `install.sh`: one command for your user (no sudo); `--enable` starts it, `--uninstall` takes it out. The udev rule also opens `/dev/uinput` to group `input`, for the scroll wheel on any desk.
- `check` says in one line when Hyprland takes no Lua (a `hyprland.conf` setup, or a Hyprland older than 0.56) or does not answer, instead of a FAIL for every action.
- `hypr-gamepad learn` asks for each control in turn and prints the `[buttons]` and `[axes]` lines the pad needs, or says it needs none. `--device` and `[device] name` may name a joystick-style pad the kernel does not call a gamepad; never a keyboard, a mouse or a touchpad.
- `[buttons]` and `[axes]` name a pad's own codes when it does not follow the kernel's gamepad spec (a plain USB pad with joystick buttons, a stick on other axes, an axis that runs the other way).
- The map and the notes name each control as the pad in the hand does: A B X Y, LB RB LT RT, View Menu Xbox on an Xbox pad; B A Y X, L R ZL ZR, Minus Plus Home on a Nintendo pad; South East West North on a plain pad. `map --pad FAMILY` shows a family's names.
- The pad is found from sysfs and is the one device opened: 7 ms instead of about 700 ms on a desk with 43 input devices, each second while the pad sleeps.
- Any gamepad: the first one the kernel calls a gamepad is the pad (`[device] name` picks another). Sticks and triggers scale from each pad's own range; triggers without buttons (Xbox) are read from their axes; the D-pad may be a hat or four buttons (older Switch Pro kernels); an Xbox pad's X and Y land west and north; game mode is home + start, or select + start on a pad without home. `status` says how it reads the pad.
- The mic button is read only on a DualSense, the lights are the LED files the pad has, and the battery is the pad's own power supply (any HID driver), ready for other pads.
- Controls are named by where they sit (south, east, west, north; select, start, home), so a config reads the same for any controller. The DualSense names (cross, circle, square, triangle, create, options, ps) still work in a config; `map --json` lists the place names.

## 0.1.0: first public version

- A PS5 DualSense drives Hyprland 0.56+ (Lua config): windows, workspaces, screens, herdr, dictation, an on-screen map, game mode, lightbar.
- A config file (`~/.config/hypr-gamepad/config.toml`) sets the integrations, herdr's keys and the layout; `setups/` holds shared setups.
- MIT license, issue forms for bugs, feedback and "Share your setup".
