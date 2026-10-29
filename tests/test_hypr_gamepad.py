"""hypr-gamepad: the DualSense drives Hyprland. Events in, Hyprland actions out.

The events are hid-playstation's codes as the DualSense sends them (read on a test machine 2026-10-29:
event258, sticks and triggers 0-255, the D-pad as ABS_HAT0X/Y). Hyprland is a stub here, never the
real one: a test that reached the real socket would move focus on the user's screen.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "hypr-gamepad"
UNIT = ROOT / "systemd/hypr-gamepad.service"

loader = importlib.machinery.SourceFileLoader("hypr_gamepad", str(SCRIPT))
sp = importlib.util.module_from_spec(importlib.util.spec_from_loader("hypr_gamepad", loader))
sys.modules["hypr_gamepad"] = sp  # dataclasses look their module up while the file loads
loader.exec_module(sp)
# The setup the pad was built on: every test below runs against it, so passing they prove that this
# config file reproduces what the pad did before there was a config file.
SETUP = ROOT / "setups/hermeticormus-dualsense/config.toml"
sp.CONFIG = sp.load_config(SETUP)

EV_KEY, EV_ABS = 0x01, 0x03
CROSS, CIRCLE, TRIANGLE, SQUARE = 0x130, 0x131, 0x133, 0x134
L3, R3 = 0x13D, 0x13E
L1, R1, L2, R2 = 0x136, 0x137, 0x138, 0x139
HAT_X, HAT_Y, LX, LY = 0x10, 0x11, 0x00, 0x01


class FakeHypr:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []
        self.active: dict | None = None   # what j/activewindow answers
        self.monitors: list | None = None  # what j/monitors answers
        self.looks = 0

    def dispatch(self, expr):
        self.sent.append(("dispatch", expr))
        return True

    def eval(self, lua):
        self.sent.append(("eval", lua))
        return True

    def json(self, what):
        if what == "activewindow":
            self.looks += 1
            return self.active
        if what == "monitors":
            return self.monitors
        return None


class FakeFx(sp.Fx):
    def __init__(self):
        self.rumbles: list[str] = []

    def rumble(self, pattern):
        self.rumbles.append(pattern)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class PadCase(unittest.TestCase):
    def setUp(self):
        self.hypr, self.fx, self.clock = FakeHypr(), FakeFx(), Clock()
        self.pad = sp.Pad(self.hypr, self.fx, self.clock)

    def key(self, code, value):
        self.pad.feed(EV_KEY, code, value)

    def tap(self, code):
        self.key(code, 1)
        self.key(code, 0)

    def abs(self, code, value):
        self.pad.feed(EV_ABS, code, value)

    def later(self, seconds):
        self.clock.now += seconds
        self.pad.tick()

    def sent(self):
        out, self.hypr.sent = self.hypr.sent, []
        return out


class WorldLayer(PadCase):
    def test_l2_held_dpad_focuses_the_window_in_that_direction(self):
        self.key(L2, 1)
        for value, direction in ((-1, "l"), (1, "r")):
            self.abs(HAT_X, value)
            self.abs(HAT_X, 0)
            self.assertEqual(self.sent(), [("dispatch", f'hl.dsp.focus({{ direction = "{direction}" }})')])
        for value, direction in ((-1, "u"), (1, "d")):
            self.abs(HAT_Y, value)
            self.abs(HAT_Y, 0)
            self.assertEqual(self.sent(), [("dispatch", f'hl.dsp.focus({{ direction = "{direction}" }})')])

    def test_without_l2_the_dpad_does_not_move_windows(self):
        self.abs(HAT_X, -1)
        self.abs(HAT_X, 0)
        self.assertNotIn("hl.dsp.focus", str(self.sent()))

    def test_l2_is_felt_in_the_hand(self):
        self.key(L2, 1)
        self.assertEqual(self.fx.rumbles, ["click"])
        self.key(L2, 0)
        self.assertFalse(self.pad.world)

    def test_bumpers_step_workspaces_on_this_screen_through_omaspaces(self):
        self.key(L2, 1)
        self.tap(R1)
        self.tap(L1)
        (verb1, lua1), (verb2, lua2) = self.sent()
        self.assertEqual((verb1, verb2), ("eval", "eval"))
        self.assertIn('package.loaded["omaspaces.split"]', lua1)
        self.assertIn("s.focus_relative(1)", lua1)
        self.assertIn('workspace = "m+1"', lua1)  # Hyprland's own step when omaspaces is not loaded
        self.assertIn("s.focus_relative(-1)", lua2)
        self.assertIn('workspace = "m-1"', lua2)

    def test_face_buttons_in_the_world_layer(self):
        self.key(L2, 1)
        for code in (CROSS, CIRCLE, SQUARE, TRIANGLE):
            self.tap(code)
        self.assertEqual([expr for _, expr in self.sent()], [
            'hl.dsp.window.fullscreen({ mode = "fullscreen" })',
            'hl.dsp.focus({ workspace = "previous" })',
            "hl.dsp.window.cycle_next()",
            'hl.dsp.workspace.toggle_special("scratchpad")',
        ])

    def test_the_hat_going_straight_from_left_to_right_presses_right_once(self):
        self.key(L2, 1)
        self.abs(HAT_X, -1)
        self.abs(HAT_X, 1)
        self.assertEqual([e for _, e in self.sent()], ['hl.dsp.focus({ direction = "l" })', 'hl.dsp.focus({ direction = "r" })'])
        self.assertEqual(set(self.pad.held), {"right"})


class Repeat(PadCase):
    def test_a_held_dpad_repeats_after_a_pause_then_steadily_and_stops_on_release(self):
        self.key(L2, 1)
        self.abs(HAT_X, 1)
        self.assertEqual(len(self.sent()), 1)
        first, every = sp.REPEAT["slow"]
        self.later(first - 0.01)
        self.assertEqual(self.sent(), [])
        self.later(0.02)
        self.assertEqual(len(self.sent()), 1)
        self.later(every)
        self.later(every)
        self.assertEqual(len(self.sent()), 2)
        self.abs(HAT_X, 0)
        self.later(1.0)
        self.assertEqual(self.sent(), [])

    def test_a_held_control_keeps_the_layer_it_was_pressed_in(self):
        self.key(L2, 1)
        self.abs(HAT_Y, -1)
        self.key(L2, 0)  # L2 let go first; the held D-pad still focuses up
        self.later(sp.REPEAT["slow"][0] + 0.01)
        self.assertEqual([e for _, e in self.sent()], ['hl.dsp.focus({ direction = "u" })'] * 2)

    def test_screens_do_not_repeat(self):
        self.hypr.monitors = column_monitors("eDP-2")
        self.key(L2, 1)
        self.abs(LX, 0)  # full left
        self.later(2.0)
        self.assertEqual([e for _, e in self.sent()], [focus_monitor("DP-1")])

    def test_the_kernels_own_autorepeat_is_ignored(self):
        self.key(L2, 1)
        self.key(CROSS, 1)
        self.key(CROSS, 2)
        self.key(CROSS, 2)
        self.assertEqual(len(self.sent()), 1)


class Flick(PadCase):
    def test_the_left_stick_reads_as_a_dpad_with_hysteresis(self):
        self.hypr.monitors = column_monitors("eDP-2")
        self.key(L2, 1)
        self.abs(LY, 128 - 70)   # 0.55 up: not yet
        self.assertEqual(self.sent(), [])
        self.abs(LY, 128 - 90)   # 0.71 up: engages
        self.assertEqual([e for _, e in self.sent()], [focus_monitor("DP-1")])
        self.abs(LY, 128 - 60)   # 0.47: still held, nothing new
        self.assertEqual(self.sent(), [])
        self.abs(LY, 128 - 40)   # 0.31: let go
        self.abs(LY, 128 - 90)   # engages again
        self.assertEqual([e for _, e in self.sent()], [focus_monitor("DP-1")])

    def test_rolling_the_stick_to_another_side_switches_direction(self):
        self.hypr.monitors = column_monitors("eDP-2")
        self.key(L2, 1)
        self.abs(LX, 255)        # right: no screen beside, so the one after
        self.abs(LY, 0)          # up wins once it is the larger tilt
        self.abs(LX, 128)
        self.assertEqual([e for _, e in self.sent()], [focus_monitor("HDMI-A-1"), focus_monitor("DP-1")])

    def test_flick_is_pure(self):
        self.assertIsNone(sp.flick(0.1, 0.2, None))
        self.assertEqual(sp.flick(-0.9, 0.1, None), "left")
        self.assertEqual(sp.flick(0.0, 0.5, "down"), "down")
        self.assertIsNone(sp.flick(0.0, 0.3, "down"))
        self.assertEqual(sp.flick(0.5, 0.7, "right"), "down")


class Robustness(PadCase):
    def test_a_failing_action_is_logged_and_the_pad_keeps_working(self):
        def broken(expr):
            raise RuntimeError("boom")

        self.hypr.dispatch = broken
        self.key(L2, 1)
        with self.assertLogs("hypr-gamepad", "ERROR"):
            self.tap(CROSS)
        self.hypr.dispatch = FakeHypr.dispatch.__get__(self.hypr)
        self.tap(CIRCLE)
        self.assertEqual(len(self.sent()), 1)

    def test_reset_lets_go_of_everything(self):
        self.key(L2, 1)
        self.abs(HAT_X, 1)
        self.abs(LX, 0)
        self.pad.reset()
        self.assertFalse(self.pad.world)
        self.assertEqual(self.pad.held, {})
        self.sent()
        self.later(5.0)
        self.assertEqual(self.sent(), [])

    def test_seeded_axes_do_not_press(self):
        self.pad.seed(HAT_X, -1)
        self.pad.seed(LX, 0)
        self.assertEqual(self.pad.held, {})
        self.abs(HAT_X, 0)  # letting go of a hat held at connect presses nothing
        self.assertEqual(self.sent(), [])

    def test_unknown_codes_are_ignored(self):
        self.key(0x2FF, 1)
        self.abs(0x05, 200)  # R2's analog axis: the digital button is what counts
        self.assertEqual(self.sent(), [])


class Layout(unittest.TestCase):
    def test_every_layout_entry_names_an_action_and_a_control(self):
        for layer, rows in sp.LAYOUT.items():
            self.assertIn(layer, sp.LAYER_NAMES)
            for control, action in rows.items():
                self.assertIn(action, sp.ACTIONS, f"{layer} {control}")
                self.assertIn(control, sp.CONTROL_NAMES, f"{layer} {control}")
                self.assertNotEqual(control, sp.LAYER_KEY)

    def test_map_json_lists_every_control_with_its_label(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), "map", "--json", "--pad", "playstation", "--config", str(SETUP)], capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(proc.stdout)
        world = {row["control"]: row for row in doc["layers"]["world"]}
        self.assertEqual(world["south"]["label"], "Full screen on / off")
        self.assertEqual((world["ls_left"]["glyph"], world["ls_left"]["name"]), ("\u2190", "Left stick"))
        self.assertEqual(len(world), len(sp.LAYOUT["world"]) + len(sp.MAP_EXTRA["world"]))  # + L2, right stick

    def test_the_script_loads_without_python_evdev(self):
        code = ("import sys, importlib.machinery, importlib.util; sys.modules['evdev'] = None; "
                f"l = importlib.machinery.SourceFileLoader('p', {str(SCRIPT)!r}); "
                "m = importlib.util.module_from_spec(importlib.util.spec_from_loader('p', l)); sys.modules['p'] = m; l.exec_module(m); "
                "print(len(m.ACTIONS))")
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(int(proc.stdout), len(sp.ACTIONS))


class StubHyprland:
    """A Hyprland request socket that answers from a table and records what it was asked."""

    def __init__(self, runtime: Path, signature: str, answers: dict[str, str]):
        self.dir = runtime / "hypr" / signature
        self.dir.mkdir(parents=True)
        self.path = self.dir / ".socket.sock"
        self.answers, self.asked = answers, []
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(self.path))
        self.server.listen(8)
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            with conn:
                message = conn.recv(65536).decode()
                self.asked.append(message)
                verb = message.split(" ", 1)[0]
                conn.sendall(self.answers.get(message, self.answers.get(verb, "error: unknown")).encode())

    def close(self, keep_file: bool = False):
        try:
            self.server.shutdown(socket.SHUT_RDWR)  # wakes accept(); close alone leaves it listening
        except OSError:
            pass
        self.server.close()
        self.thread.join(timeout=2)
        if not keep_file:  # a crashed Hyprland leaves its socket file behind
            self.path.unlink(missing_ok=True)


class HyprSocket(unittest.TestCase):
    def setUp(self):
        self.runtime = Path(tempfile.mkdtemp(dir="/tmp"))
        self.addCleanup(shutil.rmtree, self.runtime)

    def test_dispatch_eval_and_json_over_the_socket(self):
        stub = StubHyprland(self.runtime, "sig1", {"dispatch": "ok", "eval": "ok",
                                                   "j/activewindow": json.dumps({"class": "foot"})})
        self.addCleanup(stub.close)
        hypr = sp.Hypr(runtime=str(self.runtime), signature="")
        self.assertTrue(hypr.dispatch('hl.dsp.focus({ direction = "l" })'))
        self.assertTrue(hypr.eval("return 1"))
        self.assertEqual(hypr.json("activewindow"), {"class": "foot"})
        self.assertEqual(stub.asked, ['dispatch hl.dsp.focus({ direction = "l" })', "eval return 1", "j/activewindow"])
        self.assertEqual(hypr.signature, "sig1")

    def test_an_error_answer_is_false_and_logged(self):
        stub = StubHyprland(self.runtime, "sig1", {"dispatch": "error: hl.focus: invalid direction"})
        self.addCleanup(stub.close)
        hypr = sp.Hypr(runtime=str(self.runtime), signature="sig1")
        with self.assertLogs("hypr-gamepad", "INFO") as logs:
            self.assertFalse(hypr.dispatch('hl.dsp.focus({ direction = "x" })'))
        self.assertIn("invalid direction", logs.output[0])

    def test_no_hyprland_is_false_not_an_exception(self):
        hypr = sp.Hypr(runtime=str(self.runtime), signature="")
        with self.assertLogs("hypr-gamepad", "INFO"):
            self.assertFalse(hypr.dispatch("hl.dsp.no_op()"))
        self.assertIsNone(hypr.json("activewindow"))

    def test_a_restarted_hyprland_is_found_under_its_new_signature(self):
        old = StubHyprland(self.runtime, "old", {"dispatch": "ok"})
        hypr = sp.Hypr(runtime=str(self.runtime), signature="old")
        self.assertTrue(hypr.dispatch("hl.dsp.no_op()"))
        old.close()
        new = StubHyprland(self.runtime, "new", {"dispatch": "ok"})
        self.addCleanup(new.close)
        self.assertTrue(hypr.dispatch("hl.dsp.no_op()"))  # the old socket file is gone: straight to the new
        self.assertEqual(hypr.signature, "new")

    def test_a_crashed_hyprland_costs_one_press_then_the_new_one_answers(self):
        old = StubHyprland(self.runtime, "old", {"dispatch": "ok"})
        hypr = sp.Hypr(runtime=str(self.runtime), signature="old")
        old.close(keep_file=True)
        new = StubHyprland(self.runtime, "new", {"dispatch": "ok"})
        self.addCleanup(new.close)
        os.utime(new.path, (os.path.getmtime(old.path) + 5,) * 2)  # the live one is the newest
        with self.assertLogs("hypr-gamepad", "INFO") as logs:
            self.assertFalse(hypr.dispatch("hl.dsp.no_op()"))  # refused by the dead socket
            self.assertTrue(hypr.dispatch("hl.dsp.no_op()"))
        self.assertEqual(hypr.signature, "new")
        self.assertEqual(sum("does not answer" in line for line in logs.output), 1)

    def test_check_builds_every_action_and_runs_none(self):
        stub = StubHyprland(self.runtime, "sig1", {"eval": "ok"})
        self.addCleanup(stub.close)
        from contextlib import redirect_stdout
        import io
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(sp.check(sp.Hypr(runtime=str(self.runtime), signature="sig1")), 0)
        probes = [p for a in sp.ACTIONS.values() for p in getattr(a.run, "probes", [])]
        unchecked = {n for n, a in sp.ACTIONS.items() if not getattr(a.run, "probes", None)}
        self.assertEqual(unchecked, {"talk", "talk_toggle", "ideas", "jump", "map"})  # every Hyprland action is checked
        extra = ["eval local _ = " + sp.POINTER_TO.format(x=0, y=0),   # the scroll's pointer move
                 'eval local _ = hl.dsp.event("ormus.sessions-wheel cancel")',
                 'eval local _ = hl.dsp.event("ormus.hypr-gamepad-map hide")']
        self.assertEqual(stub.asked, extra + [f"eval {p}" for p in probes])
        for asked in stub.asked:  # builds a dispatcher, never hands one to hl.dispatch
            self.assertTrue(asked.startswith("eval local") or "error(" in asked, asked)
            self.assertNotIn("hl.dispatch(", asked)
            self.assertNotIn("focus_relative(", asked)
        self.assertIn("ok   focus_left", out.getvalue())

    def test_check_fails_on_one_bad_dispatcher(self):
        bad = 'eval local _ = hl.dsp.window.fullscreen({ mode = "fullscreen" })'
        stub = StubHyprland(self.runtime, "sig1", {"eval": "ok", bad: "error: attempt to call a nil value"})
        self.addCleanup(stub.close)
        from contextlib import redirect_stdout
        import io
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(sp.check(sp.Hypr(runtime=str(self.runtime), signature="sig1")), 1)
        self.assertIn("FAIL fullscreen: error: attempt to call a nil value", out.getvalue())

    def test_dry_hypr_prints_and_never_sends(self):
        stub = StubHyprland(self.runtime, "sig1", {"dispatch": "ok"})
        self.addCleanup(stub.close)
        hypr = sp.DryHypr(runtime=str(self.runtime), signature="sig1")
        from contextlib import redirect_stdout
        import io
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertTrue(hypr.dispatch("hl.dsp.no_op()"))
        self.assertEqual(out.getvalue(), "dry: dispatch hl.dsp.no_op()\n")
        self.assertEqual(stub.asked, [])


class Unit(unittest.TestCase):
    def test_the_unit_runs_the_daemon_in_the_graphical_session(self):
        text = UNIT.read_text()
        self.assertIn("ExecStart=%h/.local/bin/hypr-gamepad run\n", text)
        self.assertIn("Restart=on-failure", text)
        self.assertIn("WantedBy=graphical-session.target", text)
        self.assertNotIn("--dry", text)


if __name__ == "__main__":
    unittest.main()


# Windows as they were on a test machine, 2026-10-29 (hyprctl clients -j; names made neutral).
WORKBOARD = {"address": "0x5606a1", "class": "org.ormus.workboard.desk", "title": "server: DESK", "pid": 4163092, "grouped": []}
LOCAL_HERDR = {"address": "0x5606a2", "class": "foot", "title": "desktop: MAIN", "pid": 1650209, "grouped": []}
REMOTE = {"address": "0x5606a3", "class": "foot", "title": "server: BACKEND", "pid": 3487047, "grouped": []}
GROK = {"address": "0x5606a4", "class": "foot", "title": "Mouse lag from Hyprland software cur… - grok", "pid": 2807681, "grouped": []}
CHROMIUM = {"address": "0x5606a5", "class": "chromium", "title": "Meet - Chromium", "pid": 9, "grouped": []}
BOARD = {"address": "0x5606a6", "class": "chrome-127.0.0.1__-Default", "title": "Sun board", "pid": 9, "grouped": []}
TEAMS = {"address": "0x5606a7", "class": "teams-work", "title": "Chat | Microsoft Teams", "pid": 9, "grouped": []}
GROUPED = {"address": "0x5606a8", "class": "foot", "title": "user@desktop:~", "pid": 9, "grouped": ["0x5606a8", "0x5606a9"]}


def shortcut(mods, key, address):
    return ("dispatch", f'hl.dsp.send_shortcut({{ mods = "{mods}", key = "{key}", window = "address:{address}" }})')


class FakeProc:
    """A /proc with the process trees of a test machine's terminal windows."""

    def __init__(self, root: Path, trees: dict[int, tuple[list[str], list[int]]]):
        for pid, (argv, kids) in trees.items():
            task = root / str(pid) / "task" / str(pid)
            task.mkdir(parents=True)
            (task / "children").write_text(" ".join(map(str, kids)) + (" " if kids else ""))
            (root / str(pid) / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")


class WindowKinds(unittest.TestCase):
    def setUp(self):
        self.proc = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.proc)
        FakeProc(self.proc, {
            1650209: (["foot", "--working-directory=/home/user"], [1650230]),
            1650230: (["bash"], [1650496]),
            1650496: (["herdr"], []),
            4163092: (["foot", "--app-id=org.ormus.workboard.desk", "--", "bash", "-c", "ssh -t ..."], [4163101]),
            4163101: (["bash", "-c", "ssh -t \"$@\"", "workboard", "server", "exec", ".local/bin/herdr-theme", "attach"], [4163106]),
            4163106: (["ssh", "-t", "-o", "ServerAliveInterval=15", "server", "exec", ".local/bin/herdr-theme", "attach", "--session", "desk"], []),
            3487047: (["foot", "--working-directory=/home/user"], [3487074]),
            3487074: (["bash"], [393175]),
            393175: (["ssh", "server"], []),
            2807681: (["foot"], [2807715]),
            2807715: (["bash"], [2807840]),
            2807840: (["grok"], []),
            7000: (["foot"], [7001]),
            7001: (["nvim", "herdr-notes.md"], []),
        })

    def test_processes_tell_a_local_and_a_workboard_herdr(self):
        self.assertTrue(sp.runs_herdr(1650209, str(self.proc)))
        self.assertTrue(sp.runs_herdr(4163092, str(self.proc)))
        self.assertFalse(sp.runs_herdr(2807681, str(self.proc)))
        self.assertFalse(sp.runs_herdr(7000, str(self.proc)))   # a file named herdr-* is not herdr
        self.assertFalse(sp.runs_herdr(424242, str(self.proc)))  # gone

    def test_kinds_of_the_windows_on_a_desktop(self):
        hypr = FakeHypr()
        windows = sp.Windows(hypr, str(self.proc))
        want = {"herdr": [WORKBOARD, LOCAL_HERDR, REMOTE], "terminal": [GROK, GROUPED], "browser": [CHROMIUM],
                "board": [BOARD], "other": [TEAMS]}
        for kind, wins in want.items():
            for win in wins:
                hypr.active = win
                self.assertEqual(windows.active().kind, kind, win["title"])
        hypr.active = GROUPED
        self.assertEqual(windows.active().grouped, 2)
        hypr.active = None
        self.assertIsNone(windows.active())
        hypr.active = {"address": ""}
        self.assertIsNone(windows.active())

    def test_a_shell_title_is_not_herdr(self):
        self.assertEqual(sp.classify("foot", "user@desktop: ~/projects", False), "terminal")
        self.assertEqual(sp.classify("foot", "server: BACKEND", False), "herdr")


