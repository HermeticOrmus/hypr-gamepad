"""The repo is public: no private address and no private name in any file it carries.

The files are the ones git tracks (`git ls-files`); outside a git checkout, every file under the repo
except .git and what .gitignore leaves out. This file holds the banned words themselves, so it is the one file not read.
"""
from __future__ import annotations

import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF = Path(__file__).resolve()

# 10/8, 172.16/12, 192.168/16, and 100.64/10 (carrier-grade NAT, used by mesh VPNs).
OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
PRIVATE_IP = re.compile(
    r"(?<![\d.])(?:"
    rf"10\.{OCTET}\.{OCTET}\.{OCTET}"
    rf"|172\.(?:1[6-9]|2\d|3[01])\.{OCTET}\.{OCTET}"
    rf"|192\.168\.{OCTET}\.{OCTET}"
    rf"|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.{OCTET}\.{OCTET}"
    r")(?![\d]|\.\d)"
)
# Whole words, any case. "ormus" alone stays allowed (the plugin id ormus.hypr-gamepad-map, the
# HermeticOrmus account); only the possessive is banned.
# The copyright holder's name (LICENSE, the README footer) is meant to be there.
WORDS = ["ormus's", "ormus’s", "sg", "mars", "moon", "corvin", "corvin-server", "tailscale",
         "raven", "alqvimia", "biogenesis", "zapfast", "aegis"]
PRIVATE_WORD = re.compile(
    r"(?<![A-Za-z0-9])(?:" + "|".join(re.escape(w) for w in WORDS) + r")(?![A-Za-z0-9])", re.IGNORECASE
)


def repo_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        out = None
    if out is not None and out.stdout:
        return [ROOT / name for name in out.stdout.decode().split("\0") if name]
    found = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]  # .gitignore's, and git's own
        found += [Path(base, name) for name in files]
    return found


def findings(path: Path, text: str) -> list[str]:
    out = []
    for number, line in enumerate(text.splitlines(), start=1):
        hits = [m.group(0) for m in PRIVATE_IP.finditer(line)] + [m.group(0) for m in PRIVATE_WORD.finditer(line)]
        if hits:
            out.append(f"{path}:{number}: {', '.join(hits)}")
    return out


class Public(unittest.TestCase):
    def test_no_file_carries_a_private_address_or_name(self):
        problems = []
        for path in repo_files():
            if path.resolve() == SELF or not path.is_file():
                continue
            text = path.read_bytes().decode("utf-8", errors="replace")
            problems += findings(path.relative_to(ROOT), text)
        self.assertEqual(problems, [], "private references:\n" + "\n".join(problems))

    def test_the_audit_catches_what_it_must_and_spares_the_rest(self):
        """Without this, a broken pattern would pass every file and the audit would say nothing."""
        caught = ["host sg: DESK", "Ormus's yes", "ssh corvin-server", "teams-raven", "Mars",
                  "at 10.0.0.5", "172.20.1.1", "192.168.1.180", "100.92.213.61", "MOON"]
        for line in caught:
            self.assertTrue(findings(Path("x"), line), line)
        spared = ["ormus.hypr-gamepad-map", "HermeticOrmus", "msg", "sgx", "127.0.0.1", "100.128.0.1",
                  "172.32.0.1", "version 1.10.0.1.2", "Sun board", "marshal", "moonlight"]
        for line in spared:
            self.assertEqual(findings(Path("x"), line), [], line)


if __name__ == "__main__":
    unittest.main()
