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


def sysfs_device(root: Path, event: str, name: str, vendor: int, product: int, key: str, abs_: str,
                 driver: str = "") -> None:
    """One input device as /sys/class/input/<event>/device shows it."""
    base = root / "class" / "input" / event / "device"
    (base / "capabilities").mkdir(parents=True)
    (base / "id").mkdir()
    (base / "name").write_text(name + "\n")
    (base / "id" / "vendor").write_text(f"{vendor:04x}\n")
    (base / "id" / "product").write_text(f"{product:04x}\n")
    (base / "capabilities" / "key").write_text(key + "\n")
    (base / "capabilities" / "abs").write_text(abs_ + "\n")
    if driver:
        drivers = root / "bus" / "hid" / "drivers" / driver
        drivers.mkdir(parents=True, exist_ok=True)
        (base / "device").mkdir()
        (base / "device" / "driver").symlink_to(drivers)


class Sysfs(unittest.TestCase):
    """The pad is found from sysfs, where every device's name and capabilities are plain files: opening
    a device to look at it costs a wait in close() (the kernel's evdev_release; 43 devices took 645 ms on
    a test machine), and a sleeping pad was looked for each second."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)

    def test_a_capability_bitmap_is_read_as_codes(self):
        keys = hg.bitmap("7fdb000000000000 0 0 0 0")                  # a DualSense, as sysfs shows it
        self.assertEqual(keys, set(hg.BUTTONS))
        self.assertEqual(hg.bitmap("3003f"), {ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ, ABS_HAT0X, ABS_HAT0Y})
        self.assertEqual(hg.bitmap("0"), set())

    def test_the_desk_is_read_from_sysfs(self):
        sysfs_device(self.root, "event10", "Logitech USB Receiver", 0x046D, 0xC548, "1f0000 0 0 0 0", "3")
        sysfs_device(self.root, "event256", "ydotoold virtual device", 0x2333, 0x6666,
                     "ffffffffffffffff ffffffffffffffff ffffffffffffffff ffffffffffffffff ffffffffffffffff", "0")
        sysfs_device(self.root, "event259", "DualSense Wireless Controller Motion Sensors", 0x054C, 0x0CE6, "0", "3f")
        sysfs_device(self.root, "event258", "DualSense Wireless Controller", 0x054C, 0x0CE6,
                     "7fdb000000000000 0 0 0 0", "3003f", driver="playstation")
        devices = hg.scan(str(self.root))
        self.assertEqual([(d.path, d.gamepad) for d in devices],
                         [("/dev/input/event10", False), ("/dev/input/event256", False),
                          ("/dev/input/event258", True), ("/dev/input/event259", False)])
        pad = devices[2]
        self.assertEqual((pad.name, pad.vendor, pad.product, pad.driver),
                         ("DualSense Wireless Controller", 0x054C, 0x0CE6, "playstation"))
        names = hg.scan_profile(pad)
        self.assertEqual((names.family, names.chord), ("playstation", frozenset({"home", "start"})))

    def test_a_device_that_went_away_mid_scan_is_left_out(self):
        sysfs_device(self.root, "event258", "DualSense Wireless Controller", 0x054C, 0x0CE6,
                     "7fdb000000000000 0 0 0 0", "3003f")
        (self.root / "class" / "input" / "event300").mkdir(parents=True)  # no device under it any more
        self.assertEqual([d.path for d in hg.scan(str(self.root))], ["/dev/input/event258"])

    def test_finding_the_pad_opens_the_pad_alone(self):
        sysfs_device(self.root, "event10", "Logitech USB Receiver", 0x046D, 0xC548, "1f0000 0 0 0 0", "3")
        sysfs_device(self.root, "event258", "DualSense Wireless Controller", 0x054C, 0x0CE6,
                     "7fdb000000000000 0 0 0 0", "3003f")
        opened = []

        class Evdev:
            @staticmethod
            def InputDevice(path):
                opened.append(path)
                return path

        from unittest import mock
        with mock.patch.dict(sys.modules, {"evdev": Evdev}):
            self.assertEqual(hg.find_pad(sysfs=str(self.root)), "/dev/input/event258")
            self.assertEqual(opened, ["/dev/input/event258"])
            opened.clear()
            self.assertEqual(hg.find_pad("/dev/input/event258", sysfs=str(self.root)), "/dev/input/event258")
            self.assertIsNone(hg.find_pad("/dev/input/event10", sysfs=str(self.root)))  # not a gamepad
            self.assertEqual(opened, ["/dev/input/event258"])

    def test_a_pad_that_will_not_open_gives_way_to_the_next(self):
        sysfs_device(self.root, "event5", "Xbox Wireless Controller", 0x045E, 0x0B13, "7fdb000000000000 0 0 0 0", "3")
        sysfs_device(self.root, "event258", "DualSense Wireless Controller", 0x054C, 0x0CE6,
                     "7fdb000000000000 0 0 0 0", "3003f")

        class Evdev:
            @staticmethod
            def InputDevice(path):
                if path.endswith("event5"):
                    raise PermissionError(13, "Permission denied")
                return path

        from unittest import mock
        with mock.patch.dict(sys.modules, {"evdev": Evdev}):
            self.assertEqual(hg.find_pad(sysfs=str(self.root)), "/dev/input/event258")


class NamedDevices(unittest.TestCase):
    """A device named on purpose (--device, [device] name) may be a pad the kernel does not call a
    gamepad: joystick buttons and a stick. Never a keyboard, a mouse or a touchpad: an event number can
    change after a reboot, and a grabbed keyboard leaves the desk without one."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        sysfs_device(self.root, "event5", "DragonRise Inc. Generic USB Joystick", 0x0079, 0x0006,
                     "fff00000000 0 0 0 0", "30027")                    # BTN_TRIGGER .. BTN_BASE6; X Y Z RZ hat
        sysfs_device(self.root, "event6", "Some Keyboard", 0x1234, 0x0001, "ffffffffffffffff fffffffffffffffe", "0")
        sysfs_device(self.root, "event7", "ELAN Touchpad", 0x04F3, 0x32EE, "6420 30000 0 0 0 0", "3")
        sysfs_device(self.root, "event8", "Logitech USB Receiver", 0x046D, 0xC548, "1f0000 0 0 0 0", "3")

    def find(self, path=None, name=""):
        class Evdev:
            @staticmethod
            def InputDevice(found):
                return found

        from unittest import mock
        saved = hg.CONFIG
        self.addCleanup(setattr, hg, "CONFIG", saved)
        hg.CONFIG = hg.Config(device=hg.DeviceConfig(name=name))
        with mock.patch.dict(sys.modules, {"evdev": Evdev}):
            return hg.find_pad(path, sysfs=str(self.root))

    def test_a_joystick_is_not_found_by_itself(self):
        self.assertIsNone(self.find())

    def test_a_joystick_named_by_node_or_name_is_the_pad(self):
        self.assertEqual(self.find("/dev/input/event5"), "/dev/input/event5")
        self.assertEqual(self.find(name="Generic USB Joystick"), "/dev/input/event5")

    def test_a_keyboard_a_touchpad_or_a_mouse_never_is(self):
        for event in ("event6", "event7", "event8"):
            self.assertIsNone(self.find(f"/dev/input/{event}"), event)
        self.assertIsNone(self.find(name="Keyboard"))
        self.assertIsNone(self.find(name="Touchpad"))


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