class BaseLayer(PadCase):
    def setUp(self):
        super().setUp()
        proc = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, proc)
        self.pad.windows = sp.Windows(self.hypr, str(proc))   # no process trees: kinds from class and title

    def focus(self, win):
        self.hypr.active = win

    def test_face_buttons_reach_the_window_they_were_pressed_in(self):
        self.focus(WORKBOARD)
        self.tap(CROSS)
        self.tap(CIRCLE)
        self.tap(SQUARE)
        self.tap(L3)
        self.assertEqual(self.sent(), [shortcut("", "Return", "0x5606a1"), shortcut("", "Escape", "0x5606a1"),
                                       shortcut("CTRL", "w", "0x5606a1"), shortcut("SHIFT", "Tab", "0x5606a1")])

    def test_the_dpad_is_arrow_keys_in_any_window(self):
        for win in (WORKBOARD, CHROMIUM, TEAMS):
            self.focus(win)
            self.abs(HAT_Y, 1)
            self.abs(HAT_Y, 0)
            self.assertEqual(self.sent(), [shortcut("", "Down", win["address"])])

    def test_bumpers_change_tab_the_way_each_window_does(self):
        cases = [(WORKBOARD, [shortcut("ALT", "Left", "0x5606a1")], [shortcut("ALT", "Right", "0x5606a1")]),
                 (CHROMIUM, [shortcut("CTRL SHIFT", "Tab", "0x5606a5")], [shortcut("CTRL", "Tab", "0x5606a5")]),
                 (BOARD, [shortcut("", "bracketleft", "0x5606a6")], [shortcut("", "bracketright", "0x5606a6")]),
                 (GROUPED, [("dispatch", "hl.dsp.group.prev()")], [("dispatch", "hl.dsp.group.next()")]),
                 (TEAMS, [], []), (GROK, [], [])]
        for win, prev, nxt in cases:
            self.focus(win)
            self.tap(L1)
            self.assertEqual(self.sent(), prev, win["title"])
            self.tap(R1)
            self.assertEqual(self.sent(), nxt, win["title"])

    def test_the_left_stick_walks_herdr_agents_and_spaces(self):
        self.focus(LOCAL_HERDR)   # a terminal whose title is herdr's
        for value, axis, want in ((0, LY, ("ALT SHIFT", "Up")), (255, LY, ("ALT SHIFT", "Down")),
                                  (0, LX, ("ALT", "Up")), (255, LX, ("ALT", "Down"))):
            self.abs(axis, value)
            self.abs(axis, 128)
            self.assertEqual(self.sent(), [shortcut(*want, "0x5606a2")])

    def test_the_left_stick_is_back_and_forward_in_a_browser(self):
        self.focus(CHROMIUM)
        self.abs(LX, 0)
        self.abs(LX, 128)
        self.abs(LY, 0)          # agents mean nothing in a browser
        self.abs(LY, 128)
        self.assertEqual(self.sent(), [shortcut("ALT", "Left", "0x5606a5")])

    def test_r3_sets_the_text_back_to_normal_size_in_any_window(self):
        """A user's first run, 2026-10-29: R3 seemed to do nothing. It zoomed a herdr pane, and a tab
        that holds one pane (the usual case) shows no change: it is normal text size now."""
        for win in (WORKBOARD, CHROMIUM, TEAMS):
            self.focus(win)
            self.tap(R3)
            self.assertEqual(self.sent(), [shortcut("CTRL", "0", win["address"])])

    def test_a_held_arrow_keeps_its_window_even_when_focus_moves(self):
        self.focus(WORKBOARD)
        self.abs(HAT_Y, -1)
        self.focus(CHROMIUM)     # something else took focus; the repeats stay where the press began
        self.later(sp.REPEAT["fast"][0] + 0.001)
        self.later(sp.REPEAT["fast"][1])
        self.assertEqual(self.sent(), [shortcut("", "Up", "0x5606a1")] * 3)
        self.assertEqual(self.hypr.looks, 1)   # the window is read once, at the press

    def test_nothing_focused_sends_nothing(self):
        self.focus(None)
        self.tap(CROSS)
        self.assertEqual(self.sent(), [])

    def test_world_actions_never_read_the_window(self):
        self.focus(WORKBOARD)
        self.key(L2, 1)
        self.tap(CROSS)
        self.assertEqual(self.hypr.looks, 0)


