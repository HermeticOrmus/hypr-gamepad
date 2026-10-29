"""Any gamepad, not only the DualSense: found by what it reports, and read by its own ranges.

The shapes are the kernel drivers' (torvalds/linux master, read 2026-10-29):
- hid-playstation (DualSense): sticks and triggers 0..255, digital L2/R2 beside them, the D-pad a hat.
- xpad (Xbox 360 / One and the many pads it drives): sticks -32768..32767, triggers ABS_Z / ABS_RZ
  0..255 (360) or 0..1023 (One) with no trigger buttons, the D-pad a hat, and X sent as BTN_X
  (= BTN_NORTH) though X sits west, Y as BTN_Y (= BTN_WEST) though Y sits north.
- an Xbox pad over Bluetooth (hid-generic): the right stick on ABS_Z / ABS_RZ, the triggers on
  ABS_BRAKE / ABS_GAS.
- hid-nintendo (Pro Controller): positional face buttons, sticks -32767..32767, digital ZL/ZR,
  Capture as BTN_Z; the D-pad a hat, or BTN_DPAD_* on older kernels.

Hyprland is a stub here, never the real one.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "hypr-gamepad"

loader = importlib.machinery.SourceFileLoader("hypr_gamepad_pads", str(SCRIPT))
hg = importlib.util.module_from_spec(importlib.util.spec_from_loader("hypr_gamepad_pads", loader))
sys.modules["hypr_gamepad_pads"] = hg  # dataclasses look their module up while the file loads
loader.exec_module(hg)

EV_KEY, EV_ABS = 0x01, 0x03
BTN_SOUTH, BTN_EAST, BTN_C, BTN_NORTH, BTN_WEST, BTN_Z = 0x130, 0x131, 0x132, 0x133, 0x134, 0x135
BTN_TL, BTN_TR, BTN_TL2, BTN_TR2 = 0x136, 0x137, 0x138, 0x139
BTN_SELECT, BTN_START, BTN_MODE, BTN_THUMBL, BTN_THUMBR = 0x13A, 0x13B, 0x13C, 0x13D, 0x13E
BTN_DPAD_UP, BTN_DPAD_DOWN, BTN_DPAD_LEFT, BTN_DPAD_RIGHT = 0x220, 0x221, 0x222, 0x223
KEY_RECORD = 0xA7
ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ = 0x00, 0x01, 0x02, 0x03, 0x04, 0x05
ABS_GAS, ABS_BRAKE, ABS_HAT0X, ABS_HAT0Y = 0x09, 0x0A, 0x10, 0x11

COMMON = {BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST, BTN_TL, BTN_TR, BTN_SELECT, BTN_START, BTN_MODE,
          BTN_THUMBL, BTN_THUMBR}
HAT = {ABS_HAT0X: (-1, 1), ABS_HAT0Y: (-1, 1)}
DUALSENSE = dict(name="DualSense Wireless Controller", vendor=0x054C, product=0x0CE6, driver="playstation",
                 keys=COMMON | {BTN_TL2, BTN_TR2},
                 absinfo={**{code: (0, 255) for code in (ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ)}, **HAT})
XBOX_360 = dict(name="Microsoft X-Box 360 pad", vendor=0x045E, product=0x028E, driver="xpad", keys=COMMON,
                absinfo={**{code: (-32768, 32767) for code in (ABS_X, ABS_Y, ABS_RX, ABS_RY)},
                         ABS_Z: (0, 255), ABS_RZ: (0, 255), **HAT})
XBOX_ONE = dict(XBOX_360, name="Microsoft X-Box One pad", product=0x02EA, keys=COMMON | {KEY_RECORD},
                absinfo={**XBOX_360["absinfo"], ABS_Z: (0, 1023), ABS_RZ: (0, 1023)})
THIRD_PARTY_XPAD = dict(XBOX_360, name="PowerA Xbox Series X Controller", vendor=0x20D6, product=0x2001)
XBOX_BLUETOOTH = dict(name="Xbox Wireless Controller", vendor=0x045E, product=0x0B13, driver="hid-generic",
                      keys=COMMON | {BTN_C},
                      absinfo={**{code: (0, 65535) for code in (ABS_X, ABS_Y, ABS_Z, ABS_RZ)},
                               ABS_BRAKE: (0, 1023), ABS_GAS: (0, 1023), **HAT})
PRO = dict(name="Nintendo Switch Pro Controller", vendor=0x057E, product=0x2009, driver="nintendo",
           keys=COMMON | {BTN_TL2, BTN_TR2, BTN_Z},
           absinfo={**{code: (-32767, 32767) for code in (ABS_X, ABS_Y, ABS_RX, ABS_RY)}, **HAT})
PRO_OLD_KERNEL = dict(PRO, keys=PRO["keys"] | {BTN_DPAD_UP, BTN_DPAD_DOWN, BTN_DPAD_LEFT, BTN_DPAD_RIGHT},
                      absinfo={code: (-32767, 32767) for code in (ABS_X, ABS_Y, ABS_RX, ABS_RY)})
NO_HOME = dict(name="USB Gamepad", vendor=0x0079, product=0x0011, driver="hid-generic",
               keys={BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST, BTN_TL, BTN_TR, BTN_TL2, BTN_TR2, BTN_SELECT,
                     BTN_START},
               absinfo={ABS_X: (0, 255), ABS_Y: (0, 255), **HAT})

FULLSCREEN = 'hl.dsp.window.fullscreen({ mode = "fullscreen" })'
NEXT_WINDOW = "hl.dsp.window.cycle_next()"
SCRATCHPAD = 'hl.dsp.workspace.toggle_special("scratchpad")'
FOCUS_UP = 'hl.dsp.focus({ direction = "u" })'


class Hypr:
    def __init__(self):
        self.sent: list[str] = []

    def dispatch(self, expr):
        self.sent.append(expr)
        return True

    def eval(self, lua):
        self.sent.append(lua)
        return True

    def json(self, what):
        return None


class Fx(hg.Fx):
    def __init__(self):
        self.notes: list[str] = []

    def notify(self, title, body=""):
        self.notes.append(f"{title}: {body}")


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def profile(shape: dict, family: str = "") -> "hg.Profile":
    return hg.profile_for(shape["name"], shape["vendor"], shape["product"], shape["driver"], shape["keys"],
                          shape["absinfo"], family)


class PadCase(unittest.TestCase):
    def setUp(self):
        saved = hg.CONFIG
        self.addCleanup(setattr, hg, "CONFIG", saved)
        hg.CONFIG = hg.Config()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def pad(self, shape: dict, family: str = "") -> "hg.Pad":
        self.hypr, self.fx, self.clock = Hypr(), Fx(), Clock()
        procs = self.tmp / "proc"
        procs.mkdir(exist_ok=True)
        return hg.Pad(self.hypr, self.fx, self.clock, windows=hg.Windows(self.hypr, str(procs)),
                      voice=self.tmp, profile=profile(shape, family))

    def sent(self) -> list[str]:
        out, self.hypr.sent = self.hypr.sent, []
        return out

    def key(self, pad, code: int, seconds: float = 0.05) -> None:
        pad.feed(EV_KEY, code, 1)
        self.clock.now += seconds
        pad.feed(EV_KEY, code, 0)


class Finding(unittest.TestCase):
    """A gamepad is what the kernel's gamepad spec says every gamepad reports: BTN_SOUTH, with a left
    stick. That leaves out what a desk also carries."""

    def test_pads_are_gamepads(self):
        for shape in (DUALSENSE, XBOX_360, XBOX_BLUETOOTH, PRO, PRO_OLD_KERNEL, NO_HOME):
            self.assertTrue(hg.is_gamepad(shape["keys"], set(shape["absinfo"])), shape["name"])

    def test_what_else_a_desk_carries_is_not(self):
        motion = set(range(ABS_X, ABS_RZ + 1))                         # a DualSense's Motion Sensors
        self.assertFalse(hg.is_gamepad(set(), motion))
        self.assertFalse(hg.is_gamepad({0x110, 0x145, 0x14A}, {ABS_X, ABS_Y}))  # its touchpad
        self.assertFalse(hg.is_gamepad(set(range(1, 0x2FF)), set()))  # a virtual keyboard with every key
        self.assertFalse(hg.is_gamepad({0x71, 0x72, 0x73}, {0x28}))   # a keyboard's media keys

    def test_the_first_gamepad_by_event_number_is_the_pad(self):
        devices = [("/dev/input/event10", "Logitech USB Receiver", False),
                   ("/dev/input/event259", "DualSense Wireless Controller Motion Sensors", False),
                   ("/dev/input/event258", "DualSense Wireless Controller", True),
                   ("/dev/input/event9", "Xbox Wireless Controller", True)]
        self.assertEqual(hg.pick_pad(devices, ""), "/dev/input/event9")

    def test_a_name_picks_the_pad_and_prefers_a_gamepad_among_its_matches(self):
        devices = [("/dev/input/event9", "Xbox Wireless Controller", True),
                   ("/dev/input/event259", "DualSense Wireless Controller Motion Sensors", False),
                   ("/dev/input/event258", "DualSense Wireless Controller", True)]
        self.assertEqual(hg.pick_pad(devices, "DualSense"), "/dev/input/event258")

    def test_a_name_may_pick_a_device_the_kernel_does_not_call_a_gamepad(self):
        devices = [("/dev/input/event5", "DragonRise Inc. Generic USB Joystick", False),
                   ("/dev/input/event9", "Xbox Wireless Controller", True)]
        self.assertEqual(hg.pick_pad(devices, "Generic USB Joystick"), "/dev/input/event5")

    def test_no_pad_is_none(self):
        self.assertIsNone(hg.pick_pad([("/dev/input/event10", "Logitech USB Receiver", False)], ""))
        self.assertIsNone(hg.pick_pad([("/dev/input/event9", "Xbox Wireless Controller", True)], "DualSense"))

    def test_the_driver_is_read_from_sysfs_and_a_virtual_device_has_none(self):
        sysfs = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, sysfs)
        drivers = sysfs / "bus" / "hid" / "drivers" / "playstation"
        drivers.mkdir(parents=True)
        device = sysfs / "class" / "input" / "event258" / "device" / "device"
        device.mkdir(parents=True)
        (device / "driver").symlink_to(drivers)
        self.assertEqual(hg.driver_of("/dev/input/event258", str(sysfs)), "playstation")
        self.assertEqual(hg.driver_of("/dev/input/event300", str(sysfs)), "")


class Profiles(unittest.TestCase):
    def test_a_real_dualsense_reads_as_it_always_did(self):
        """The default Profile is what the tests and the old pad assume; a DualSense as the kernel
        reports it must be read the same way."""
        found, default = profile(DUALSENSE), hg.Profile()
        self.assertEqual((found.family, found.buttons, found.axes, found.chord),
                         (default.family, default.buttons, default.axes, default.chord))

    def test_xpad_sends_x_and_y_by_their_labels_so_they_swap_back(self):
        for shape in (XBOX_360, THIRD_PARTY_XPAD):
            found = profile(shape)
            self.assertEqual(found.family, "xbox", shape["name"])
            self.assertEqual((found.buttons[BTN_NORTH], found.buttons[BTN_WEST]), ("west", "north"))
            self.assertEqual(found.buttons[BTN_SOUTH], "south")

    def test_family_comes_from_the_driver_then_the_maker(self):
        self.assertEqual(profile(PRO).family, "nintendo")
        self.assertEqual(profile(XBOX_BLUETOOTH).family, "xbox")       # hid-generic, Microsoft's id
        self.assertEqual(profile(NO_HOME).family, "generic")
        self.assertEqual(profile(NO_HOME, family="nintendo").family, "nintendo")

    def test_xpad_triggers_are_axes(self):
        found = profile(XBOX_ONE)
        self.assertEqual((found.axes[ABS_Z].role, found.axes[ABS_RZ].role), ("l2", "r2"))
        self.assertEqual((found.axes[ABS_RZ].low, found.axes[ABS_RZ].high), (0, 1023))
        self.assertEqual(found.buttons[KEY_RECORD], "capture")

    def test_a_bluetooth_xbox_pad_has_its_right_stick_on_z_and_its_triggers_on_brake_and_gas(self):
        found = profile(XBOX_BLUETOOTH)
        roles = {code: axis.role for code, axis in found.axes.items()}
        self.assertEqual(roles, {ABS_X: "lx", ABS_Y: "ly", ABS_Z: "rx", ABS_RZ: "ry", ABS_BRAKE: "l2",
                                 ABS_GAS: "r2", ABS_HAT0X: "hatx", ABS_HAT0Y: "haty"})

    def test_a_pad_with_trigger_buttons_reads_no_trigger_axis(self):
        for shape in (DUALSENSE, PRO):
            roles = {axis.role for axis in profile(shape).axes.values()}
            self.assertNotIn("l2", roles, shape["name"])
            self.assertNotIn("r2", roles, shape["name"])

    def test_nintendo_capture(self):
        self.assertEqual(profile(PRO).buttons[BTN_Z], "capture")
        self.assertNotIn(BTN_Z, profile(dict(PRO, driver="hid-generic", vendor=0x1234)).buttons)

    def test_the_d_pad_is_the_hat_or_else_its_buttons(self):
        old = profile(PRO_OLD_KERNEL)
        self.assertEqual([old.buttons[c] for c in (BTN_DPAD_UP, BTN_DPAD_DOWN, BTN_DPAD_LEFT, BTN_DPAD_RIGHT)],
                         ["up", "down", "left", "right"])
        both = profile(dict(PRO, keys=PRO_OLD_KERNEL["keys"]))         # hat and buttons: the hat only
        self.assertNotIn(BTN_DPAD_UP, both.buttons)
        self.assertEqual(both.axes[ABS_HAT0Y].role, "haty")

    def test_game_mode_is_home_and_start_or_select_and_start_without_home(self):
        self.assertEqual(profile(XBOX_360).chord, frozenset({"home", "start"}))
        self.assertEqual(profile(NO_HOME).chord, frozenset({"select", "start"}))


class Scaling(unittest.TestCase):
    def test_a_stick_is_scaled_from_its_own_range(self):
        dualsense, xpad, pro, bluetooth = (hg.Axis("lx", 0, 255), hg.Axis("lx", -32768, 32767),
                                           hg.Axis("lx", -32767, 32767), hg.Axis("lx", 0, 65535))
        for value in (0, 1, 64, 127, 128, 129, 200, 255):
            self.assertEqual(dualsense.tilt(value), max(-1.0, min(1.0, (value - 128) / 127)))  # as before
        self.assertEqual([xpad.tilt(v) for v in (-32768, 0, 32767)], [-1.0, 0.0, 1.0])
        self.assertEqual([pro.tilt(v) for v in (-32767, 0, 32767)], [-1.0, 0.0, 1.0])
        self.assertEqual([bluetooth.tilt(v) for v in (0, 32768, 65535)], [-1.0, 0.0, 1.0])

    def test_a_trigger_is_scaled_from_its_own_range(self):
        self.assertEqual([hg.Axis("r2", 0, 1023).travel(v) for v in (0, 1023)], [0.0, 1.0])
        self.assertAlmostEqual(hg.Axis("r2", 0, 255).travel(51), 0.2)


class Reading(PadCase):
    def test_an_xbox_trigger_axis_holds_the_desktop_side(self):
        pad = self.pad(XBOX_360)
        pad.feed(EV_ABS, ABS_Z, 200)                                   # LT most of the way
        self.key(pad, BTN_SOUTH)
        self.assertEqual(self.sent(), [FULLSCREEN])
        pad.feed(EV_ABS, ABS_Z, 0)
        self.key(pad, BTN_SOUTH)
        self.assertEqual(self.sent(), [])                              # Enter, to no window

    def test_a_trigger_axis_presses_past_half_and_lets_go_under_a_third(self):
        pad = self.pad(XBOX_ONE)
        for value, world in ((400, False), (520, True), (400, True), (320, True), (300, False), (0, False)):
            pad.feed(EV_ABS, ABS_Z, value)
            self.assertEqual(pad.world, world, value)

    def test_xbox_x_and_y_do_what_sits_west_and_north(self):
        pad = self.pad(XBOX_360)
        pad.feed(EV_ABS, ABS_Z, 255)
        self.key(pad, BTN_NORTH)                                       # X: west, the next window
        self.key(pad, BTN_WEST)                                        # Y: north, the scratchpad
        self.assertEqual(self.sent(), [NEXT_WINDOW, SCRATCHPAD])

    def test_sticks_read_their_own_range(self):
        pad = self.pad(XBOX_360)
        pad.feed(EV_ABS, ABS_X, 32767)
        pad.feed(EV_ABS, ABS_Y, -32768)
        self.assertEqual(pad.stick["left"], [1.0, -1.0])
        bluetooth = self.pad(XBOX_BLUETOOTH)
        bluetooth.feed(EV_ABS, ABS_Z, 65535)                           # the right stick, over Bluetooth
        self.assertEqual(bluetooth.stick["right"], [1.0, 0.0])
        bluetooth.feed(EV_ABS, ABS_BRAKE, 1023)
        self.assertTrue(bluetooth.world)

    def test_the_d_pad_from_buttons(self):
        pad = self.pad(PRO_OLD_KERNEL)
        pad.feed(EV_KEY, BTN_TL2, 1)                                   # ZL: the desktop side
        self.key(pad, BTN_DPAD_UP)
        self.assertEqual(self.sent(), [FOCUS_UP])

    def test_a_pad_with_hat_and_d_pad_buttons_moves_once(self):
        pad = self.pad(dict(PRO, keys=PRO_OLD_KERNEL["keys"]))
        pad.feed(EV_KEY, BTN_TL2, 1)
        pad.feed(EV_KEY, BTN_DPAD_UP, 1)
        pad.feed(EV_ABS, ABS_HAT0Y, -1)
        self.assertEqual(self.sent(), [FOCUS_UP])

    def test_select_and_start_toggle_game_mode_on_a_pad_without_home(self):
        pad = self.pad(NO_HOME)
        pad.feed(EV_KEY, BTN_SELECT, 1)
        pad.feed(EV_KEY, BTN_START, 1)
        self.assertEqual(pad.mode, "game")

    def test_a_trigger_in_game_mode_does_nothing_and_is_where_it_is_on_the_way_back(self):
        pad = self.pad(XBOX_360)
        pad.toggle_mode()
        pad.feed(EV_ABS, ABS_Z, 255)
        self.assertFalse(pad.world)
        pad.toggle_mode()
        pad.feed(EV_ABS, ABS_Z, 250)                                   # still held: not a new press
        self.assertFalse(pad.world)
        pad.feed(EV_ABS, ABS_Z, 0)
        pad.feed(EV_ABS, ABS_Z, 255)
        self.assertTrue(pad.world)

    def test_a_lost_pad_forgets_its_triggers(self):
        pad = self.pad(XBOX_360)
        pad.feed(EV_ABS, ABS_Z, 255)
        pad.reset()
        self.assertFalse(pad.world)
        pad.feed(EV_ABS, ABS_Z, 255)
        self.assertTrue(pad.world)


class DeviceConfig(unittest.TestCase):
    def test_the_device_table(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        path = tmp / "config.toml"
        path.write_text('[device]\nname = "Pro Controller"\nfamily = "nintendo"\n')
        config = hg.load_config(path)
        self.assertEqual((config.device.name, config.device.family), ("Pro Controller", "nintendo"))
        path.write_text('[device]\nfamily = "sega"\n')
        with self.assertRaises(hg.ConfigError) as caught:
            hg.load_config(path)
        self.assertIn("device.family", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