class Names(PadCase):
    """Each family's own names, on the map and in the notes: what is printed on the pad in the hand."""

    def test_each_family_names_its_controls(self):
        controls = ("south", "east", "west", "north", "l1", "r1", "l2", "r2", "l3", "r3", "select", "start",
                    "home", "capture")
        for shape, names in ((XBOX_ONE, ["A", "B", "X", "Y", "LB", "RB", "LT", "RT", "LS", "RS", "View", "Menu",
                                         "Xbox", "Share"]),
                             (PRO, ["B", "A", "Y", "X", "L", "R", "ZL", "ZR", "LS", "RS", "Minus", "Plus",
                                    "Home", "Capture"]),
                             (NO_HOME, ["South", "East", "West", "North", "L1", "R1", "L2", "R2", "L3", "R3",
                                        "Select", "Start", "Home", "Capture"]),
                             (DUALSENSE, ["Cross", "Circle", "Square", "Triangle", "L1", "R1", "L2", "R2", "L3",
                                          "R3", "Create", "Options", "PS", "Capture"])):
            found = profile(shape)
            self.assertEqual([found.name_of(c) for c in controls], names, shape["name"])
        self.assertEqual(profile(dict(DUALSENSE, product=0x09CC)).name_of("select"), "Share")  # a DualShock 4
        self.assertEqual(profile(DUALSENSE).name_of("ls_up"), "Left stick up")

    def test_the_chord_is_named_as_the_pad_names_it(self):
        self.assertEqual(profile(DUALSENSE).chord_name(), "PS + Options")
        self.assertEqual(profile(XBOX_360).chord_name(), "Xbox + Menu")
        self.assertEqual(profile(NO_HOME).chord_name(), "Select + Start")

    def test_the_map_shows_the_pads_names(self):
        xbox = profile(XBOX_360)
        rows = {r["control"]: r for r in hg.map_rows("base", xbox)}
        self.assertEqual([(rows[c]["glyph"], rows[c]["name"]) for c in ("south", "west", "north")],
                         [("", "A"), ("", "X"), ("", "Y")])
        self.assertEqual(rows["l1"]["name"], "LB")
        world = {r["control"]: r for r in hg.map_rows("world", xbox)}
        self.assertEqual(world["chord"]["name"], "Xbox + Menu")
        self.assertEqual(hg.layer_names(xbox)["world"], "LT held: the desktop")
        ds = {r["control"]: r for r in hg.map_rows("base", hg.Profile())}
        self.assertEqual((ds["south"]["glyph"], ds["south"]["name"]), ("\u2715", "Cross"))
        self.assertEqual(hg.layer_names(hg.Profile())["world"], "L2 held: the desktop")

    def test_notes_name_the_pressed_control_as_the_pad_does(self):
        pad = self.pad(XBOX_360)
        self.key(pad, BTN_WEST)                                        # Y: north, the jump; no herdr window
        self.key(pad, BTN_SELECT)                                      # View: ideas, not set up
        pad.feed(EV_KEY, BTN_MODE, 1)
        pad.feed(EV_KEY, BTN_START, 1)                                 # Xbox + Menu: game mode
        self.assertEqual(self.fx.notes, ["Y jumps inside herdr: ", "View is not set up: see [ideas] in the config",
                                         "Game mode: The pad is the game's. Xbox + Menu brings it back."])

    def test_the_map_command_names_a_family_on_request(self):
        import json
        import subprocess
        proc = subprocess.run([sys.executable, str(SCRIPT), "map", "--json", "--pad", "nintendo"],
                              capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(proc.stdout)
        rows = {r["control"]: r for r in doc["layers"]["base"]}
        self.assertEqual((rows["south"]["name"], rows["east"]["name"]), ("B", "A"))
        self.assertEqual(doc["layer_names"]["world"], "ZL held: the desktop")
        proc = subprocess.run([sys.executable, str(SCRIPT), "map", "--pad", "sega"], capture_output=True,
                              text=True, timeout=10)
        self.assertNotEqual(proc.returncode, 0)


class MapPad(unittest.TestCase):
    def test_the_map_names_the_pad_connected_and_reads_its_charge_without_opening_it(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        self.assertEqual(hg.map_pad(None, str(root))[0].family, "generic")      # no pad: the plain names
        sysfs_device(root, "event7", "Microsoft X-Box 360 pad", 0x045E, 0x028E, "7fdb000000000000 0 0 0 0",
                     "3003f", driver="xpad")
        supply = root / "class" / "input" / "event7" / "device" / "device" / "power_supply" / "xpad_battery"
        supply.mkdir(parents=True)
        (supply / "capacity").write_text("40\n")
        (supply / "status").write_text("Discharging\n")
        found, charge = hg.map_pad(None, str(root))
        self.assertEqual((found.family, found.name_of("south"), charge), ("xbox", "A", "40%"))
        self.assertEqual(hg.map_pad("nintendo", str(root))[0].name_of("south"), "B")


class ReadyNote(unittest.TestCase):
    def note(self, found: "hg.Profile", mode: str = "desk") -> str:
        notes = []

        class Stop(Exception):
            pass

        class Motors(Fx):
            def __init__(self, dev, dry=False):
                super().__init__()
                self.notes = notes

        class Dev:
            uniq, path, name = "", "/dev/input/event30", found.name

            class info:
                vendor, product = found.vendor, found.product

            def close(self):
                pass

        def serve(dev, pad, motors, mic=None):
            raise Stop

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        from unittest import mock
        with mock.patch.multiple(hg, find_pad=lambda path=None: Dev(), serve=serve, Motors=Motors,
                                 profile_of=lambda dev: found, input_dir=lambda dev: str(tmp),
                                 DryHypr=lambda: Hypr(), voice_dir=lambda: tmp), \
                mock.patch.object(hg.time, "sleep"), self.assertRaises(Stop):
            hg.run_daemon(True, None)
        return notes[0]

    def test_a_dualsense_says_what_it_always_said(self):
        self.assertEqual(self.note(hg.Profile()), "DualSense ready: Battery unknown. Hold L2 for the desktop.")

    def test_another_pad_says_its_name_and_its_trigger(self):
        self.assertEqual(self.note(profile(XBOX_360)),
                         "Microsoft X-Box 360 pad ready: Battery unknown. Hold LT for the desktop.")


BTN_TRIGGER, BTN_THUMB, BTN_THUMB2, BTN_TOP = 0x120, 0x121, 0x122, 0x123
DRAGONRISE = dict(name="DragonRise Inc. Generic USB Joystick", vendor=0x0079, product=0x0006, driver="hid-generic",
                  keys=set(range(BTN_TRIGGER, 0x12C)),                 # BTN_TRIGGER .. BTN_BASE6: no BTN_SOUTH
                  absinfo={ABS_X: (0, 255), ABS_Y: (0, 255), ABS_Z: (0, 255), ABS_RZ: (0, 255), **HAT})


class Remaps(PadCase):
    """A pad that sends other codes than the kernel's gamepad spec says: [buttons] names the code of a
    control, [axes] the axis of a stick or trigger (a leading - flips it, "" takes it away)."""

    def write(self, toml: str) -> Path:
        path = self.tmp / "config.toml"
        path.write_text(toml)
        return path

    def remapped(self, shape: dict, toml: str) -> "hg.Profile":
        hg.CONFIG = hg.load_config(self.write(toml))
        buttons, axes = hg.remaps(hg.CONFIG)
        return hg.profile_for(shape["name"], shape["vendor"], shape["product"], shape["driver"], shape["keys"],
                              shape["absinfo"], "", buttons, axes)

    def test_buttons_name_the_code_of_a_control(self):
        found = self.remapped(NO_HOME, '[buttons]\nnorth = "BTN_WEST"\nwest = "0x133"\n')
        self.assertEqual((found.buttons[BTN_WEST], found.buttons[BTN_NORTH]), ("north", "west"))
        found = self.remapped(NO_HOME, '[buttons]\ntriangle = "BTN_Y"\n')       # PlayStation name, old code name
        self.assertEqual(found.buttons[BTN_WEST], "north")
        self.assertNotIn("north", [found.buttons[c] for c in found.buttons if c != BTN_WEST])

    def test_a_joystick_pad_works_once_its_buttons_are_named(self):
        toml = ('[device]\nname = "Generic USB Joystick"\n\n[buttons]\nsouth = "BTN_THUMB2"\neast = "BTN_THUMB"\n'
                'west = "BTN_TOP"\nnorth = "BTN_TRIGGER"\nl2 = "BTN_BASE"\nselect = "BTN_BASE3"\nstart = "BTN_BASE4"\n')
        found = self.remapped(DRAGONRISE, toml)
        self.assertEqual((found.axes[ABS_Z].role, found.axes[ABS_RZ].role), ("rx", "ry"))
        self.assertEqual(found.chord, frozenset({"select", "start"}))
        hypr, procs = Hypr(), self.tmp / "proc"
        procs.mkdir()
        pad = hg.Pad(hypr, Fx(), Clock(), windows=hg.Windows(hypr, str(procs)), voice=self.tmp, profile=found)
        pad.feed(EV_KEY, 0x126, 1)                                     # BTN_BASE: L2, the desktop side
        pad.feed(EV_KEY, BTN_THUMB2, 1)
        self.assertEqual(hypr.sent, [FULLSCREEN])

    def test_a_trigger_named_as_a_button_drops_its_axis_and_the_other_way_round(self):
        found = self.remapped(XBOX_360, '[buttons]\nl2 = "BTN_TL"\nl1 = "BTN_THUMBL"\n')
        self.assertNotIn("l2", {axis.role for axis in found.axes.values()})
        self.assertEqual(found.buttons[BTN_TL], "l2")
        found = self.remapped(PRO, '[axes]\nl2 = ""\n')
        self.assertNotIn("l2", found.buttons.values())                # ZL is gone
        self.assertEqual(found.buttons[BTN_TR2], "r2")

    def test_axes_name_a_stick_or_trigger_axis_and_may_flip_it(self):
        found = self.remapped(XBOX_360, '[axes]\nright_x = "ABS_Z"\nright_y = "-ABS_RZ"\nl2 = "ABS_RX"\nr2 = ""\n')
        roles = {code: (axis.role, axis.flip) for code, axis in found.axes.items()}
        self.assertEqual(roles[ABS_Z], ("rx", False))
        self.assertEqual(roles[ABS_RZ], ("ry", True))
        self.assertEqual(roles[ABS_RX], ("l2", False))
        self.assertNotIn(ABS_RY, roles)                               # the old right stick y: taken by nothing
        self.assertEqual(found.axes[ABS_RZ].tilt(0), 1.0)              # flipped: 0 of 0..255 reads as full down
        self.assertEqual(hg.Axis("l2", 0, 255, True).travel(255), 0.0)

    def test_an_axis_the_pad_lacks_is_left_out(self):
        found = self.remapped(NO_HOME, '[axes]\nright_x = "ABS_RX"\n')
        self.assertNotIn(ABS_RX, found.axes)

    def test_the_tables_are_checked_by_name(self):
        for toml, where in (('[buttons]\nnorth = "BTN_NOPE"\n', "buttons.north"),
                            ('[buttons]\nwing = "BTN_SOUTH"\n', "buttons.wing"),
                            ('[buttons]\nls_up = "BTN_SOUTH"\n', "buttons.ls_up"),
                            ('[buttons]\ntriangle = "BTN_WEST"\nnorth = "BTN_NORTH"\n', "buttons"),
                            ('[axes]\nlx = "ABS_X"\n', "axes.lx"),
                            ('[axes]\nright_x = "BTN_SOUTH"\n', "axes.right_x"),
                            ('[buttons]\nnorth = 308\n', "buttons")):
            with self.assertRaises(hg.ConfigError, msg=toml) as caught:
                hg.load_config(self.write(toml))
            self.assertIn(where, str(caught.exception), toml)

    def test_check_reports_a_bad_table(self):
        import subprocess
        proc = subprocess.run([sys.executable, str(SCRIPT), "check", "--config",
                               str(self.write('[axes]\nright_x = "ABS_NOPE"\n'))], capture_output=True, text=True,
                              timeout=10)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("axes.right_x", proc.stdout)


class Learn(unittest.TestCase):
    """`hypr-gamepad learn` asks for each control in turn and prints the [buttons] and [axes] lines this
    pad needs: only the ones that differ from what hypr-gamepad makes of it by itself."""

    def catch(self, kind: str, events, absinfo=None, rest=None):
        absinfo = absinfo or {ABS_X: (0, 255), ABS_Y: (0, 255), ABS_Z: (0, 255), ABS_HAT0X: (-1, 1),
                              ABS_HAT0Y: (-1, 1)}
        rest = rest or {ABS_X: 128, ABS_Y: 128, ABS_Z: 0, ABS_HAT0X: 0, ABS_HAT0Y: 0}
        catch = hg.Catch(kind, absinfo, rest)
        for event in events:
            found = catch.feed(*event)
            if found is not None:
                return found
        return None

    def test_a_button_is_its_first_press(self):
        self.assertEqual(self.catch("button", [(EV_KEY, BTN_SOUTH, 0), (EV_ABS, ABS_X, 140), (EV_KEY, BTN_NORTH, 1)]),
                         ("key", BTN_NORTH))
        self.assertIsNone(self.catch("button", [(EV_ABS, ABS_X, 255), (EV_KEY, BTN_SOUTH, 0)]))

    def test_a_trigger_is_its_button_or_an_axis_pulled_most_of_the_way(self):
        self.assertEqual(self.catch("trigger", [(EV_ABS, ABS_Z, 40), (EV_KEY, BTN_TL2, 1)]), ("key", BTN_TL2))
        self.assertEqual(self.catch("trigger", [(EV_ABS, ABS_Z, 100), (EV_ABS, ABS_Z, 160)]), ("axis", ABS_Z, False))
        self.assertEqual(self.catch("trigger", [(EV_ABS, ABS_Z, 40)], rest={ABS_Z: 255}), ("axis", ABS_Z, True))
        self.assertIsNone(self.catch("trigger", [(EV_ABS, ABS_X, 255)]))   # a stick moves half its range at most

    def test_a_stick_is_the_axis_that_moves_and_its_way(self):
        self.assertEqual(self.catch("stick", [(EV_ABS, ABS_Y, 140), (EV_ABS, ABS_X, 250)]), ("axis", ABS_X, False))
        self.assertEqual(self.catch("stick", [(EV_ABS, ABS_Y, 5)]), ("axis", ABS_Y, True))
        self.assertIsNone(self.catch("stick", [(EV_ABS, ABS_HAT0X, 1), (EV_KEY, BTN_SOUTH, 1)]))

    def test_a_d_pad_direction_is_the_hat_or_a_button(self):
        self.assertEqual(self.catch("dpad", [(EV_ABS, ABS_HAT0Y, -1)]), ("hat",))
        self.assertEqual(self.catch("dpad", [(EV_KEY, BTN_DPAD_UP, 1)]), ("key", BTN_DPAD_UP))

    def test_settled_is_everything_let_go_and_back_at_rest(self):
        absinfo, rest = {ABS_X: (0, 255), ABS_Z: (0, 255)}, {ABS_X: 128, ABS_Z: 0}
        self.assertTrue(hg.settled(set(), {ABS_X: 140, ABS_Z: 30}, rest, absinfo))
        self.assertFalse(hg.settled({BTN_SOUTH}, {}, rest, absinfo))
        self.assertFalse(hg.settled(set(), {ABS_X: 250}, rest, absinfo))

    def test_a_pad_read_as_it_is_needs_no_lines(self):
        learned = {"south": ("key", BTN_SOUTH), "west": ("key", BTN_NORTH), "north": ("key", BTN_WEST),
                   "l2": ("axis", ABS_Z, False), "r2": ("axis", ABS_RZ, False), "up": ("hat",),
                   "left_x": ("axis", ABS_X, False), "left_y": ("axis", ABS_Y, False),
                   "right_x": ("axis", ABS_RX, False), "right_y": ("axis", ABS_RY, False), "capture": None}
        self.assertEqual(hg.learn_lines(profile(XBOX_360), learned), [])

    def test_a_joystick_pad_gets_the_lines_it_needs(self):
        learned = {"south": ("key", BTN_THUMB2), "east": ("key", BTN_THUMB), "west": ("key", BTN_TOP),
                   "north": ("key", BTN_TRIGGER), "l2": ("key", 0x126), "r2": ("key", 0x127),
                   "up": ("hat",), "home": None,
                   "left_x": ("axis", ABS_X, False), "left_y": ("axis", ABS_Y, True),
                   "right_x": ("axis", ABS_Z, False), "right_y": ("axis", ABS_RZ, False)}
        self.assertEqual(hg.learn_lines(profile(DRAGONRISE), learned),
                         ["[buttons]", 'south = "BTN_THUMB2"', 'east = "BTN_THUMB"', 'west = "BTN_TOP"',
                          'north = "BTN_TRIGGER"', 'l2 = "BTN_BASE"', 'r2 = "BTN_BASE2"', "",
                          "[axes]", 'left_y = "-ABS_Y"'])

    def test_a_trigger_learned_as_an_axis_where_a_button_was_expected(self):
        learned = {"l2": ("axis", ABS_Z, False)}
        self.assertEqual(hg.learn_lines(profile(DUALSENSE), learned), ["[axes]", 'l2 = "ABS_Z"'])

    def test_the_lines_read_back_as_the_learned_pad(self):
        """What learn prints, pasted into a config, makes the profile read the pad as it was learned."""
        learned = {"south": ("key", BTN_THUMB2), "l2": ("key", 0x126), "left_y": ("axis", ABS_Y, True)}
        lines = hg.learn_lines(profile(DRAGONRISE), learned)
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "config.toml").write_text("\n".join(lines) + "\n")
        buttons, axes = hg.remaps(hg.load_config(tmp / "config.toml"))
        shape = DRAGONRISE
        found = hg.profile_for(shape["name"], shape["vendor"], shape["product"], shape["driver"], shape["keys"],
                               shape["absinfo"], "", buttons, axes)
        self.assertEqual((found.buttons[BTN_THUMB2], found.buttons[0x126], found.axes[ABS_Y].flip),
                         ("south", "l2", True))
        self.assertEqual(hg.learn_lines(found, learned), [])

    def test_learn_without_a_pad_says_so(self):
        import subprocess
        proc = subprocess.run([sys.executable, str(SCRIPT), "learn", "--device", "/dev/input/event9999"],
                              capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 1)
        self.assertRegex(proc.stdout, "No gamepad|python-evdev")


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