class KeyCheck(unittest.TestCase):
    def test_key_probes_build_a_shortcut_for_no_window(self):
        for name, action in sp.ACTIONS.items():
            for probe in getattr(action.run, "probes", []):
                if "send_shortcut" in probe:
                    self.assertTrue(probe.startswith("local _ = hl.dsp.send_shortcut("), probe)
                    self.assertIn('window = "address:0x0"', probe, name)

    def test_every_key_name_is_one_xkb_knows(self):
        names = {k for a in sp.ACTIONS.values() for k in getattr(a.run, "keysyms", [])}
        self.assertGreaterEqual(names, {"Return", "Escape", "Tab", "Up", "bracketleft", "w", "BackSpace",
                                        "equal", "minus", "0"})
        for name in names:
            self.assertTrue(sp.keysym_known(name), name)
        self.assertFalse(sp.keysym_known("NotAKeyAtAll"))


class FakeProc2:
    def __init__(self):
        self.code = None

    def poll(self):
        return self.code


class FakeRunner:
    def __init__(self):
        self.calls: list[list[str]] = []
        self.procs: list[FakeProc2] = []
        self.fail = False

    def spawn(self, argv):
        self.calls.append(argv)
        if self.fail:
            return None
        proc = FakeProc2()
        self.procs.append(proc)
        return proc

    def capture(self, argv, out):
        self.calls.append(argv)
        if self.fail:
            return None
        proc = FakeProc2()
        proc.out = out
        self.procs.append(proc)
        return proc

    def reap(self):
        pass


class FxLog(sp.Fx):
    def __init__(self):
        self.rumbles, self.notes = [], []

    def rumble(self, pattern):
        self.rumbles.append(pattern)

    def notify(self, title, body=""):
        self.notes.append(f"{title}: {body}")


class TalkCase(PadCase):
    """voice-flow is a stub: each call is a FakeProc2 the test finishes, and the test writes the files
    voice-flow would (recording.state, pill.state)."""

    def setUp(self):
        self.hypr, self.fx, self.clock = FakeHypr(), FxLog(), Clock()
        self.voice = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.voice)
        self.runner = FakeRunner()
        self.pad = sp.Pad(self.hypr, self.fx, self.clock, runner=self.runner, voice=self.voice)
        self.pad.talk.sleep = lambda seconds: None   # reset() waits on a recorder; tests do not wait
        self.hypr.active = WORKBOARD

    def finish_start(self, pid="", wav=""):
        (self.voice / "recording.state").write_text(f"{pid}:{wav}")
        self.runner.procs[-1].code = 0
        self.pad.tick()

    def finish_stop(self, pill="done:hello there"):
        (self.voice / "recording.state").unlink(missing_ok=True)
        (self.voice / "pill.state").write_text(pill)
        self.runner.procs[-1].code = 0
        self.pad.tick()

    def hold_r2(self, seconds):
        self.key(R2, 1)
        self.clock.now += seconds

    def voice_calls(self):
        return sum(c == ["voice-flow"] for c in self.runner.calls)


class TalkHold(TalkCase):
    def test_hold_talk_let_go_paste(self):
        self.hold_r2(0.1)
        self.assertEqual((self.voice_calls(), self.pad.talk.state), (1, "starting"))
        self.finish_start()
        self.assertEqual(self.pad.talk.state, "recording")
        self.clock.now += 2.0
        self.key(R2, 0)
        self.assertEqual((self.voice_calls(), self.pad.talk.state), (2, "stopping"))
        self.finish_stop()
        self.assertEqual(self.pad.talk.state, "idle")
        self.assertEqual(self.fx.rumbles, ["tick", "double"])
        self.assertEqual(self.sent(), [])   # talking sends no key of its own; voice-flow pastes

    def test_let_go_before_the_recorder_is_up_stops_once_it_is(self):
        self.hold_r2(0.6)
        self.key(R2, 0)
        self.assertEqual(self.voice_calls(), 1)
        self.finish_start()
        self.assertEqual((self.voice_calls(), self.pad.talk.state), (2, "stopping"))

    def test_nothing_heard_is_one_tick_not_two(self):
        self.hold_r2(0.1)
        self.finish_start()
        self.clock.now += 1.0
        self.key(R2, 0)
        self.finish_stop("cancel:silent")
        self.assertEqual(self.fx.rumbles, ["tick", "tick"])

    def test_words_kept_on_the_clipboard_count_as_landed(self):
        self.hold_r2(0.1)
        self.finish_start()
        self.clock.now += 1.0
        self.key(R2, 0)
        self.finish_stop("copied:Ctrl+Shift+V hello")
        self.assertEqual(self.fx.rumbles[-1], "double")

    def test_r2_talks_in_the_world_layer_too(self):
        self.key(L2, 1)
        self.hold_r2(0.1)
        self.assertEqual(self.voice_calls(), 1)


class TalkLatch(TalkCase):
    def test_a_tap_keeps_listening_until_the_next_tap(self):
        self.hold_r2(0.1)
        self.key(R2, 0)
        self.assertEqual(self.voice_calls(), 1)
        self.assertIn("click", self.fx.rumbles)
        self.finish_start()
        self.clock.now += 5.0
        self.pad.tick()
        self.assertEqual(self.pad.talk.state, "recording")
        self.key(R2, 1)              # the next tap ends it
        self.assertEqual((self.voice_calls(), self.pad.talk.state), (2, "stopping"))
        self.key(R2, 0)
        self.assertEqual(self.voice_calls(), 2)

    def test_r2_while_the_last_words_are_pasting_says_so(self):
        self.hold_r2(0.1)
        self.finish_start()
        self.clock.now += 1.0
        self.key(R2, 0)
        self.key(R2, 1)
        self.key(R2, 0)
        self.assertEqual(self.voice_calls(), 2)
        self.assertIn("Talk: Still pasting the last words", self.fx.notes)

    def test_r2_ends_a_recording_super_h_started(self):
        (self.voice / "recording.state").write_text("1:/tmp/x.wav")
        self.key(R2, 1)
        self.assertEqual((self.voice_calls(), self.pad.talk.state), (1, "stopping"))


class TalkDrop(TalkCase):
    def test_circle_while_talking_drops_the_recording_and_is_not_esc(self):
        recorder = subprocess.Popen(["sleep", "30"])
        self.addCleanup(recorder.kill)
        wav = self.voice / "rec.wav"
        wav.write_bytes(b"RIFF")
        (self.voice / "agent.mode").write_text("")
        self.hold_r2(0.1)
        self.finish_start(pid=str(recorder.pid), wav=str(wav))
        self.tap(CIRCLE)
        self.assertEqual(recorder.wait(timeout=5), -signal.SIGTERM)
        self.assertFalse((self.voice / "recording.state").exists())
        self.assertFalse(wav.exists())
        self.assertFalse((self.voice / "agent.mode").exists())
        self.assertEqual((self.voice / "pill.state").read_text(), "cancel")
        self.assertEqual(self.pad.talk.state, "idle")
        self.assertEqual(self.sent(), [])          # no Escape went to the window
        self.clock.now += 1.0
        self.key(R2, 0)                            # letting go of R2 afterwards pastes nothing
        self.assertEqual(self.voice_calls(), 1)

    def test_circle_while_the_recorder_starts_drops_it_once_up(self):
        self.hold_r2(0.1)
        self.tap(CIRCLE)
        self.finish_start(pid="", wav="")
        self.assertEqual(self.pad.talk.state, "idle")
        self.assertFalse((self.voice / "recording.state").exists())
        self.assertEqual(self.voice_calls(), 1)

    def test_circle_when_not_talking_is_esc(self):
        self.tap(CIRCLE)
        self.assertEqual(self.sent(), [shortcut("", "Escape", "0x5606a1")])


