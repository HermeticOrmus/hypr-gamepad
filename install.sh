#!/usr/bin/env bash
# hypr-gamepad's installer, for the user who runs it: no sudo, nothing outside your home.
#
#   ./install.sh              the program, the user service, a config (only if you have none) and, with
#                             the Omarchy shell, the on-screen map; then what to run next
#   ./install.sh --enable     the same, then start the service (and the map) now and at each login
#   ./install.sh --uninstall  stop the service and take out what install put in; your config stays
#
# Root's part, the udev rule (lights, the mic button, the scroll wheel), is printed, never run.
set -euo pipefail
IFS=$'\n\t'

usage() {
    echo "usage: ./install.sh [--enable | --uninstall]" >&2
    exit 2
}

mode=install
enable=0
for arg in "$@"; do
    case "$arg" in
        --enable) enable=1 ;;
        --uninstall) mode=uninstall ;;
        -h | --help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) usage ;;
    esac
done

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
bin="$HOME/.local/bin/hypr-gamepad"
unit="$config_home/systemd/user/hypr-gamepad.service"
config="$config_home/hypr-gamepad/config.toml"
plugin_id="ormus.hypr-gamepad-map"
plugins="$config_home/omarchy/plugins"
rules_dir="${HYPR_GAMEPAD_UDEV_RULES:-/etc/udev/rules.d}"   # the tests point it elsewhere
rule="$rules_dir/60-hypr-gamepad.rules"

say() { printf '%s\n' "$*"; }

if [[ "$mode" == uninstall ]]; then
    if [[ -f "$unit" ]]; then
        systemctl --user disable --now hypr-gamepad.service || true
        rm -f "$unit"
        systemctl --user daemon-reload || true
    fi
    rm -f "$bin"
    if [[ -d "$plugins/$plugin_id" ]]; then
        if command -v omarchy >/dev/null; then
            omarchy plugin disable "$plugin_id" || true
        fi
        rm -rf "${plugins:?}/$plugin_id"
        if command -v omarchy >/dev/null; then
            omarchy restart shell || true
        fi
    fi
    say "hypr-gamepad is out. Your config stays: $config"
    if [[ -f "$rule" ]]; then
        say "The udev rule is root's: sudo rm $rule"
    fi
    exit 0
fi

install -Dm755 "$repo/hypr-gamepad" "$bin"
install -Dm644 "$repo/systemd/hypr-gamepad.service" "$unit"
say "installed $bin"
say "installed $unit"
if [[ -e "$config" ]]; then
    say "kept your config: $config"
else
    install -Dm644 "$repo/config.example.toml" "$config"
    say "installed $config (every key commented out: the defaults)"
fi

map=0
if command -v omarchy >/dev/null; then
    rm -rf "${plugins:?}/$plugin_id"
    mkdir -p "$plugins"
    cp -r "$repo/omarchy/$plugin_id" "$plugins/"
    say "installed the on-screen map: $plugins/$plugin_id"
    map=1
else
    say "no Omarchy shell (no omarchy command): the on-screen map is skipped; the pad works without it"
fi

# What only the person can fix, each in one line.
need=()
python3 - <<'PY' || need+=("python 3.11 or newer")
import sys
sys.exit(0 if sys.version_info >= (3, 11) else 1)
PY
if ! python3 -c 'import evdev' 2>/dev/null; then
    need+=("python-evdev: python-evdev on Arch, python3-evdev on Debian, Ubuntu and Fedora")
fi
if ! id -nG | tr ' ' '\n' | grep -qx input; then
    need+=("your user in group input, to read the pad: sudo usermod -aG input \"\$USER\", then log out and in")
fi
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) need+=("$HOME/.local/bin on your PATH") ;;
esac
if (( ${#need[@]} > 0 )); then
    say ""
    say "Still needed:"
    for item in "${need[@]}"; do
        say "  - $item"
    done
fi

if ! cmp -s "$repo/udev/60-hypr-gamepad.rules" "$rule"; then
    say ""
    say "Root's part, once: the lightbar, the player lights and the mic button of a DualSense, and the"
    say "smooth-scroll wheel (/dev/uinput) for group input. The pad works without it."
    say "  sudo install -m 0644 \"$repo/udev/60-hypr-gamepad.rules\" $rules_dir/"
    say "  sudo udevadm control --reload-rules && sudo udevadm trigger --name-match=uinput"
    say "  then turn the pad off and on"
fi

if (( enable == 1 )); then
    systemctl --user daemon-reload
    systemctl --user enable --now hypr-gamepad.service
    say ""
    say "hypr-gamepad runs, and starts at each login. Its log: journalctl --user -u hypr-gamepad"
    if (( map == 1 )); then
        omarchy plugin enable "$plugin_id"
        omarchy restart shell
    fi
else
    say ""
    say "Next:"
    say "  hypr-gamepad check          # your config, and every action built in your Hyprland (runs none)"
    say "  hypr-gamepad status         # the pad it found and how it reads it"
    say "  hypr-gamepad run --dry      # press buttons: it prints what it would do, and does nothing"
    say "  ./install.sh --enable       # then start it for good"
fi
