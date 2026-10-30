"""The config file: what the pad talks to (talk, the jump, the board, the wheel, ideas), which windows
are herdr's, herdr's keys and the layout come from config.toml. No file gives a friend's defaults:
herdr 0.9.5's own keys, voice-flow for talk, and nothing of any one desk.

Hyprland is a stub here, never the real one; `check` is run only with a config it refuses, so it stops
before it asks Hyprland anything.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "hypr-gamepad"

# A copy of its own, so swapping CONFIG here never reaches test_hypr_gamepad's copy.
loader = importlib.machinery.SourceFileLoader("hypr_gamepad_config", str(SCRIPT))
hg = importlib.util.module_from_spec(importlib.util.spec_from_loader("hypr_gamepad_config", loader))
sys.modules["hypr_gamepad_config"] = hg  # dataclasses look their module up while the file loads
loader.exec_module(hg)

HERDR = {"address": "0xa1", "class": "org.omarchy.herdr", "title": "desktop: MAIN", "pid": 0, "grouped": []}
BROWSER = {"address": "0xa2", "class": "chromium", "title": "Docs - Chromium", "pid": 0, "grouped": []}
MONITORS = [{"name": "DP-1", "x": 0, "y": 0, "width": 1920, "height": 1080, "scale": 1.0, "transform": 0,
             "focused": True}]


def shortcut(mods: str, key: str, address: str) -> str:
    return f'hl.dsp.send_shortcut({{ mods = "{mods}", key = "{key}", window = "address:{address}" }})'


class Hypr:
    def __init__(self):
        self.sent: list[str] = []
        self.active: dict | None = None
        self.monitors: list | None = MONITORS

    def dispatch(self, expr):
        self.sent.append(expr)
        return True

    def eval(self, lua):
        self.sent.append(lua)
        return True

    def json(self, what):
        return {"activewindow": self.active, "monitors": self.monitors}.get(what)


class Fx(hg.Fx):
    def __init__(self):
        self.rumbles: list[str] = []
        self.notes: list[str] = []

    def rumble(self, pattern):
        self.rumbles.append(pattern)

    def notify(self, title, body=""):
        self.notes.append(f"{title}: {body}" if body else title)


class Proc:
    def __init__(self):
        self.code = None

    def poll(self):
        return self.code


class Runner:
    """Records what would start; nothing starts."""

    def __init__(self):
        self.calls: list[list[str]] = []
        self.procs: list[Proc] = []

    def spawn(self, argv):
        self.calls.append(list(argv))
        self.procs.append(Proc())
        return self.procs[-1]

    def capture(self, argv, out):
        proc = self.spawn(argv)
        proc.out = out
        return proc

    def reap(self):
        pass


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class ConfigCase(unittest.TestCase):
    """Each test sets the config it runs with (`use`), and the one before comes back after it."""

    def setUp(self):
        saved = hg.CONFIG
        self.addCleanup(setattr, hg, "CONFIG", saved)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def write(self, toml: str) -> Path:
        path = self.tmp / "config.toml"
        path.write_text(toml)
        return path

    def use(self, toml: str | None = None) -> None:
        """This config (no text: no file at all), and a fresh pad that runs with it."""
        if toml is None:
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.tmp / "empty")}):
                hg.CONFIG = hg.load_config(None)
        else:
            hg.CONFIG = hg.load_config(self.write(toml))
        self.hypr, self.fx, self.clock, self.runner = Hypr(), Fx(), Clock(), Runner()
        procs = self.tmp / "proc"
        procs.mkdir(exist_ok=True)
        self.pad = hg.Pad(self.hypr, self.fx, self.clock, windows=hg.Windows(self.hypr, str(procs)),
                          runner=self.runner, voice=self.tmp)

    def tap(self, control: str, seconds: float = 0.05) -> None:
        self.pad.press(control)
        self.clock.now += seconds
        self.pad.release(control)

    def hold(self, control: str, seconds: float) -> None:
        self.pad.press(control)
        for _ in range(int(seconds / 0.01)):
            self.clock.now += 0.01
            self.pad.tick()

    def sent(self) -> list[str]:
        out, self.hypr.sent = self.hypr.sent, []
        return out

    def rows(self, layer: str = "base") -> dict[str, dict]:
        return {r["control"]: r for r in hg.map_rows(layer)}


class Defaults(ConfigCase):
    def test_no_file_is_the_defaults(self):
        self.use()
        self.assertEqual(hg.CONFIG, hg.Config())
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/xdg"}):
            self.assertEqual(hg.default_config_path(), Path("/xdg/hypr-gamepad/config.toml"))
        with mock.patch.dict(os.environ, {"HOME": "/home/friend"}):
            os.environ.pop("XDG_CONFIG_HOME", None)
            self.assertEqual(hg.default_config_path(), Path("/home/friend/.config/hypr-gamepad/config.toml"))

    def test_herdr_gets_its_own_095_keys(self):
        """herdr 0.9.5's defaults: prefix Ctrl+B, then p / n tabs, k / j / h / l panes, z zoom."""
        self.use()
        self.hypr.active = HERDR
        for control, key in (("l1", "p"), ("r1", "n"), ("ls_up", "k"), ("ls_down", "j"),
                             ("ls_left", "h"), ("ls_right", "l")):
            self.tap(control)
            self.assertEqual(self.sent(), [shortcut("CTRL", "b", "0xa1"), shortcut("", key, "0xa1")], control)
        win = self.pad.windows.active()
        self.assertEqual(hg.ACTIONS["zoom"].run.step_for(win), (hg.Key("CTRL", "b"), hg.Key("", "z")))

    def test_triangle_sends_prefix_o_in_a_herdr_window(self):
        """prefix+o: herdr's latest notification, the agent that called last."""
        self.use()
        self.hypr.active = HERDR
        self.tap("north")
        self.assertEqual(self.sent(), [shortcut("CTRL", "b", "0xa1"), shortcut("", "o", "0xa1")])
        self.assertEqual(self.runner.calls, [])

    def test_triangle_outside_herdr_says_where_it_works(self):
        self.use()
        self.hypr.active = BROWSER
        self.tap("north")
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.fx.notes, ["Triangle jumps inside herdr"])

    def test_talk_is_voice_flow(self):
        self.use()
        self.assertIsInstance(self.pad.talk, hg.Talk)
        self.pad.press("r2")
        self.assertEqual(self.runner.calls, [["voice-flow"]])

    def test_board_wheel_and_ideas_are_off_and_say_so(self):
        self.use()
        self.tap("home")                             # no board
        self.hold("home", 0.6)                       # no wheel
        self.pad.release("home")
        self.assertEqual(self.sent(), [])
        self.tap("select")
        self.tap("select")
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.fx.notes, ["Create is not set up: see [ideas] in the config"])  # once
        for layer in ("base", "world"):
            self.assertNotIn("home", self.rows(layer))
            self.assertNotIn("select", self.rows(layer))

    def test_talk_none_says_so_once(self):
        self.use('[talk]\nbackend = "none"\n')
        self.tap("r2", 1.0)
        self.tap("r2")
        self.pad.button("mic", True)
        self.pad.button("mic", False)
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.fx.notes, ["Talk is not set up: see [talk] in the config"])
        self.assertNotIn("r2", self.rows())
        self.assertNotIn("mic", self.rows())

    def test_no_desk_of_its_own_is_built_in(self):
        self.use()
        self.assertEqual(hg.classify("chrome-127.0.0.1__-Default", "Sun board", False), "other")
        self.assertEqual(hg.classify("org.ormus.workboard.desk", "server: DESK", False), "other")
        text = SCRIPT.read_text()
        for name in ("sun-wheel", "voice-ideas-toggle", "org.ormus.workboard.", "Sun board",
                     "ormus.sessions-wheel", "7741", "herdr-theme"):
            self.assertNotIn(name, text)