class TalkTrouble(TalkCase):
    def test_a_recorder_that_never_starts_is_said(self):
        self.hold_r2(0.1)
        self.runner.procs[-1].code = 1
        self.pad.tick()
        self.assertEqual(self.pad.talk.state, "idle")
        self.assertIn("Talk: The recording did not start", self.fx.notes)

    def test_no_voice_flow_is_said(self):
        self.runner.fail = True
        self.hold_r2(0.1)
        self.assertEqual(self.pad.talk.state, "idle")
        self.assertIn("Talk: voice-flow did not start", self.fx.notes)
        self.clock.now += 1
        self.key(R2, 0)
        self.assertEqual(len(self.runner.calls), 1)

    def test_the_pad_going_away_mid_sentence_drops_it(self):
        self.hold_r2(0.1)
        self.finish_start()
        self.pad.reset()
        self.assertEqual(self.pad.talk.state, "idle")
        self.assertFalse((self.voice / "recording.state").exists())
        self.assertEqual(self.voice_calls(), 1)   # never the stop call that would paste
        self.assertIn("Talk: The pad went away: the recording was dropped", self.fx.notes)

    def test_the_pad_going_away_while_the_recorder_starts_drops_it_once_up(self):
        self.hold_r2(0.1)
        self.pad.reset()
        self.finish_start()
        self.assertEqual(self.pad.talk.state, "idle")
        self.assertEqual(self.voice_calls(), 1)


class Ideas(TalkCase):
    def test_create_turns_the_voice_ideas_listener_on_or_off(self):
        self.tap(0x13A)
        self.assertEqual(self.runner.calls, [["voice-ideas-toggle"]])
        self.key(L2, 1)
        self.tap(0x13A)
        self.assertEqual(len(self.runner.calls), 2)


class DryTalk(unittest.TestCase):
    def test_dry_runner_says_and_starts_nothing(self):
        from contextlib import redirect_stdout
        import io
        out = io.StringIO()
        with redirect_stdout(out):
            proc = sp.DryRunner().spawn(["voice-flow"])
        self.assertEqual(out.getvalue(), "dry: run voice-flow\n")
        self.assertEqual(proc.poll(), 0)

    def test_the_unit_keeps_the_sessions_path(self):
        self.assertNotIn("Environment=PATH", UNIT.read_text())


WHEEL = ROOT / "tests/fixtures/wheel-items.json"  # `sun-wheel items` on a test machine, 2026-10-29, first 3, names made neutral


class JumpCase(TalkCase):
    def answer(self, text=None, code=0):
        proc = self.runner.procs[-1]
        Path(proc.out).write_text(WHEEL.read_text() if text is None else text)
        proc.code = code
        self.pad.tick()

    def jumps(self):
        return [c[2] for c in self.runner.calls if c[:2] == ["sun-wheel", "jump"]]


class JumpTriangle(JumpCase):
    def test_triangle_shows_the_agent_that_waits_most(self):
        self.tap(TRIANGLE)
        self.assertEqual(self.runner.calls, [["sun-wheel", "items"]])
        self.answer()
        self.assertEqual(self.runner.calls[-1], ["sun-wheel", "jump", "server|desk|w9:p1", "--notify"])
        self.assertEqual(self.fx.notes[-1], "1 of 3: Web sessions update DM: server · ONBOARDING · run waits on you")
        self.assertFalse(Path(self.runner.procs[0].out).exists())   # the answer file is cleaned up
        self.assertEqual(self.sent(), [])

    def test_again_walks_down_the_same_list_then_round(self):
        self.tap(TRIANGLE)
        self.answer()
        for _ in range(3):
            self.clock.now += 2.0
            self.tap(TRIANGLE)
        self.assertEqual(self.jumps(), ["server|desk|w9:p1", "server|work|w1:p4", "server|desk|w2:p1", "server|desk|w9:p1"])
        self.assertEqual(sum(c == ["sun-wheel", "items"] for c in self.runner.calls), 1)
        self.assertTrue(self.fx.notes[-2].startswith("3 of 3: Haiku para el jardín: server · ~ · done, not seen yet"))

    def test_after_a_pause_the_list_is_read_again(self):
        self.tap(TRIANGLE)
        self.answer()
        self.clock.now += sp.JUMP_CYCLE_S + 1
        self.tap(TRIANGLE)
        self.assertEqual(self.runner.calls[-1], ["sun-wheel", "items"])
        self.answer()
        self.assertEqual(self.jumps(), ["server|desk|w9:p1", "server|desk|w9:p1"])

    def test_a_press_while_the_list_is_on_its_way_waits_for_it(self):
        self.tap(TRIANGLE)
        self.tap(TRIANGLE)
        self.assertEqual(self.runner.calls, [["sun-wheel", "items"]])

    def test_nothing_waiting_is_said(self):
        self.tap(TRIANGLE)
        self.answer('{"items": [], "more": 0}')
        self.assertEqual(self.jumps(), [])
        self.assertIn("Agents: Nothing waits on you", self.fx.notes)

    def test_a_board_that_does_not_answer_is_said(self):
        for text, code in (("", 1), ("not json", 0), ('{"no": "items"}', 0)):
            self.tap(TRIANGLE)
            self.answer(text, code)
            self.assertEqual(self.fx.notes[-1], "Agents: sun-wheel does not answer")
            self.clock.now += sp.JUMP_CYCLE_S + 1
        self.assertEqual(self.jumps(), [])

    def test_a_jump_that_lands_is_felt(self):
        self.tap(TRIANGLE)
        self.answer()
        self.runner.procs[-1].code = 0
        self.pad.tick()
        self.assertEqual(self.fx.rumbles[-1], "double")

    def test_a_failed_jump_is_not_felt_as_landed(self):
        self.tap(TRIANGLE)
        self.answer()
        self.runner.procs[-1].code = 1
        self.pad.tick()
        self.assertNotEqual(self.fx.rumbles[-1], "double")

    def test_in_the_world_layer_triangle_is_still_the_scratchpad(self):
        self.key(L2, 1)
        self.tap(TRIANGLE)
        self.assertEqual(self.runner.calls, [])
        self.assertEqual([e for _, e in self.sent()], ['hl.dsp.workspace.toggle_special("scratchpad")'])


class Board(JumpCase):
    BOARD = "hl.dsp.exec_cmd([[omarchy-launch-or-focus-webapp 'Sun board' 'http://127.0.0.1:7741/']])"

    def test_a_ps_tap_raises_the_sun_board(self):
        self.key(0x13C, 1)
        self.assertEqual(self.sent(), [])      # nothing on the press: a hold is the wheel's
        self.clock.now += 0.1
        self.key(0x13C, 0)
        self.assertEqual(self.sent(), [("dispatch", self.BOARD)])

    def test_a_long_ps_hold_does_not_raise_it(self):
        self.key(0x13C, 1)
        self.clock.now += 1.0
        self.key(0x13C, 0)
        self.assertEqual(self.sent(), [])


class FakeWheel(sp.Wheel):
    def __init__(self):
        self.events = []

    def scroll(self, vertical, horizontal, notches_v, notches_h):
        self.events.append((vertical, horizontal, notches_v, notches_h))

    def totals(self):
        return [sum(e[i] for e in self.events) for i in range(4)]


RX, RY = 0x03, 0x04


class ScrollCase(PadCase):
    def setUp(self):
        super().setUp()
        self.wheel = FakeWheel()
        self.pad = sp.Pad(self.hypr, self.fx, self.clock, wheel=self.wheel)
        self.hypr.active = dict(WORKBOARD, at=[2681, 1198], size=[1683, 1017])
        self.pointer = {"x": 2878, "y": 1474}   # inside the workboard (measured on a test machine, 2026-10-29)
        real_json = self.hypr.json
        self.hypr.json = lambda what: self.pointer if what == "cursorpos" else real_json(what)

    def tilt(self, rx, ry, seconds):
        self.abs(RX, rx)
        self.abs(RY, ry)
        for _ in range(int(seconds / 0.01)):
            self.later(0.01)


