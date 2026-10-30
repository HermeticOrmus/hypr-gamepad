# hypr-gamepad and herdr

In a [herdr](https://herdr.dev) window the pad sends herdr's own keys: L1 and R1 switch tabs, the left stick moves (panes by default), Triangle goes to herdr's latest notification, and Square takes back the last word. `[herdr.keys]` in `~/.config/hypr-gamepad/config.toml` says which keys those are, in herdr's own syntax.

## Out of the box

With no `[herdr]` table the pad uses herdr 0.9.5's default keys, so a fresh herdr answers:

| Control | Action | Key sent |
|---|---|---|
| L1 / R1 | `tab_prev` / `tab_next` | `prefix+p` / `prefix+n` |
| Left stick up / down | `agent_prev` / `agent_next` | `prefix+k` / `prefix+j` (the pane above / below) |
| Left stick left / right | `space_prev` / `space_next` | `prefix+h` / `prefix+l` (the pane to the left / right) |
| Triangle | `jump` | `prefix+o` (the latest notification) |
| none by default | `zoom` | `prefix+z` |

The prefix is herdr's default, `ctrl+b`. A prefix key is two keys in a row; the pad sends both.

## Prefix-free keys

herdr's keyboard guide suggests direct `ctrl+alt` chords: terminals leave them free, and they reach herdr without a prefix. Add them to herdr's config next to the prefix keys:

```toml
# ~/.config/herdr/config.toml
[keys]
focus_pane_left = ["prefix+h", "ctrl+alt+h"]
focus_pane_down = ["prefix+j", "ctrl+alt+j"]
focus_pane_up = ["prefix+k", "ctrl+alt+k"]
focus_pane_right = ["prefix+l", "ctrl+alt+l"]
previous_tab = ["prefix+p", "ctrl+alt+["]
next_tab = ["prefix+n", "ctrl+alt+]"]
zoom = ["prefix+z", "ctrl+alt+z"]
```

Then tell the pad to send them:

```toml
# ~/.config/hypr-gamepad/config.toml
[herdr.keys]
tab_prev = "ctrl+alt+["
tab_next = "ctrl+alt+]"
agent_prev = "ctrl+alt+k"
agent_next = "ctrl+alt+j"
space_prev = "ctrl+alt+h"
space_next = "ctrl+alt+l"
zoom = "ctrl+alt+z"
```

`ctrl+alt+l` locks the screen on KDE: pick another key on either side there. herdr's guide lists the `ctrl+alt` chords that terminals and desktops take.

## Agents and workspaces on the left stick

herdr has actions it leaves unbound: `previous_agent`, `next_agent`, `previous_workspace`, `next_workspace`. Bind them in herdr, and the left stick walks your agents (up / down) and your workspaces (left / right) instead of panes:

```toml
# ~/.config/herdr/config.toml
[keys]
previous_agent = "ctrl+alt+y"
next_agent = "ctrl+alt+b"
previous_workspace = ["prefix+shift+p", "ctrl+alt+w"]
next_workspace = ["prefix+shift+n", "ctrl+alt+e"]
```

```toml
# ~/.config/hypr-gamepad/config.toml
[herdr.keys]
agent_prev = "ctrl+alt+y"
agent_next = "ctrl+alt+b"
space_prev = "ctrl+alt+w"
space_next = "ctrl+alt+e"

[herdr.labels]
agent_prev = "Previous agent"
agent_next = "Next agent"
space_prev = "Previous herdr space"
space_next = "Next herdr space"
```

`[herdr.labels]` is what the on-screen map says for each one. Run `herdr config check` after a change to herdr's config, and `hypr-gamepad check` after one to the pad's: it checks every key name.

## Which windows are herdr's

A window is herdr's when its class is `org.omarchy.herdr`, when herdr runs in the terminal it shows (local, or `herdr` at the other end of an `ssh`), or when its title reads as herdr titles its window (`host: WORKSPACE`). `[windows]` adds classes, class prefixes and program names: a launcher that starts herdr under another name goes in `herdr_programs`.

## When a key does nothing

The window got the key, and something before herdr took it: the terminal or the desktop. Run `hypr-gamepad run --dry` and press the control: the line it prints is the key it sends. If that key does nothing when you type it on the keyboard either, bind another one on both sides.
