"""install.sh: one command puts hypr-gamepad in place for the user who runs it.

Every run here has its own HOME, and stubs for systemctl and omarchy that write down what they were
asked: nothing of the real desktop is touched. Root's part (the udev rule) is only printed.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "install.sh"
PLUGIN = "ormus.hypr-gamepad-map"


class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.stubs = self.tmp / "stubs"
        self.stubs.mkdir()
        # The only programs on PATH: these, and the stubs. The desk's own systemctl and omarchy must
        # never be reached from a test (an early version of this file reached omarchy through /usr/bin).
        self.tools = self.tmp / "tools"
        self.tools.mkdir()
        for tool in ("bash", "sh", "install", "cp", "rm", "mkdir", "sed", "id", "tr", "grep", "cmp", "python3",
                     "dirname", "cat", "env", "printf"):
            found = shutil.which(tool)
            if found:
                (self.tools / tool).symlink_to(found)
        self.calls = self.tmp / "calls"
        self.stub("systemctl")
        self.rules = self.tmp / "rules.d"
        self.rules.mkdir()

    def stub(self, name: str) -> None:
        path = self.stubs / name
        path.write_text(f'#!/bin/sh\necho "{name} $*" >> "{self.calls}"\n')
        path.chmod(0o755)

    def run_install(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        environ = {"HOME": str(self.home), "PATH": f"{self.stubs}:{self.tools}",
                   "HYPR_GAMEPAD_UDEV_RULES": str(self.rules), **(env or {})}
        return subprocess.run([str(self.tools / "bash"), str(INSTALL), *args], capture_output=True, text=True, timeout=60,
                              env=environ, cwd=self.tmp)

    def called(self) -> list[str]:
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_a_fresh_install_puts_every_file_in_place_and_starts_nothing(self):
        proc = self.run_install()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        program = self.home / ".local/bin/hypr-gamepad"
        self.assertEqual(program.read_bytes(), (ROOT / "hypr-gamepad").read_bytes())
        self.assertTrue(program.stat().st_mode & stat.S_IXUSR)
        unit = self.home / ".config/systemd/user/hypr-gamepad.service"
        self.assertEqual(unit.read_text(), (ROOT / "systemd/hypr-gamepad.service").read_text())
        config = self.home / ".config/hypr-gamepad/config.toml"
        self.assertEqual(config.read_text(), (ROOT / "config.example.toml").read_text())
        self.assertEqual(self.called(), [])                            # nothing enabled, nothing started
        self.assertIn("sudo install -m 0644", proc.stdout)            # root's part, printed
        self.assertIn("hypr-gamepad check", proc.stdout)               # what to run next
        self.assertIn("--enable", proc.stdout)

    def test_a_config_already_there_is_kept(self):
        config = self.home / ".config/hypr-gamepad/config.toml"
        config.parent.mkdir(parents=True)
        config.write_text("# mine\n")
        proc = self.run_install()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(config.read_text(), "# mine\n")
        self.assertIn("kept", proc.stdout)

    def test_xdg_config_home_is_where_the_config_and_the_unit_go(self):
        xdg = self.tmp / "xdg"
        proc = self.run_install(env={"XDG_CONFIG_HOME": str(xdg)})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((xdg / "hypr-gamepad/config.toml").is_file())
        self.assertTrue((xdg / "systemd/user/hypr-gamepad.service").is_file())

    def test_enable_starts_the_service(self):
        proc = self.run_install("--enable")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.called(), ["systemctl --user daemon-reload",
                                         "systemctl --user enable --now hypr-gamepad.service"])

    def test_the_map_plugin_goes_in_only_with_the_omarchy_shell(self):
        proc = self.run_install()
        self.assertFalse((self.home / ".config/omarchy/plugins" / PLUGIN).exists())
        self.assertIn("no Omarchy", proc.stdout)
        self.stub("omarchy")
        proc = self.run_install("--enable")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        plugin = self.home / ".config/omarchy/plugins" / PLUGIN
        self.assertEqual(sorted(p.name for p in plugin.iterdir()),
                         sorted(p.name for p in (ROOT / "omarchy" / PLUGIN).iterdir()))
        self.assertIn(f"omarchy plugin enable {PLUGIN}", self.called())
        self.assertIn("omarchy restart shell", self.called())

    def test_an_installed_udev_rule_is_not_asked_for_again(self):
        shutil.copy(ROOT / "udev/60-hypr-gamepad.rules", self.rules / "60-hypr-gamepad.rules")
        proc = self.run_install()
        self.assertNotIn("sudo install -m 0644", proc.stdout)
        (self.rules / "60-hypr-gamepad.rules").write_text("# an older one\n")
        proc = self.run_install()
        self.assertIn("sudo install -m 0644", proc.stdout)            # differs from the repo's: asked again

    def test_uninstall_takes_out_what_install_put_in_and_keeps_the_config(self):
        self.stub("omarchy")
        self.run_install("--enable")
        self.calls.unlink()
        proc = self.run_install("--uninstall")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((self.home / ".local/bin/hypr-gamepad").exists())
        self.assertFalse((self.home / ".config/systemd/user/hypr-gamepad.service").exists())
        self.assertFalse((self.home / ".config/omarchy/plugins" / PLUGIN).exists())
        self.assertTrue((self.home / ".config/hypr-gamepad/config.toml").exists())
        self.assertEqual(self.called(), ["systemctl --user disable --now hypr-gamepad.service",
                                         "systemctl --user daemon-reload", f"omarchy plugin disable {PLUGIN}",
                                         "omarchy restart shell"])

    def test_an_unknown_option_is_refused(self):
        proc = self.run_install("--everything")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage", proc.stderr.lower())
        self.assertFalse((self.home / ".local").exists())


if __name__ == "__main__":
    unittest.main()
