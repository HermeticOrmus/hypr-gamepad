# Troubleshooting

Three commands answer most questions. None of them presses anything:

```bash
hypr-gamepad status                      # the pad it found, how it reads it, lights, mic, Hyprland
hypr-gamepad check                       # your config, then every action built in your Hyprland
journalctl --user -u hypr-gamepad -e     # what the service said
```

Each section below starts with what you see.

## "waiting for the pad" in the log, or `pad: not connected`

No gamepad is in reach.

1. Turn the pad on and connect it (Bluetooth paired, or the cable in).
2. If `status` still says `not connected`, check that you are in group `input`: `id -nG`. If not, run `sudo usermod -aG input "$USER"`, then log out and in.
3. If the pad is connected and still not found, it may not report itself as a gamepad (some USB pads and adapters). Name it in the config, `[device] name = "part of its name"`, then run `hypr-gamepad learn`.

## "Another program holds the pad"

Something else grabbed the pad, often Steam or a game that reads it directly. Close that program, and the pad comes back within a second. To give the pad to a game on purpose, use game mode: home + start (PS + Options on a DualSense).

## The pad works, but the right stick does not scroll

The log says `no scroll: the virtual wheel could not be made`. Smooth scrolling is a virtual mouse wheel made through `/dev/uinput`, which your user may not open. Install the udev rule (it opens `/dev/uinput` to group `input`):

```bash
sudo install -m 0644 udev/60-hypr-gamepad.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger --name-match=uinput
systemctl --user restart hypr-gamepad
```

## No lightbar or player lights, or the mic button does nothing (DualSense)

`status` says `lights: not writable (install the udev rule)` or `mic button: ... not readable (install the udev rule)`. Install the udev rule as above, then turn the pad off and on. On any pad other than a DualSense, `none on this pad` is expected: only a DualSense has those.

## `FAIL hyprland: it reads a hyprland.conf`

hypr-gamepad sends its actions to Hyprland as Lua, which needs a Lua config: `~/.config/hypr/hyprland.lua`, Hyprland 0.56 or newer (current Omarchy has one). A setup with only `hyprland.conf` does not work yet.

## `FAIL hyprland: does not answer`

Run the command inside your Hyprland session. Over a plain `ssh`, or from a service started outside the session, Hyprland's socket is not in reach.

## Holding the start button shows no map

1. Check the plugin: `omarchy plugin list` should show `ormus.hypr-gamepad-map` as enabled.
2. If it is not, run `./install.sh --enable`, or `omarchy plugin enable ormus.hypr-gamepad-map && omarchy restart shell`.
3. Check that `hypr-gamepad map --json` prints a map: the plugin runs that command and draws its rows.

The map needs the Omarchy shell; the pad works without it.

## Buttons come out swapped, or a D-pad, a trigger or a stick does nothing

Look at the `read as` line of `hypr-gamepad status`: it says the family, where the right stick and the triggers come from, and the D-pad. If the pad sends other codes than Linux's gamepad standard:

```bash
systemctl --user stop hypr-gamepad   # learn needs the pad to itself
hypr-gamepad learn                   # press what it asks, paste what it prints into your config
systemctl --user start hypr-gamepad
```

On a Nintendo pad, B (the bottom button) is Enter and A is Esc, by place. To swap them, put `south = "escape"` and `east = "enter"` in `[layout.base]`.

## R2 does not type what I say

- `Talk is not set up`: `[talk] backend` is `none`. Set it to `voice-flow`, or to `command` with your dictation tool's start and stop commands.
- `Talk: voice-flow did not start`: the command is not on the service's PATH. Install [voice-flow](https://github.com/HermeticOrmus/voice-flow), or give `[talk] toggle` the full path.

## A herdr control does nothing

The key reached the window, and something before herdr took it, or herdr binds another key. [herdr.md](herdr.md) has herdr's defaults and how to match `[herdr.keys]` to your herdr.

## Still stuck

Run `hypr-gamepad run --dry` with the service stopped: each press prints what it would do. Then [open a bug report](https://github.com/HermeticOrmus/hypr-gamepad/issues/new?template=bug_report.yml) with that output, `status`, and `check`.