class HerdrKeys(ConfigCase):
    def test_herdr_keys_become_hyprland_chords(self):
        chords = hg.herdr_chords
        self.assertEqual(chords("ctrl+alt+]", "ctrl+b"), (hg.Key("CTRL ALT", "bracketright"),))
        self.assertEqual(chords("alt+left", "ctrl+b"), (hg.Key("ALT", "Left"),))
        self.assertEqual(chords("prefix+n", "ctrl+b"), (hg.Key("CTRL", "b"), hg.Key("", "n")))
        self.assertEqual(chords("prefix+shift+p", "ctrl+space"), (hg.Key("CTRL", "space"), hg.Key("SHIFT", "p")))
        self.assertEqual(chords("alt+shift+up", ""), (hg.Key("ALT SHIFT", "Up"),))
        for key, sym in (("enter", "Return"), ("esc", "Escape"), ("tab", "Tab"), ("minus", "minus"),
                         ("-", "minus"), ("[", "bracketleft"), ("space", "space"), ("f5", "F5")):
            self.assertEqual(chords(f"ctrl+{key}", ""), (hg.Key("CTRL", sym),), key)
        self.assertEqual(chords("", "ctrl+b"), ())

    def test_a_bad_key_is_an_error_naming_it(self):
        for toml, where in (('[herdr.keys]\ntab_next = "ctrl+wobble"\n', "herdr.keys.tab_next"),
                            ('[herdr.keys]\nzoom = "ctrl+"\n', "herdr.keys.zoom"),
                            ('[herdr]\nprefix = "prefix+b"\n', "herdr.prefix"),
                            ('[herdr]\nprefix = ""\n', "herdr.keys.tab_prev")):  # prefix+p with no prefix
            with self.assertRaises(hg.ConfigError) as caught:
                hg.load_config(self.write(toml))
            self.assertIn(where, str(caught.exception))

    def test_an_empty_key_does_nothing_in_herdr(self):
        self.use('[herdr.keys]\ntab_next = ""\n')
        self.hypr.active = HERDR
        self.tap("r1")
        self.assertEqual(self.sent(), [])
        self.assertNotIn("herdr", self.rows()["r1"]["kinds"])
        self.assertIn("herdr", self.rows()["l1"]["kinds"])

    def test_the_setup_keys_and_labels(self):
        self.use((ROOT / "setups/hermeticormus-dualsense/config.toml").read_text())
        self.hypr.active = HERDR
        self.tap("ls_down")
        self.assertEqual(self.sent(), [shortcut("ALT SHIFT", "Down", "0xa1")])
        win = self.pad.windows.active()
        self.assertEqual(hg.ACTIONS["zoom"].run.step_for(win), (hg.Key("CTRL", "space"), hg.Key("", "z")))
        self.assertEqual(self.rows()["ls_left"]["labels"]["herdr"], "Previous herdr space")