class ScrollRight(ScrollCase):
    def test_the_rate_curve(self):
        self.assertEqual(sp.scroll_rate(0.1, 2400), 0.0)
        self.assertEqual(sp.scroll_rate(-0.18, 2400), 0.0)
        self.assertAlmostEqual(sp.scroll_rate(1.0, 2400), 2400)
        self.assertAlmostEqual(sp.scroll_rate(-1.0, 2400), -2400)
        self.assertAlmostEqual(sp.scroll_rate(0.59, 2400), 600, delta=1)   # half the way past the dead zone: a quarter

    def test_full_tilt_up_scrolls_up_twenty_notches_a_second(self):
        self.tilt(128, 0, 1.0)
        hi_v, hi_h, notches_v, notches_h = self.wheel.totals()
        self.assertAlmostEqual(hi_v, 2400 * 128 / 127 * 0 + 2400, delta=40)   # stick 0 = full up
        self.assertEqual(notches_v, hi_v // 120)
        self.assertEqual((hi_h, notches_h), (0, 0))

    def test_down_is_negative_and_sideways_is_the_horizontal_wheel(self):
        self.tilt(128, 255, 0.5)
        self.assertLess(self.wheel.totals()[0], 0)
        self.wheel.events.clear()
        self.tilt(255, 128, 0.5)
        hi_v, hi_h, _, _ = self.wheel.totals()
        self.assertEqual(hi_v, 0)
        self.assertGreater(hi_h, 500)

    def test_a_resting_stick_sends_nothing(self):
        self.tilt(140, 115, 1.0)   # 0.09 / 0.10: inside the dead zone
        self.assertEqual(self.wheel.events, [])

    def test_a_gesture_ends_with_one_empty_event(self):
        self.tilt(128, 0, 0.2)
        self.tilt(128, 128, 0.1)
        self.assertEqual(self.wheel.events[-1], (0, 0, 0, 0))
        self.assertEqual(sum(e == (0, 0, 0, 0) for e in self.wheel.events), 1)

    def test_the_pointer_inside_the_focused_window_stays(self):
        self.tilt(128, 0, 0.2)
        self.assertEqual(self.sent(), [])

    def test_a_pointer_elsewhere_moves_to_the_focused_window_once_per_gesture(self):
        self.pointer = {"x": 100, "y": 100}
        self.tilt(128, 0, 0.3)
        self.assertEqual(self.sent(), [("dispatch", "hl.dsp.cursor.move({ x = 3522, y = 1706 })")])
        self.tilt(128, 128, 0.1)
        self.tilt(128, 0, 0.1)    # a new gesture looks again
        self.assertEqual(len(self.sent()), 1)

    def test_the_left_stick_does_not_scroll(self):
        self.tilt(128, 128, 0.0)
        self.abs(LY, 0)
        for _ in range(50):
            self.later(0.01)
        self.assertEqual(self.wheel.events, [])

    def test_reset_stops_a_scroll(self):
        self.tilt(128, 0, 0.1)
        self.pad.reset()
        self.wheel.events.clear()
        self.later(0.5)
        self.assertEqual(self.wheel.events, [])


class DryScroll(unittest.TestCase):
    def test_the_dry_wheel_says_each_gesture_once(self):
        from contextlib import redirect_stdout
        import io
        wheel, out = sp.DryWheel(), io.StringIO()
        with redirect_stdout(out):
            wheel.scroll(240, 0, 2, 0)
            wheel.scroll(120, 0, 1, 0)
            wheel.scroll(0, 0, 0, 0)
            wheel.scroll(0, 0, 0, 0)
        self.assertEqual(out.getvalue(), "dry: scrolled 360 up, 0 right (hi-res, 120 a notch)\n")


# A test machine's screens, 2026-10-29 (hyprctl monitors -j, trimmed): HDMI-A-1 has focus.
MONITORS = [
    {"name": "eDP-2", "x": 2883, "y": 360, "width": 2560, "height": 1600, "scale": 2.0, "transform": 0, "focused": False},
    {"name": "HDMI-A-1", "x": 2669, "y": 1160, "width": 2560, "height": 1600, "scale": 1.5, "transform": 0, "focused": True},
    {"name": "DP-1", "x": 1707, "y": -661, "width": 5120, "height": 1440, "scale": 1.41, "transform": 0, "focused": False},
]
PS = 0x13C


def events(sent):
    return [e[len('hl.dsp.event("ormus.sessions-wheel '):-2] for _, e in sent if e.startswith("hl.dsp.event(")]


class WheelCase(ScrollCase):
    def setUp(self):
        super().setUp()
        self.hypr.monitors = MONITORS

    def hold_ps(self, seconds=0.5):
        self.key(PS, 1)
        for _ in range(int(seconds / 0.01)):
            self.later(0.01)


class PadWheel(WheelCase):
    def test_the_middle_of_the_focused_screen(self):
        x, y = sp.focused_center(self.hypr)
        self.assertAlmostEqual(x, 2669 + 2560 / 1.5 / 2)
        self.assertAlmostEqual(y, 1160 + 1600 / 1.5 / 2)
        self.hypr.monitors = [dict(MONITORS[1], transform=1)]   # turned a quarter
        self.assertAlmostEqual(sp.focused_center(self.hypr)[0], 2669 + 1600 / 1.5 / 2)
        self.hypr.monitors = []
        self.assertIsNone(sp.focused_center(self.hypr))

    def test_ps_held_opens_the_wheel_on_the_focused_screen(self):
        self.hold_ps()
        got = events(self.sent())
        self.assertEqual(len(got), 1)
        verb, token, x, y = got[0].split(" ")
        self.assertEqual((verb, x, y), ("padhold", "3522.3", "1693.3"))
        self.assertTrue(token.startswith("pad"))
        self.assertEqual(self.wheel.events, [])

    def test_the_stick_aims_and_never_scrolls_while_it_is_open(self):
        self.hold_ps()
        token = events(self.sent())[0].split(" ")[1]
        self.abs(RX, 255)          # right
        self.abs(RY, 128)
        for _ in range(10):
            self.later(0.01)
        self.abs(RX, 128)
        self.abs(RY, 0)            # up
        for _ in range(10):
            self.later(0.01)
        aims = [e for e in events(self.sent()) if e.startswith("aim")]
        self.assertEqual(aims[0], f"aim {token} 1.00 0.00")
        self.assertEqual(aims[-1], f"aim {token} 0.00 -1.00")
        self.assertEqual(self.wheel.events, [])

    def test_aims_are_few(self):
        self.hold_ps()
        self.sent()
        for value in range(128, 256, 2):   # a slow roll to the right over 0.64 s
            self.abs(RX, value)
            self.later(0.01)
        aims = [e for e in events(self.sent()) if e.startswith("aim")]
        self.assertLessEqual(len(aims), 22)  # at most one each 30 ms, and only on a 0.05 step
        self.assertTrue(aims[-1].endswith("1.00 0.00") or aims[-1].endswith("0.95 0.00"), aims[-1])

    def test_letting_go_of_ps_jumps_and_does_not_raise_the_board(self):
        self.hold_ps()
        token = events(self.sent())[0].split(" ")[1]
        self.abs(RX, 255)
        self.key(PS, 0)
        sent = self.sent()
        self.assertEqual(events(sent)[-2:], [f"aim {token} 1.00 0.00", f"release {token} nan nan"])  # the last aim first
        self.assertNotIn("omarchy-launch-or-focus-webapp", str(sent))

    def test_circle_closes_the_wheel_with_no_jump_and_no_esc(self):
        self.hypr.active = WORKBOARD
        self.hold_ps()
        self.sent()
        self.tap(CIRCLE)
        self.assertEqual(self.sent(), [("dispatch", 'hl.dsp.event("ormus.sessions-wheel cancel")')])
        self.key(PS, 0)
        self.assertEqual(self.sent(), [])

    def test_no_scroll_after_the_wheel_until_the_stick_rests(self):
        self.hold_ps()
        self.abs(RY, 0)
        self.key(PS, 0)
        self.wheel.events.clear()
        for _ in range(30):
            self.later(0.01)
        self.assertEqual(self.wheel.events, [])
        self.abs(RY, 128)          # rests
        self.abs(RY, 0)            # and tilts again: now it scrolls
        for _ in range(30):
            self.later(0.01)
        self.assertGreater(self.wheel.totals()[0], 0)

    def test_a_ps_tap_still_raises_the_board_and_opens_no_wheel(self):
        self.key(PS, 1)
        self.later(0.1)
        self.key(PS, 0)
        sent = self.sent()
        self.assertEqual(events(sent), [])
        self.assertIn("omarchy-launch-or-focus-webapp", str(sent))

    def test_the_pad_going_away_closes_the_wheel(self):
        self.hold_ps()
        self.sent()
        self.pad.reset()
        self.assertEqual(events(self.sent()), ["cancel"])


OPTIONS = 0x13B


def map_events(sent):
    return [e[len('hl.dsp.event("ormus.hypr-gamepad-map '):-2] for _, e in sent if e.startswith('hl.dsp.event("ormus.hypr-gamepad-map')]


class MapOnScreen(PadCase):
    def setUp(self):
        super().setUp()
        proc = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, proc)
        self.pad.windows = sp.Windows(self.hypr, str(proc))
        self.hypr.active = CHROMIUM

    def test_options_held_shows_the_map_for_the_window_and_letting_go_hides_it(self):
        self.key(OPTIONS, 1)
        self.assertEqual(map_events(self.sent()), ["show browser base 0"])
        self.clock.now += 1.0
        self.key(OPTIONS, 0)
        self.assertEqual(map_events(self.sent()), ["hide"])

    def test_a_tap_keeps_it_up_until_the_next_options(self):
        self.key(OPTIONS, 1)
        self.clock.now += 0.1
        self.key(OPTIONS, 0)
        self.assertEqual(map_events(self.sent()), ["show browser base 0"])
        self.clock.now += 5.0
        self.key(OPTIONS, 1)
        self.assertEqual(map_events(self.sent()), ["hide"])
        self.clock.now += 0.1
        self.key(OPTIONS, 0)                   # that press only closed it
        self.assertEqual(self.sent(), [])

    def test_l2_while_it_is_up_shows_the_desktop_side(self):
        self.key(OPTIONS, 1)
        self.key(L2, 1)
        self.key(L2, 0)
        self.assertEqual(map_events(self.sent()), ["show browser base 0", "show browser world 0", "show browser base 0"])

    def test_l2_without_the_map_sends_nothing_for_it(self):
        self.key(L2, 1)
        self.key(L2, 0)
        self.assertEqual(map_events(self.sent()), [])

    def test_options_in_the_world_layer_opens_that_side(self):
        self.hypr.active = WORKBOARD
        self.key(L2, 1)
        self.key(OPTIONS, 1)
        self.assertEqual(map_events(self.sent()), ["show herdr world 0"])

    def test_the_pad_going_away_hides_it(self):
        self.key(OPTIONS, 1)
        self.clock.now += 0.1
        self.key(OPTIONS, 0)
        self.sent()
        self.pad.reset()
        self.assertEqual(map_events(self.sent()), ["hide"])


class MapRows(unittest.TestCase):
    def test_rows_follow_the_pad_and_carry_what_the_overlay_needs(self):
        rows = sp.map_rows("base")
        self.assertEqual([r["group"] for r in rows][:4], ["Buttons"] * 4)
        self.assertEqual([r["control"] for r in rows][:5], ["south", "east", "west", "north", "up"])
        by = {r["control"]: r for r in rows}
        self.assertEqual((by["south"]["glyph"], by["south"]["name"]), ("✕", "Cross"))
        self.assertEqual((by["ls_left"]["glyph"], by["ls_left"]["name"]), ("←", "Left stick"))
        self.assertEqual(by["ls_left"]["labels"]["browser"], "Back")
        self.assertEqual(by["ls_up"]["kinds"], ["board", "herdr"])
        self.assertEqual(by["south"]["kinds"], ["*"])
        self.assertEqual(by["rstick"]["label"], "Scroll; the further, the faster")
        self.assertEqual(by["l2"]["label"], "Hold: the desktop side")
        for r in rows:
            self.assertEqual(set(r), {"control", "group", "glyph", "name", "label", "labels", "kinds"})
        world = {r["control"]: r for r in sp.map_rows("world")}
        self.assertEqual([world[c]["label"] for c in ("rs_up", "rs_down", "r3")],
                         ["Bigger text", "Smaller text", "Normal text size"])
        self.assertEqual((world["rs_up"]["glyph"], world["rs_up"]["name"]), ("↑", "Right stick"))
        self.assertNotIn("rstick", world)          # with L2 held the right stick sizes text, it does not scroll
        self.assertEqual((by["l3"]["label"], by["r3"]["label"]), ("Shift+Tab: the agent's mode", "Normal text size"))
        sticks = [r["control"] for r in rows if r["group"] == "Sticks"]
        self.assertEqual(sticks, ["ls_up", "ls_down", "ls_left", "ls_right", "l3", "rstick", "r3"])

    def test_map_json_has_both_sides_and_the_battery(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), "map", "--json", "--pad", "playstation", "--config", str(SETUP)], capture_output=True, text=True, timeout=10)
        doc = json.loads(proc.stdout)
        self.assertEqual(set(doc["layers"]), {"base", "world"})
        self.assertIn("battery", doc)
        self.assertEqual(doc["layer_names"]["world"], "L2 held: the desktop")


class GameCase(WheelCase):
    def setUp(self):
        super().setUp()
        self.fx = FxLog()
        self.runner = FakeRunner()
        self.voice = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.voice)
        self.pad = sp.Pad(self.hypr, self.fx, self.clock, wheel=self.wheel, runner=self.runner, voice=self.voice)
        self.hypr.active = WORKBOARD

    def chord(self, first=PS, second=OPTIONS):
        self.key(first, 1)
        self.clock.now += 0.1
        self.key(second, 1)
        self.key(second, 0)
        self.key(first, 0)


