<p align="center">
  <img src="https://ormus.solutions/mascot/pixellab_liquid_to_swan.gif" alt="hypr-gamepad" width="128" style="image-rendering: pixelated;" />
</p>

<h1 align="center">hypr-gamepad</h1>

<p align="center">
  <em>Drive Hyprland with a gamepad — windows, workspaces, terminal agents and voice dictation from the couch</em>
</p>

<p align="center">
  <a href="https://github.com/HermeticOrmus/hypr-gamepad/stargazers"><img src="https://img.shields.io/github/stars/HermeticOrmus/hypr-gamepad?style=flat-square&color=aa8142" alt="Stars" /></a>
  <a href="https://github.com/HermeticOrmus/hypr-gamepad/blob/main/LICENSE"><img src="https://img.shields.io/github/license/HermeticOrmus/hypr-gamepad?style=flat-square&color=aa8142" alt="License" /></a>
  <a href="https://github.com/HermeticOrmus/hypr-gamepad/commits"><img src="https://img.shields.io/github/last-commit/HermeticOrmus/hypr-gamepad?style=flat-square&color=aa8142" alt="Last Commit" /></a>
  <img src="https://img.shields.io/badge/Hyprland-aa8142?style=flat-square&logo=hyprland&logoColor=white" alt="Hyprland" />
  <img src="https://img.shields.io/badge/Gamepad-aa8142?style=flat-square&logo=playstation&logoColor=white" alt="Gamepad" />
</p>

---

> Sit back, pick up the pad: every window, workspace, screen and agent answers to it, and you talk instead of type.

hypr-gamepad is a small daemon that turns a gamepad into a desktop controller for [Hyprland](https://hyprland.org). Inside a window the buttons are Enter, Esc, arrows, tabs and scrolling. Hold L2 and the same buttons move between windows, workspaces and screens. Hold R2 and talk: [voice-flow](https://github.com/HermeticOrmus/voice-flow) types what you said. It knows [herdr](https://herdr.dev), so the sticks walk your coding agents.

Keys reach the window you pressed in through Hyprland's own `send_shortcut`: nothing is typed into the desktop through a fake keyboard, and no modifier is ever left down.

## Status

Early, and in daily use with a PS5 DualSense. Other controllers are next: the code already reads the standard Linux gamepad buttons, and the work on scaling sticks and triggers of any pad, plus a `learn` command for unknown ones, is under way. If you try another pad, [share what you saw](https://github.com/HermeticOrmus/hypr-gamepad/issues/new?template=share-setup.yml).

## What the pad does

Hold **Options** to see this on screen, for the window you are in.

| Control | Inside the window | L2 held: the desktop |
|---|---|---|
| Cross | Enter | Full screen on / off |
| Circle | Esc (with talk on: drop the take) | Back to the workspace before |
| Square | Take back the last word; hold to keep deleting (never Esc, a running agent keeps going) | Next window on this workspace |
| Triangle | Go to herdr's latest notification | Scratchpad on / off |
| D-pad | Arrow keys | Focus the window that way |
| L1 / R1 | Previous / next tab (herdr, browser, window group) | Previous / next workspace on this screen |
| Left stick | Move in herdr (panes by default, your agents and spaces with your keys); browser back / forward | Focus the screen that way |
| L3 | Shift+Tab: the agent's mode | |
| Right stick | Scroll; the further, the faster | Up / down: bigger / smaller text |
| R3 | Normal text size | Normal text size |
| R2 | Hold to talk, let go to paste; a tap keeps listening | same |
| Mic button | Talk: a press starts, the next press pastes | same |
| PS + Options | Game mode: the pad goes to your game, and back | same |

The lightbar is gold at the desk, red while you talk and blue in game mode; the player lights show which screen has focus. Every control can be changed in the config.

## Requirements

- Hyprland 0.56 or newer with a Lua config (`hyprland.lua`, as current Omarchy has). An old `hyprland.conf` setup does not work: `hypr-gamepad check` tells you.
- Python 3.11+ and python-evdev (`python-evdev` on Arch).
- A PS5 DualSense or DualSense Edge, over Bluetooth or USB.
- Optional: [voice-flow](https://github.com/HermeticOrmus/voice-flow) or any dictation tool you can start and stop from a command; [herdr](https://herdr.dev); the Omarchy shell for the on-screen map.

## Install

There is no installer yet; these are the steps it will run.

```bash
git clone https://github.com/HermeticOrmus/hypr-gamepad.git
cd hypr-gamepad
install -Dm755 hypr-gamepad ~/.local/bin/hypr-gamepad
install -Dm644 systemd/hypr-gamepad.service ~/.config/systemd/user/hypr-gamepad.service
mkdir -p ~/.config/hypr-gamepad
cp -n config.example.toml ~/.config/hypr-gamepad/config.toml
```

The lightbar, the player lights and the mic button need one udev rule and your user in group `input` (the pad works without them):

```bash
sudo install -m 0644 udev/60-hypr-gamepad.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules        # then turn the pad off and on
```

Smooth scrolling makes a virtual mouse wheel, so your user needs write access to `/dev/uinput` (group `input` on most setups).

Try it before you enable it:

```bash
hypr-gamepad check          # reads the config and builds every action in your Hyprland, running none
hypr-gamepad run --dry      # press buttons: it prints what it would do, and does nothing
systemctl --user daemon-reload
systemctl --user enable --now hypr-gamepad
```

The on-screen map, with the Omarchy shell:

```bash
cp -r omarchy/ormus.hypr-gamepad-map ~/.config/omarchy/plugins/
omarchy plugin enable ormus.hypr-gamepad-map
omarchy restart shell
```

## Config

`~/.config/hypr-gamepad/config.toml`. Every key is in [config.example.toml](config.example.toml) with its default. Set only what you change; `hypr-gamepad check` names any key it does not understand.

- `[talk]`: voice-flow, any start/stop command pair, or none.
- `[jump]`, `[board]`, `[wheel]`, `[ideas]`: what Triangle, PS and Create run.
- `[herdr]`: the keys your herdr uses (herdr's own syntax, its defaults out of the box).
- `[layout.base]`, `[layout.world]`: move any action to any control.

## Share your setup

A whole setup is one config file. [setups/](setups/) holds the ones people run, starting with the author's: a DualSense, herdr with Alt chords, voice-flow and a few tools of his own.

Show yours: [open a "Share your setup" issue](https://github.com/HermeticOrmus/hypr-gamepad/issues/new?template=share-setup.yml) with your controller, your system and your config. Different controllers are the most useful: they show what works beyond the DualSense.

## Tests

```bash
./check.sh        # Python unit tests and the map's Node tests; no real Hyprland or pad is touched
```

## Feedback

Tell us what worked and what got in your way: [open a feedback issue](https://github.com/HermeticOrmus/hypr-gamepad/issues/new?template=feedback.yml). Questions go to [Discussions](https://github.com/HermeticOrmus/hypr-gamepad/discussions).

## Contributing

Small pull requests, one change each, with a test that fails before the change. Run `./check.sh` first. Commits follow `type(scope): description`. Never prove a change by sending synthetic keys to your desktop: use `--dry`, a virtual pad, or `check`.

## License

MIT © 2026 [Diego Bodart](https://github.com/HermeticOrmus) — see [LICENSE](LICENSE). Built under the [Gold Hat principle](GOLD_HAT.md).