class Problems(ConfigCase):
    def test_unknown_keys_warn_one_line_each(self):
        path = self.write('[talk]\nbackend = "voice-flow"\nvolume = 3\n\n[sparkles]\nx = 1\n')
        with self.assertLogs(hg.log, "WARNING") as logs:
            config = hg.load_config(path)
        self.assertEqual(config, hg.Config())
        self.assertEqual(len(logs.output), 2)
        self.assertIn("talk.volume", logs.output[0])
        self.assertIn("sparkles", logs.output[1])

    def test_a_wrong_type_is_an_error_naming_the_key(self):
        for toml, where in (('[talk]\ntoggle = "voice-flow"\n', "talk.toggle"),
                            ('[herdr.keys]\ntab_prev = 3\n', "herdr.keys.tab_prev"),
                            ('[board]\nlabel = ["Tap"]\n', "board.label"),
                            ('[windows]\nterminals = ["foot", 3]\n', "windows.terminals"),
                            ('talk = 1\n', "talk"),
                            ('[talk]\nbackend = "shout"\n', "talk.backend"),
                            ('[jump]\nbackend = "command"\n', "jump.items"),
                            ('[wheel]\nplugin = \'my"wheel\'\n', "wheel.plugin")):
            with self.assertRaises(hg.ConfigError) as caught:
                hg.load_config(self.write(toml))
            self.assertIn(where, str(caught.exception), toml)

    def test_an_unknown_action_or_control_in_a_layout_is_an_error(self):
        for toml, words in (('[layout.base]\ncross = "fly"\n', ("layout.base.cross", "fly")),
                            ('[layout.world]\nwing = "enter"\n', ("layout.world.wing",)),
                            ('[layout.base]\nl2 = "enter"\n', ("layout.base.l2",)),
                            ('[layout.base]\nrs_up = "enter"\n', ("layout.base.rs_up",))):  # it scrolls there
            with self.assertRaises(hg.ConfigError) as caught:
                hg.load_config(self.write(toml))
            for word in words:
                self.assertIn(word, str(caught.exception))

    def test_toml_that_does_not_parse_is_an_error_naming_the_file(self):
        path = self.write("[talk\n")
        with self.assertRaises(hg.ConfigError) as caught:
            hg.load_config(path)
        self.assertIn(str(path), str(caught.exception))

    def test_a_file_named_on_the_command_line_must_be_there(self):
        with self.assertRaises(hg.ConfigError):
            hg.load_config(self.tmp / "nothing.toml")

    def test_check_reports_a_config_problem(self):
        path = self.write('[layout.base]\ncross = "fly"\n')
        proc = subprocess.run([sys.executable, str(SCRIPT), "check", "--config", str(path)],
                              capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FAIL config", proc.stdout)
        self.assertIn("layout.base.cross", proc.stdout)

    def test_run_refuses_a_bad_config(self):
        path = self.write('[talk]\ntoggle = "voice-flow"\n')
        proc = subprocess.run([sys.executable, str(SCRIPT), "run", "--dry", "--config", str(path)],
                              capture_output=True, text=True, timeout=10)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("talk.toggle", proc.stderr)


class Layout(ConfigCase):
    def test_the_layout_changes_single_controls(self):
        self.use('[layout.base]\ntriangle = "zoom"\nsquare = ""\n\n[layout.world]\ncross = "scratchpad"\n')
        self.assertEqual(hg.layout("base")["north"], "zoom")
        self.assertNotIn("west", hg.layout("base"))
        self.assertEqual(hg.layout("base")["south"], "enter")      # the rest stay as they were
        self.hypr.active = HERDR
        self.tap("north")
        self.assertEqual(self.sent(), [shortcut("CTRL", "b", "0xa1"), shortcut("", "z", "0xa1")])
        self.tap("west")
        self.assertEqual(self.sent(), [])
        self.pad.press("l2")
        self.tap("south")
        self.assertEqual(self.sent(), ['hl.dsp.workspace.toggle_special("scratchpad")'])
        self.assertEqual(self.rows()["north"]["labels"]["herdr"], "Zoom the herdr pane")
        self.assertNotIn("west", self.rows())


class PlaceNames(ConfigCase):
    """Controls are named by where they sit on the pad (the kernel's gamepad spec), so one config
    reads the same for any controller; the PlayStation names still work in a config file."""

    def test_controls_are_named_by_place(self):
        self.use()
        base = hg.layout("base")
        self.assertEqual([base[c] for c in ("south", "east", "west", "north")],
                         ["enter", "escape", "take_back", "jump"])
        self.assertEqual([base[c] for c in ("select", "start", "home")], ["ideas", "map", "board"])
        for gone in ("cross", "circle", "square", "triangle", "create", "options", "ps"):
            self.assertNotIn(gone, hg.CONTROL_NAMES)
        self.assertEqual([r["control"] for r in hg.map_rows("base")][:4], ["south", "east", "west", "north"])

    def test_the_map_still_shows_the_dualsense_names(self):
        self.use('[board]\ncommand = ["board"]\n\n[ideas]\ncommand = ["ideas"]\n')
        rows = self.rows()
        self.assertEqual([(rows[c]["glyph"], rows[c]["name"]) for c in ("south", "east", "west", "north")],
                         [("✕", "Cross"), ("○", "Circle"), ("□", "Square"), ("△", "Triangle")])
        self.assertEqual([rows[c]["name"] for c in ("select", "start", "home")], ["Create", "Options", "PS"])

    def test_playstation_names_work_in_a_config(self):
        self.use('[layout.base]\ntriangle = "zoom"\nsquare = ""\n\n[layout.world]\nps = "scratchpad"\n')
        self.assertEqual(hg.layout("base")["north"], "zoom")
        self.assertNotIn("west", hg.layout("base"))
        self.assertEqual(hg.layout("world")["home"], "scratchpad")
        self.assertEqual(hg.layout("base")["south"], "enter")

    def test_place_names_work_in_a_config(self):
        self.use('[layout.base]\nnorth = "zoom"\nwest = ""\n')
        self.assertEqual(hg.layout("base")["north"], "zoom")
        self.assertNotIn("west", hg.layout("base"))

    def test_one_control_named_twice_is_an_error(self):
        with self.assertRaises(hg.ConfigError) as caught:
            hg.load_config(self.write('[layout.base]\ntriangle = "zoom"\nnorth = "map"\n'))
        self.assertIn("layout.base", str(caught.exception))
        self.assertIn("triangle", str(caught.exception))
        self.assertIn("north", str(caught.exception))


COMMAND_TALK = """
[talk]
backend = "command"
start = ["dictate", "start"]
stop = ["dictate", "stop"]
cancel = ["dictate", "cancel"]
"""
START, STOP, CANCEL = ["dictate", "start"], ["dictate", "stop"], ["dictate", "cancel"]


class CommandTalk(ConfigCase):
    """A dictation tool driven by plain commands: start when a talk starts, stop when it ends (the tool
    types the words), cancel when Circle drops it."""

    def setUp(self):
        super().setUp()
        self.use(COMMAND_TALK)

    def test_hold_talks_and_letting_go_ends_it(self):
        self.assertIsInstance(self.pad.talk, hg.CommandTalk)
        self.pad.press("r2")
        self.assertEqual(self.runner.calls, [START])
        self.assertEqual(self.pad.light_state(), "talk")
        self.clock.now += 1.0
        self.pad.release("r2")
        self.assertEqual(self.runner.calls, [START, STOP])
        self.assertFalse(self.pad.talk.active())
        self.assertEqual(self.pad.light_state(), "desk")

    def test_a_tap_keeps_listening_until_the_next_press(self):
        self.tap("r2", 0.1)
        self.assertEqual(self.runner.calls, [START])
        self.assertTrue(self.pad.talk.active())
        self.clock.now += 5.0
        self.tap("r2", 0.1)
        self.assertEqual(self.runner.calls, [START, STOP])
        self.assertFalse(self.pad.talk.active())

    def test_circle_drops_it_and_is_not_esc(self):
        self.hypr.active = HERDR
        self.pad.press("r2")
        self.clock.now += 1.0
        self.tap("east")
        self.pad.release("r2")
        self.assertEqual(self.runner.calls, [START, CANCEL])
        self.assertEqual(self.sent(), [])
        self.assertFalse(self.pad.talk.active())

    def test_the_button_that_is_esc_drops_it_after_a_swap(self):
        """A Nintendo pad's swap (B, south, is Esc; A, east, is Enter): the Esc button drops a talk, and
        the Enter button is Enter, in either layer."""
        self.use(COMMAND_TALK + '\n[layout.base]\nsouth = "escape"\neast = "enter"\n')
        self.hypr.active = HERDR
        self.pad.press("r2")
        self.clock.now += 1.0
        self.tap("east")                                             # Enter: the talk goes on
        self.assertEqual(self.sent(), [shortcut("", "Return", "0xa1")])
        self.assertTrue(self.pad.talk.active())
        self.pad.press("l2")
        self.tap("south")                                            # Esc, on the desktop side too
        self.pad.release("l2")
        self.pad.release("r2")
        self.assertEqual(self.runner.calls, [START, CANCEL])
        self.assertEqual(self.sent(), [])
        self.assertFalse(self.pad.talk.active())

    def test_the_mic_button_starts_and_the_next_press_ends(self):
        self.pad.button("mic", True)
        self.pad.button("mic", False)
        self.clock.now += 3.0
        self.pad.button("mic", True)
        self.pad.button("mic", False)
        self.assertEqual(self.runner.calls, [START, STOP])

    def test_the_pad_going_away_drops_it(self):
        self.pad.press("r2")
        self.pad.reset()
        self.assertEqual(self.runner.calls, [START, CANCEL])
        self.assertFalse(self.pad.talk.active())

    def test_command_needs_a_start(self):
        with self.assertRaises(hg.ConfigError) as caught:
            hg.load_config(self.write('[talk]\nbackend = "command"\nstop = ["x"]\n'))
        self.assertIn("talk.start", str(caught.exception))


class Integrations(ConfigCase):
    def test_the_board_command_is_quoted_for_the_shell_inside_lua(self):
        self.use('[board]\ncommand = ["open-board", "it\'s here", "a]]b"]\n')
        self.tap("home")
        self.assertEqual(self.sent(), ["hl.dsp.exec_cmd([=[open-board 'it'\"'\"'s here' 'a]]b']=])"])
        self.assertEqual(self.rows()["home"]["label"], "Tap: the board")

    def test_the_jump_command_gets_the_key_appended_or_where_key_stands(self):
        for go, want in (('["agents", "show"]', ["agents", "show", "k1"]),
                         ('["agents", "show", "{key}", "--quiet"]', ["agents", "show", "k1", "--quiet"])):
            self.use(f'[jump]\nbackend = "command"\nitems = ["agents", "list"]\ngo = {go}\n')
            self.tap("north")
            self.assertEqual(self.runner.calls, [["agents", "list"]])
            proc = self.runner.procs[-1]
            Path(proc.out).write_text(json.dumps({"items": [{"key": "k1", "name": "one"}]}))
            proc.code = 0
            self.pad.tick()
            self.assertEqual(self.runner.calls[-1], want)

    def test_the_wheel_plugin_names_its_events(self):
        self.use('[wheel]\nplugin = "my.wheel"\n')
        self.hold("home", 0.5)
        self.assertTrue(self.sent()[0].startswith('hl.dsp.event("my.wheel padhold pad'))
        self.pad.release("home")
        self.assertTrue(self.sent()[-1].startswith('hl.dsp.event("my.wheel release pad'))
        self.assertEqual(self.rows()["home"]["label"], "Hold: the sessions wheel (right stick aims, let go jumps)")

    def test_windows_lists_add_to_the_built_in_ones(self):
        self.use('[windows]\nherdr_classes = ["my.herdr"]\nherdr_class_prefixes = ["my.remote."]\n'
                 'herdr_programs = ["herdr-wrap"]\nboard_titles = ["Ops board"]\n'
                 'terminals = ["my-term"]\nbrowsers = ["my-browser"]\n')
        cases = [("my.herdr", "x", "herdr"), ("my.remote.desk", "x", "herdr"), ("org.omarchy.herdr", "x", "herdr"),
                 ("anything", "Ops board", "board"), ("my-browser", "x", "browser"), ("chromium", "x", "browser"),
                 ("my-term", "user@host: ~", "terminal"), ("my-term", "desktop: MAIN", "herdr"),
                 ("foot", "user@host: ~", "terminal")]
        for cls, title, kind in cases:
            self.assertEqual(hg.classify(cls, title, False), kind, (cls, title))
        proc = self.tmp / "proc"
        for pid, argv, kids in ((10, ["my-term"], [11]), (11, ["herdr-wrap", "attach"], [])):
            task = proc / str(pid) / "task" / str(pid)
            task.mkdir(parents=True)
            (task / "children").write_text(" ".join(map(str, kids)))
            (proc / str(pid) / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
        self.assertTrue(hg.runs_herdr(10, str(proc)))
        self.hypr.active = {"address": "0xa3", "class": "my-term", "title": "user@host: ~", "pid": 10, "grouped": []}
        self.assertEqual(self.pad.windows.active().kind, "herdr")


class MapCommand(ConfigCase):
    def run_map(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "map", *args], capture_output=True, text=True,
                              timeout=10, env=env)

    def test_map_json_labels_follow_the_config(self):
        path = self.write('[herdr.labels]\nagent_prev = "Up one pane"\n\n'
                          '[board]\ncommand = ["open-board"]\nlabel = "Tap: the ops board"\n\n'
                          '[wheel]\nplugin = "my.wheel"\n')
        proc = self.run_map("--json", "--config", str(path))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = {r["control"]: r for r in json.loads(proc.stdout)["layers"]["base"]}
        self.assertEqual(rows["ls_up"]["labels"]["herdr"], "Up one pane")
        self.assertEqual(rows["ls_down"]["labels"]["herdr"], "Pane below")
        self.assertEqual(rows["home"]["label"],
                         "Tap: the ops board. Hold: the sessions wheel (right stick aims, let go jumps)")
        self.assertEqual(rows["north"]["kinds"], ["herdr"])

    def test_map_works_without_a_config(self):
        env = dict(os.environ, XDG_CONFIG_HOME=str(self.tmp / "empty"))
        proc = self.run_map("--json", env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = {r["control"]: r for r in json.loads(proc.stdout)["layers"]["base"]}
        self.assertEqual([rows[c]["labels"]["herdr"] for c in ("ls_up", "ls_down", "ls_left", "ls_right", "l1", "r1")],
                         ["Pane above", "Pane below", "Pane to the left", "Pane to the right",
                          "Previous herdr tab", "Next herdr tab"])
        self.assertNotIn("home", rows)
        text = self.run_map(env=env)
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertIn("Inside the window", text.stdout)
        self.assertEqual(text.stderr, "")

    def test_an_unknown_key_warns_on_stderr_and_the_map_still_shows(self):
        path = self.write('[talk]\nvolume = 3\n')
        proc = self.run_map("--config", str(path))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(proc.stderr.splitlines()), 1)
        self.assertIn("talk.volume", proc.stderr)


class Example(unittest.TestCase):
    def test_the_example_is_the_defaults(self):
        """config.example.toml lists every key with its default, commented out: uncommented, it is
        the defaults, so the example never drifts from the code."""
        lines = (ROOT / "config.example.toml").read_text().splitlines()
        setting = re.compile(r"# (\[[a-z.]+\]|[a-z_]+ = )")   # "# [talk]", "# backend = ...": the rest is prose
        toml = "\n".join(line[2:] if setting.match(line) else "" for line in lines)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "config.toml")
            path.write_text(toml)
            with self.assertNoLogs(hg.log, "WARNING"):
                self.assertEqual(hg.load_config(path), hg.Config())
        text = (ROOT / "config.example.toml").read_text()
        for name in hg.ACTIONS:
            self.assertRegex(text, rf"(?<![a-z_]){name}(?![a-z_])", "the example's list of actions")
        for control in hg.bindable("world"):
            self.assertRegex(text, rf"(?<![a-z_]){control}(?![a-z_])", "the example's list of controls")

    def test_the_herdr_page_configs_load_as_they_are(self):
        """docs/herdr.md's hypr-gamepad blocks are configs a person pastes: each must load with no warning,
        and send the keys the herdr block beside it binds."""
        text = (ROOT / "docs/herdr.md").read_text()
        blocks = re.findall(r"```toml\n(.*?)```", text, re.S)
        pad = [b for b in blocks if b.startswith("# ~/.config/hypr-gamepad/")]
        herdr = [b for b in blocks if b.startswith("# ~/.config/herdr/")]
        self.assertEqual((len(pad), len(herdr)), (2, 2))
        for block, keys in zip(pad, herdr):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp, "config.toml")
                path.write_text(block)
                with self.assertNoLogs(hg.log, "WARNING"):
                    config = hg.load_config(path)
            for field in hg.fields(hg.HerdrKeys):
                sent = getattr(config.herdr.keys, field.name)
                if sent != getattr(hg.HerdrKeys(), field.name):
                    self.assertIn(f'"{sent}"', keys, field.name)        # herdr's side binds what the pad sends


if __name__ == "__main__":
    unittest.main()