class GameMode(GameCase):
    def test_ps_and_options_give_the_pad_to_a_game_and_nothing_else_happens(self):
        self.chord()
        self.assertEqual(self.pad.mode, "game")
        self.assertEqual(self.fx.rumbles[-1], "long")
        self.assertIn("Game mode: The pad is the game's. PS + Options brings it back.", self.fx.notes)
        sent = str(self.sent())
        self.assertNotIn("omarchy-launch-or-focus-webapp", sent)   # not the board (PS tap)
        self.assertNotIn("hypr-gamepad-map", sent)                      # not the map (Options)

    def test_either_order_is_the_chord(self):
        self.chord(OPTIONS, PS)
        self.assertEqual(self.pad.mode, "game")
        self.assertEqual(map_events(self.sent()), ["show herdr base 0", "hide"])   # Options first showed it

    def test_in_game_mode_the_pad_acts_on_nothing(self):
        self.chord()
        self.sent()
        for code in (CROSS, CIRCLE, TRIANGLE, L1, R1, R2, 0x13A):
            self.tap(code)
        self.key(L2, 1)
        self.abs(HAT_X, -1)
        self.abs(LY, 0)
        self.abs(RY, 0)
        for _ in range(40):
            self.later(0.01)
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.wheel.events, [])

    def test_the_chord_again_brings_it_back(self):
        self.chord()
        self.abs(RY, 0)            # a stick left tilted in the game
        self.chord()
        self.assertEqual(self.pad.mode, "desk")
        self.assertEqual(self.fx.rumbles[-1], "double")
        self.abs(HAT_Y, 1)
        self.abs(HAT_Y, 0)
        self.assertEqual(self.sent()[-1], shortcut("", "Down", "0x5606a1"))

    def test_going_to_a_game_drops_a_talk_and_closes_the_wheel(self):
        self.key(R2, 1)
        (self.voice / "recording.state").write_text(":")
        self.runner.procs[-1].code = 0
        self.pad.tick()
        self.assertEqual(self.pad.talk.state, "recording")
        self.key(PS, 1)
        self.later(0.5)            # the wheel opened
        self.key(OPTIONS, 1)
        self.assertEqual(self.pad.talk.state, "idle")
        self.assertIn("cancel", events(self.sent()))
        self.key(R2, 0)
        self.assertEqual(sum(c == ["voice-flow"] for c in self.runner.calls), 1)   # nothing pasted

    def test_the_mode_outlives_a_pad_that_goes_away(self):
        self.chord()
        self.pad.reset()
        self.assertEqual(self.pad.mode, "game")
        self.assertEqual(self.pad.buttons, set())


class FakeDev:
    path, name = "/dev/input/event258", "DualSense Wireless Controller"

    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def grab(self):
        if self.fail:
            raise OSError(16, "Device or resource busy")
        self.calls.append("grab")

    def ungrab(self):
        self.calls.append("ungrab")


class Grab(unittest.TestCase):
    def test_the_map_lists_the_chord(self):
        rows = {r["control"]: r for r in sp.map_rows("base")}
        self.assertEqual((rows["chord"]["name"], rows["chord"]["group"]), ("PS + Options", "Middle"))


RULE = ROOT / "udev/60-hypr-gamepad.rules"
# A Bluetooth input report as the pad sent it on a test machine (2026-10-29, hidraw11), first 13 of 78 bytes:
# id 0x31, a tag byte, sticks 127 130 128 127, triggers 0 0, seq, buttons 0x08 0 0 0.
REPORT = bytes([0x31, 0x01, 127, 130, 128, 127, 0, 0, 0x2a, 0x08, 0, 0, 0]) + bytes(65)


def with_mic(report, down):
    b = bytearray(report)
    b[11] = 0x04 if down else 0
    return bytes(b)


class MicButton(TalkCase):
    def test_the_mic_bit_in_the_raw_reports(self):
        self.assertFalse(sp.mic_down(REPORT))
        self.assertTrue(sp.mic_down(with_mic(REPORT, True)))
        usb = bytes([0x01, 127, 130, 128, 127, 0, 0, 0x2a, 0x08, 0, 0x04, 0]) + bytes(52)
        self.assertTrue(sp.mic_down(usb))
        self.assertIsNone(sp.mic_down(bytes([0x05]) + bytes(40)))   # a feature reply, not input
        self.assertIsNone(sp.mic_down(bytes([0x31, 1, 2])))

    def test_the_reader_turns_reports_into_presses_and_lets_go(self):
        # hidraw gives one report per read: a SEQPACKET pair keeps that (a pipe would glue them)
        reader, writer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(writer.close)
        reader.setblocking(False)
        mic = sp.MicReader(str(Path(tempfile.mkdtemp())))   # no hidraw here
        self.assertIsNone(mic.fd)
        mic.fd = reader.detach()
        self.addCleanup(mic.close)
        seen = []
        self.pad.button = lambda name, down: seen.append((name, down))
        for down in (False, True, True, True, False, False):
            writer.send(with_mic(REPORT, down))
        mic.read(self.pad)
        self.assertEqual(seen, [("mic", True), ("mic", False)])

    def test_a_press_starts_talking_and_the_next_one_pastes(self):
        self.pad.button("mic", True)
        self.pad.button("mic", False)
        self.assertEqual((self.voice_calls(), self.pad.talk.state), (1, "starting"))
        self.finish_start()
        self.clock.now += 3.0
        self.pad.tick()
        self.assertEqual(self.pad.talk.state, "recording")   # kept listening
        self.pad.button("mic", True)
        self.pad.button("mic", False)
        self.assertEqual((self.voice_calls(), self.pad.talk.state), (2, "stopping"))

    def test_the_mic_button_does_nothing_in_game_mode(self):
        self.pad.mode = "game"
        self.pad.button("mic", True)
        self.pad.button("mic", False)
        self.assertEqual(self.runner.calls, [])


class FakeLights(sp.Lights):
    def __init__(self):
        self.colors, self.lit = [], []

    def color(self, rgb):
        self.colors.append(rgb)

    def players(self, lit):
        self.lit.append(lit)


# The same screens with Hyprland's ids (2026-10-29): HDMI-A-1 has focus, and is third by id.
SCREENS = [dict(MONITORS[0], id=0), dict(MONITORS[1], id=2), dict(MONITORS[2], id=1)]


class PadLights(TalkCase):
    def setUp(self):
        super().setUp()
        self.lights = FakeLights()
        self.pad.lights = self.lights
        self.hypr.monitors = SCREENS

    def test_the_lightbar_follows_the_state_and_is_written_on_change_only(self):
        self.pad.tick()
        self.pad.tick()
        self.assertEqual(self.lights.colors, [sp.LIGHT["desk"]])
        self.key(L2, 1)
        self.pad.tick()
        self.key(L2, 0)
        self.pad.tick()
        self.hold_r2(0.1)
        self.pad.tick()
        self.assertEqual(self.lights.colors, [sp.LIGHT[s] for s in ("desk", "world", "desk", "talk")])
        self.pad.toggle_mode()
        self.pad.tick()
        self.assertEqual(self.lights.colors[-1], sp.LIGHT["game"])

    def test_the_player_lights_say_which_screen_has_focus(self):
        self.pad.tick()
        self.assertEqual(self.lights.lit, [sp.PLAYERS[3]])        # HDMI-A-1: third by id
        self.hypr.monitors = [dict(m, focused=m["name"] == "eDP-2") for m in SCREENS]
        self.pad.tick()                                          # not read again so soon
        self.assertEqual(len(self.lights.lit), 1)
        self.clock.now += sp.SCREEN_EVERY_S
        self.pad.tick()
        self.assertEqual(self.lights.lit[-1], sp.PLAYERS[1])
        self.assertEqual(sp.PLAYERS[1], (3,))                    # one light, in the middle

    def test_no_monitors_leaves_the_player_lights_alone(self):
        self.hypr.monitors = None
        self.pad.tick()
        self.assertEqual(self.lights.lit, [])


class SysfsLightsFiles(unittest.TestCase):
    def test_it_writes_the_led_files_and_stops_after_a_refusal(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        lights = sp.SysfsLights("/sys/devices/x/input/input132")
        self.assertEqual(lights.rgb.name, "input132:rgb:indicator")
        lights.rgb = root / "rgb"
        lights.rgb.mkdir()
        lights.player = [root / f"p{n}" for n in range(1, 6)]
        for path in lights.player:
            path.mkdir()
        lights.color((255, 150, 18))
        lights.players((2, 4))
        self.assertEqual((lights.rgb / "multi_intensity").read_text(), "255 150 18")
        self.assertEqual((lights.rgb / "brightness").read_text(), "255")
        self.assertEqual([(p / "brightness").read_text() for p in lights.player], ["0", "1", "0", "1", "0"])
        lights.rgb = root / "refused"  # there, but not writable: the udev rule is not installed
        lights.rgb.mkdir(mode=0o500)
        with self.assertLogs("hypr-gamepad", "INFO") as logs:
            lights.color((1, 2, 3))
            lights.color((4, 5, 6))
        self.assertEqual(len(logs.output), 1)
        self.assertTrue(lights.broken)


class OnlyWhatThePadHas(unittest.TestCase):
    """Not every pad has a DualSense's extras. The mic button is read only on a DualSense: a DualShock
    4's USB report carries a timestamp where the DualSense keeps the mic bit, so reading it there would
    talk at random. The lights are the LED files the pad has; the battery is the pad's own power
    supply, whatever its driver calls it."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)

    def test_the_mic_button_is_read_only_on_a_dualsense(self):
        self.assertTrue(sp.has_mic(0x054C, 0x0CE6))   # DualSense
        self.assertTrue(sp.has_mic(0x054C, 0x0DF2))   # DualSense Edge
        for vendor, product in ((0x054C, 0x09CC), (0x054C, 0x05C4), (0x045E, 0x0B13), (0x057E, 0x2009)):
            self.assertFalse(sp.has_mic(vendor, product), hex(product))

    def test_a_dualshock_report_reads_as_a_mic_press_which_is_why(self):
        report = bytes([0x01, 128, 128, 128, 128, 0x08, 0, 0, 0, 0, 0x04, 0])  # byte 10: its timestamp
        self.assertTrue(sp.mic_down(report))

    def test_a_pad_with_a_lightbar_and_no_player_lights_gets_its_lightbar(self):
        (self.root / "input7:rgb:indicator").mkdir()
        lights = sp.SysfsLights("/sys/devices/x/input/input7", leds=str(self.root))
        with self.assertNoLogs("hypr-gamepad", "INFO"):
            lights.color((255, 150, 18))
            lights.players((1,))
        self.assertEqual((self.root / "input7:rgb:indicator" / "multi_intensity").read_text(), "255 150 18")
        self.assertFalse(lights.broken)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["input7:rgb:indicator"])

    def test_a_pad_without_led_files_gets_no_lights_and_no_complaint(self):
        lights = sp.SysfsLights("/sys/devices/x/input/input7", leds=str(self.root))
        with self.assertNoLogs("hypr-gamepad", "INFO"):
            lights.color((1, 2, 3))
            lights.players((1, 2))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_the_battery_is_the_pads_own_power_supply(self):
        where = self.root / "input7"
        supply = where / "device" / "power_supply" / "nintendo_switch_controller_battery_aa"
        supply.mkdir(parents=True)
        (supply / "capacity").write_text("75\n")
        (supply / "status").write_text("Discharging\n")
        self.assertEqual(sp.battery(str(where)), "75% discharging")
        self.assertEqual(sp.battery(str(self.root / "input8")), "unknown")

    def test_run_reads_no_mic_on_a_pad_without_one(self):
        mics, served = [], []

        class Stop(Exception):
            pass

        class Dev:
            uniq, path, name = "", "/dev/input/event30", "Wireless Controller"

            class info:
                vendor, product = 0x054C, 0x09CC  # a DualShock 4

            def close(self):
                pass

        def serve(dev, pad, motors, mic=None):
            served.append(mic)
            raise Stop

        voice = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, voice)
        with mock.patch.multiple(sp, find_pad=lambda path=None: Dev(), serve=serve, Motors=lambda dev, dry=False: FxLog(),
                                 profile_of=lambda dev: sp.Profile(),
                                 MicReader=lambda where: mics.append(where), input_dir=lambda dev: str(self.root),
                                 DryHypr=FakeHypr, voice_dir=lambda: voice), \
                mock.patch.object(sp.time, "sleep"), self.assertRaises(Stop):
            sp.run_daemon(True, None)
        self.assertEqual((mics, served), ([], [None]))


class UdevRule(unittest.TestCase):
    def test_the_rule_reaches_only_the_dualsense_and_reads_its_raw_node(self):
        rules = [l for l in RULE.read_text().splitlines() if l and not l.startswith("#")]
        self.assertEqual(len(rules), 3)
        for rule in rules:
            self.assertIn('KERNELS=="*:054C:0CE6.*|*:054C:0DF2.*"', rule)
            self.assertNotIn("0666", rule)
            self.assertNotIn("uaccess", rule)   # uaccess would give read AND write
        leds = [r for r in rules if 'SUBSYSTEM=="leds"' in r]
        self.assertEqual(len(leds), 2)
        for rule in leds:
            self.assertIn("chgrp input", rule)
            self.assertIn("chmod g+w", rule)
        self.assertIn('SUBSYSTEM=="hidraw"', rules[2])
        self.assertIn('GROUP="input", MODE="0640"', rules[2])   # read only

    def test_it_sorts_before_the_seat_rules_that_turn_uaccess_into_acls(self):
        self.assertLess(RULE.name, "71-seat.rules")        # tags the device for the seat
        self.assertLess(RULE.name, "73-seat-late.rules")   # turns uaccess into the ACL

    def test_it_is_installed_by_hand_not_by_the_user_service(self):
        self.assertIn("sudo install -m 0644 udev/60-hypr-gamepad.rules /etc/udev/rules.d/", RULE.read_text())
        self.assertNotIn("udev", UNIT.read_text())


class TalkTruth(TalkCase):
    """recording.state is the truth (independent review, 2026-10-29): Talk must never keep a recording
    alive that it no longer drives, nor think it records when nothing does."""

    def test_a_pad_lost_while_the_recorder_starts_leaves_nothing_for_the_next_pad_to_paste(self):
        recorder = subprocess.Popen(["sleep", "30"])
        self.addCleanup(recorder.kill)
        self.hold_r2(0.1)                     # starting: voice-flow's start is still running
        start = self.runner.procs[-1]
        came_up = []

        def start_comes_up(_seconds=0):
            if not came_up:
                (self.voice / "recording.state").write_text(f"{recorder.pid}:")
                start.code = 0
                came_up.append(True)

        self.pad.talk.sleep = start_comes_up
        self.pad.reset()                      # the pad went away (or SIGTERM): the daemon drops this Pad
        start_comes_up()                      # if nobody waited, voice-flow's start ends after the drop
        pad2 = sp.Pad(self.hypr, self.fx, self.clock, runner=self.runner, voice=self.voice)
        pad2.feed(EV_KEY, R2, 1)
        self.assertEqual(pad2.talk.state, "starting")       # a new talk, not the stop call that pastes
        self.assertEqual(recorder.wait(timeout=5), -signal.SIGTERM)   # the lost recorder was stopped

    def test_a_latched_talk_ended_elsewhere_is_let_go(self):
        self.hold_r2(0.1)
        self.key(R2, 0)                       # a tap: it keeps listening
        self.finish_start()
        (self.voice / "recording.state").unlink()   # Super+H ended it (voice-flow pasted it)
        self.pad.tick()
        self.assertEqual(self.pad.talk.state, "idle")
        self.tap(CIRCLE)                      # Circle is Esc again, not a drop
        self.assertEqual(self.sent(), [shortcut("", "Escape", "0x5606a1")])
        self.hold_r2(0.1)
        self.assertEqual(self.pad.talk.state, "starting")   # R2 starts a new talk, never a stop call

    def test_r2_right_after_it_ended_elsewhere_starts_a_new_talk(self):
        self.hold_r2(0.1)
        self.key(R2, 0)
        self.finish_start()
        (self.voice / "recording.state").unlink()
        self.hold_r2(0.1)                     # no tick in between
        self.assertEqual(self.pad.talk.state, "starting")
        self.assertTrue(self.pad.talk.held)


class Ev:
    def __init__(self, etype, code, value):
        self.type, self.code, self.value = etype, code, value


class Info:
    def __init__(self, value):
        self.value = value


class FeedDev:
    """A pad whose reads the test scripts, with the state the kernel would report after a drop."""

    def __init__(self):
        self.batches, self.keys, self.axes = [], [], {}

    def read(self):
        return self.batches.pop(0) if self.batches else []

    def active_keys(self):
        return list(self.keys)

    def absinfo(self, code):
        return Info(self.axes.get(code, 0 if code in (HAT_X, HAT_Y) else 128))


EV_SYNC, SYNC_REPORT, SYNC_DROPPED = 0x00, 0, 3


class DroppedEvents(PadCase):
    """Independent review, 2026-10-29: a release the kernel dropped (SYN_DROPPED) left a held arrow
    repeating into the window until the button was pressed again."""

    def setUp(self):
        super().setUp()
        self.hypr.active = WORKBOARD
        proc = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, proc)
        self.pad.windows = sp.Windows(self.hypr, str(proc))
        self.dev = FeedDev()
        self.reader = sp.EventReader(self.dev, self.pad)

    def test_a_release_lost_in_a_drop_stops_the_repeat(self):
        self.dev.batches = [[Ev(EV_ABS, HAT_Y, 1), Ev(EV_SYNC, SYNC_REPORT, 0)],
                            [Ev(EV_SYNC, SYNC_DROPPED, 0), Ev(EV_ABS, HAT_Y, 0), Ev(EV_SYNC, SYNC_REPORT, 0)]]
        self.reader.read()
        self.assertIn("down", self.pad.held)
        self.dev.axes[HAT_Y] = 0                 # the D-pad is up again, as the kernel now says
        self.reader.read()
        self.assertEqual(self.pad.held, {})
        self.sent()
        self.later(2.0)
        self.assertEqual(self.sent(), [])        # no Down keeps going to the window

    def test_events_between_the_drop_and_the_report_are_not_played(self):
        self.dev.batches = [[Ev(EV_SYNC, SYNC_DROPPED, 0), Ev(EV_KEY, CROSS, 1), Ev(EV_KEY, CROSS, 0), Ev(EV_SYNC, SYNC_REPORT, 0)]]
        self.reader.read()
        self.assertEqual(self.sent(), [])        # half a picture is not acted on

    def test_a_button_still_down_after_the_drop_counts_as_pressed(self):
        self.dev.keys = [CROSS]
        self.dev.batches = [[Ev(EV_SYNC, SYNC_DROPPED, 0), Ev(EV_SYNC, SYNC_REPORT, 0)]]
        self.reader.read()
        self.assertEqual(self.sent(), [shortcut("", "Return", "0x5606a1")])
        self.dev.keys = []
        self.dev.batches = [[Ev(EV_KEY, CROSS, 0), Ev(EV_SYNC, SYNC_REPORT, 0)]]
        self.reader.read()
        self.assertEqual(self.pad.buttons, set())

    def test_plain_events_play_as_before(self):
        self.dev.batches = [[Ev(EV_KEY, CROSS, 1), Ev(EV_SYNC, SYNC_REPORT, 0), Ev(EV_KEY, CROSS, 0), Ev(EV_SYNC, SYNC_REPORT, 0)]]
        self.reader.read()
        self.assertEqual(self.sent(), [shortcut("", "Return", "0x5606a1")])


class BusyGrab(unittest.TestCase):
    """Independent review, 2026-10-29: a grab another program blocked was tried and logged on every
    pass of the loop (100 a second)."""

    def setUp(self):
        self.clock, self.fx, self.dev = Clock(), FxLog(), FakeDev(fail=True)
        self.grab = sp.Grabber(self.dev, self.fx, self.clock)

    def test_a_blocked_grab_is_said_once_and_tried_each_second(self):
        tries = []
        real = self.dev.grab
        self.dev.grab = lambda: (tries.append(self.clock.now), real())
        with self.assertLogs("hypr-gamepad", "INFO") as logs:
            for _ in range(250):                 # 2.5 s of loop passes
                self.grab.sync(True)
                self.clock.now += 0.01
        self.assertEqual(len(tries), 3)          # at 0, 1 and 2 s
        self.assertEqual(len(logs.output), 1)
        self.assertEqual(len([n for n in self.fx.notes if n.startswith("Pad:")]), 1)
        self.assertFalse(self.grab.have)

    def test_the_grab_comes_back_when_the_other_program_lets_go(self):
        with self.assertLogs("hypr-gamepad", "INFO") as logs:
            self.grab.sync(True)
            self.dev.fail = False
            self.clock.now += 1.0
            self.grab.sync(True)
        self.assertTrue(self.grab.have)
        self.assertEqual(self.dev.calls, ["grab"])
        self.assertTrue(any("grabbed" in line for line in logs.output))

    def test_letting_go_is_at_once(self):
        self.dev.fail = False
        with self.assertLogs("hypr-gamepad", "INFO"):
            self.grab.sync(True)
            self.grab.sync(False)
        self.assertEqual((self.dev.calls, self.grab.have), (["grab", "ungrab"], False))



class MapGroups(PadCase):
    """Independent review, 2026-10-29: the map lit L1/R1 in any terminal and dimmed them in a grouped
    window of another kind."""

    def setUp(self):
        super().setUp()
        proc = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, proc)
        self.pad.windows = sp.Windows(self.hypr, str(proc))

    def test_the_map_is_told_whether_the_window_is_in_a_group(self):
        self.hypr.active = GROUPED
        self.key(OPTIONS, 1)
        self.assertEqual(map_events(self.sent()), ["show terminal base 1"])
        self.clock.now += 1.0                # held, not tapped: letting go hides it
        self.key(OPTIONS, 0)
        self.hypr.active = CHROMIUM
        self.key(OPTIONS, 1)
        self.assertEqual(map_events(self.sent())[-1], "show browser base 0")

    def test_tab_rows_name_the_group_not_the_terminal(self):
        rows = {r["control"]: r for r in sp.map_rows("base")}
        self.assertNotIn("terminal", rows["l1"]["kinds"])
        self.assertIn("group", rows["l1"]["kinds"])
        self.assertEqual(rows["l1"]["labels"]["group"], "Previous tab of the group")


class WakeNote(unittest.TestCase):
    """2026-10-29 s2, a virtual pad dropped and brought back under the dry daemon: a pad that woke in
    game mode said "Hold L2 for the desktop", which game mode does not do."""

    def notes(self, modes):
        """run_daemon with a pad that is served once per mode in `modes` (each serve leaves the pad in
        that mode and drops it), then a stop; the notes it gave, in order. Nothing real is touched."""
        notes, served = [], iter(modes)

        class Stop(Exception):
            pass

        class Motors(FxLog):
            def __init__(self, dev, dry=False):
                super().__init__()
                self.notes = notes

        class Dev:
            uniq, path, name = "aa:bb:cc:dd:ee:ff", "/dev/input/event258", "DualSense Wireless Controller"

            class info:
                vendor, product = 0x054C, 0x0CE6

            def close(self):
                pass

        def serve(dev, pad, motors, mic=None):
            mode = next(served, None)
            if mode is None:
                raise Stop
            pad.mode = mode
            raise OSError(19, "No such device")

        voice = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, voice)
        with mock.patch.multiple(sp, find_pad=lambda path=None: Dev(), serve=serve, Motors=Motors,
                                 profile_of=lambda dev: sp.Profile(),
                                 battery=lambda mac: "80% discharging", input_dir=lambda dev: "/nonexistent",
                                 DryHypr=FakeHypr, voice_dir=lambda: voice), \
                mock.patch.object(sp.time, "sleep"), self.assertLogs("hypr-gamepad", "INFO"), \
                self.assertRaises(Stop):
            sp.run_daemon(True, None)
        return notes

    def test_a_pad_that_wakes_at_the_desk_says_hold_l2(self):
        notes = self.notes(["desk"])
        self.assertEqual(notes, ["DualSense ready: Battery 80% discharging. Hold L2 for the desktop."] * 2)

    def test_a_pad_that_wakes_in_game_mode_says_the_way_back_not_l2(self):
        first, back = self.notes(["game"])
        self.assertEqual(first, "DualSense ready: Battery 80% discharging. Hold L2 for the desktop.")
        self.assertNotIn("L2", back)
        self.assertIn("80% discharging", back)
        self.assertIn("PS + Options", back)


class NotesInDnd(unittest.TestCase):
    """2026-10-29 s2, a user's first run: Do Not Disturb was on, and every note the pad gave (the
    agent Triangle showed, "DualSense ready") went silently into the history. The Omarchy shell shows
    the notes of its action app in Do Not Disturb (omarchy-notification-send's default app; the
    shell's notifications plugin, shouldBypassDnd): they answer something the person just did."""

    def test_a_note_goes_as_an_omarchy_action(self):
        motors = sp.Motors(None)
        with mock.patch.object(sp.subprocess, "Popen") as popen:
            motors.notify("1 of 9: Claude Code", "server - PROJECT - run waits on you")
        argv = popen.call_args.args[0]
        self.assertEqual(argv[0], "notify-send")
        self.assertEqual(argv[argv.index("-a") + 1], "omarchy-action")
        self.assertEqual(argv[-2:], ["1 of 9: Claude Code", "server - PROJECT - run waits on you"])

    def test_a_dry_note_is_printed_not_sent(self):
        motors = sp.Motors(None, dry=True)
        with mock.patch.object(sp.subprocess, "Popen") as popen, \
                mock.patch("builtins.print") as printed:
            motors.notify("Game mode", "The pad is the game's.")
        popen.assert_not_called()
        printed.assert_called_once()


class TakeBack(BaseLayer):
    """Dictation sometimes lands words that are not wanted, and the keys that clear an agent's input
    (Esc, Ctrl+C) also stop the agent. Square deletes the word before
    the cursor: Ctrl+W where the agent reads it (Claude Code 2.1.312 in a scratch session: one word a
    press, a folded "[Pasted text #1]" in one), Ctrl+Backspace where Ctrl+W would close a tab."""

    def test_square_deletes_a_word_the_way_each_window_does(self):
        for win, chord in ((WORKBOARD, ("CTRL", "w")), (LOCAL_HERDR, ("CTRL", "w")), (GROK, ("CTRL", "w")),
                           (CHROMIUM, ("CTRL", "BackSpace")), (BOARD, ("CTRL", "BackSpace")),
                           (TEAMS, ("CTRL", "BackSpace"))):
            self.focus(win)
            self.tap(SQUARE)
            self.assertEqual(self.sent(), [shortcut(*chord, win["address"])], win["title"])

    def test_it_never_sends_a_key_that_stops_the_agent(self):
        self.focus(WORKBOARD)
        self.key(SQUARE, 1)
        for _ in range(400):            # four seconds held
            self.later(0.01)
        self.key(SQUARE, 0)
        sent = self.sent()
        self.assertGreater(len(sent), 30)
        self.assertEqual({expr for _, expr in sent}, {shortcut("CTRL", "w", "0x5606a1")[1]})

    def test_held_it_keeps_deleting_faster_and_stops_when_let_go(self):
        self.focus(WORKBOARD)
        self.key(SQUARE, 1)
        self.assertEqual(len(self.sent()), 1)    # the press itself deletes a word at once
        times = []
        for _ in range(300):
            self.later(0.01)
            times += [self.clock.now] * len(self.sent())
        self.key(SQUARE, 0)
        gaps = [b - a for a, b in zip(times, times[1:])]
        self.assertAlmostEqual(times[0] - 1000.0, 0.40, delta=0.011)   # the first repeat
        self.assertAlmostEqual(gaps[0], 0.12, delta=0.011)
        self.assertAlmostEqual(gaps[-1], 0.06, delta=0.011)              # full speed after 1.5 s more
        for _ in range(50):
            self.later(0.01)
        self.assertEqual(self.sent(), [])

    def test_the_repeat_speeds_up_only_where_it_says(self):
        self.assertEqual(sp.repeat_gap("slow", 0.45), 0.22)
        self.assertEqual(sp.repeat_gap("slow", 9.0), 0.22)
        self.assertAlmostEqual(sp.repeat_gap("words", 0.40), 0.12)
        self.assertAlmostEqual(sp.repeat_gap("words", 1.15), 0.09)
        self.assertAlmostEqual(sp.repeat_gap("words", 1.90), 0.06)
        self.assertAlmostEqual(sp.repeat_gap("words", 9.0), 0.06)


class TextSize(ScrollCase):
    """Text size in the focused window, from the pad. L2 held: the right stick up is bigger text, down smaller (Ctrl+= / Ctrl+-, foot's
    and the browsers' keys), held it repeats; R3 is normal size in either layer."""

    ADDR = "0x5606a1"

    def test_l2_and_the_right_stick_size_the_text_and_never_scroll(self):
        self.key(L2, 1)
        self.tilt(128, 0, 0.1)
        self.tilt(128, 128, 0.1)
        self.tilt(128, 255, 0.1)
        self.tilt(128, 128, 0.1)
        self.assertEqual(self.sent(), [shortcut("CTRL", "equal", self.ADDR), shortcut("CTRL", "minus", self.ADDR)])
        self.assertEqual(self.wheel.events, [])

    def test_held_up_it_keeps_growing(self):
        self.key(L2, 1)
        self.tilt(128, 0, 1.0)      # the first at once, then at 0.45 s and every 0.22 s
        self.assertEqual(self.sent(), [shortcut("CTRL", "equal", self.ADDR)] * 4)

    def test_letting_go_of_l2_stops_the_growing_and_does_not_scroll(self):
        self.key(L2, 1)
        self.tilt(128, 0, 0.6)
        self.key(L2, 0)
        self.sent()
        self.tilt(128, 0, 1.0)      # the stick still up: no more size, no scroll until it rests
        self.assertEqual((self.sent(), self.wheel.events), ([], []))
        self.tilt(128, 128, 0.05)
        self.tilt(128, 0, 0.2)
        self.assertGreater(self.wheel.totals()[0], 0)   # rested, then up: it scrolls up again

    def test_a_scroll_held_when_l2_goes_down_sizes_nothing_until_the_stick_rests(self):
        self.tilt(128, 0, 0.2)       # scrolling up
        self.wheel.events.clear()
        self.key(L2, 1)
        self.tilt(128, 0, 1.0)
        self.assertEqual(self.sent(), [])
        self.assertEqual([e for e in self.wheel.events if any(e)], [])   # and the scroll stopped
        self.tilt(128, 128, 0.05)
        self.tilt(128, 0, 0.05)
        self.assertEqual(self.sent(), [shortcut("CTRL", "equal", self.ADDR)])

    def test_after_l2_a_resting_stick_scrolls_at_the_first_push(self):
        self.key(L2, 1)
        self.key(L2, 0)
        self.tilt(128, 0, 0.2)
        self.assertGreater(self.wheel.totals()[0], 0)

    def test_r3_is_normal_size_on_both_sides(self):
        self.tap(R3)
        self.key(L2, 1)
        self.tap(R3)
        self.assertEqual(self.sent(), [shortcut("CTRL", "0", self.ADDR)] * 2)

    def test_a_pad_that_goes_away_mid_size_lets_go(self):
        self.key(L2, 1)
        self.tilt(128, 0, 0.1)
        self.pad.reset()
        self.sent()
        for _ in range(100):
            self.later(0.01)
        self.assertEqual(self.sent(), [])


def column_monitors(focused):
    """A test machine's screens, 2026-10-29 (hyprctl monitors -j): a column. DP-1 on top, the
    laptop's eDP-2 in the middle, HDMI-A-1 below; no screen stands beside another."""
    mons = [
        {"id": 0, "name": "eDP-2", "x": 2883, "y": 360, "width": 2560, "height": 1600, "scale": 2.0, "transform": 0},
        {"id": 1, "name": "DP-1", "x": 1707, "y": -661, "width": 5120, "height": 1440, "scale": 1.41, "transform": 0},
        {"id": 2, "name": "HDMI-A-1", "x": 2669, "y": 1160, "width": 2560, "height": 1600, "scale": 1.5, "transform": 0},
    ]
    for m in mons:
        m["focused"] = m["name"] == focused
    return mons


def focus_monitor(name):
    return f'hl.dsp.focus({{ monitor = "{name}" }})'


class Screens(PadCase):
    """A user's first run, 2026-10-29 15:36: L2 + the left stick sent hl.dsp.focus({ monitor = "l" })
    and Hyprland answered "monitor not found", 11 times. Its direction lookup takes only a screen whose
    edge touches that side (MonitorQueryCore::directionLookup, v0.56.2), and these screens stand in a
    column: nothing is ever left or right, nothing is above the top one."""

    def walk(self, start, axis, value):
        self.hypr.monitors = column_monitors(start)
        self.key(L2, 1)
        before = len(self.fx.rumbles)
        self.abs(axis, value)
        self.abs(axis, 128)
        self.key(L2, 0)
        return [e for _, e in self.sent()], self.fx.rumbles[before:]

    def test_up_and_down_walk_the_column(self):
        self.assertEqual(self.walk("eDP-2", LY, 0)[0], [focus_monitor("DP-1")])
        self.assertEqual(self.walk("eDP-2", LY, 255)[0], [focus_monitor("HDMI-A-1")])
        self.assertEqual(self.walk("HDMI-A-1", LY, 0)[0], [focus_monitor("eDP-2")])
        self.assertEqual(self.walk("DP-1", LY, 255)[0], [focus_monitor("eDP-2")])

    def test_with_no_screen_beside_left_and_right_go_to_the_one_before_and_after(self):
        self.assertEqual(self.walk("eDP-2", LX, 0)[0], [focus_monitor("DP-1")])
        self.assertEqual(self.walk("eDP-2", LX, 255)[0], [focus_monitor("HDMI-A-1")])
        self.assertEqual(self.walk("DP-1", LX, 0)[0], [focus_monitor("HDMI-A-1")])      # round
        self.assertEqual(self.walk("HDMI-A-1", LX, 255)[0], [focus_monitor("DP-1")])

    def test_past_the_top_or_the_bottom_nothing_moves_and_the_hand_feels_it(self):
        self.assertEqual(self.walk("DP-1", LY, 0), ([], ["tick"]))
        self.assertEqual(self.walk("HDMI-A-1", LY, 255), ([], ["tick"]))

    def test_screens_side_by_side_go_by_where_they_stand(self):
        mons = [{"name": "A", "x": 0, "y": 0, "width": 1920, "height": 1080, "scale": 1, "focused": True},
                {"name": "B", "x": 1920, "y": 0, "width": 2560, "height": 1440, "scale": 1.25},
                {"name": "C", "x": 0, "y": 1080, "width": 1080, "height": 1920, "scale": 1, "transform": 1}]
        self.assertEqual(sp.screen_toward(mons, "right"), "B")
        self.assertEqual(sp.screen_toward(mons, "down"), "C")       # rotated: 1920 wide, 1080 high
        self.assertEqual(sp.screen_toward(mons, "up"), None)
        self.assertIsNone(sp.screen_toward(None, "left"))
        self.assertIsNone(sp.screen_toward([{"name": "A", "focused": False}], "left"))
