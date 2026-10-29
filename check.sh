#!/usr/bin/env bash
# The gate: every Python test (the program and the public-repo audit), then the map plugin's Node tests.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m unittest discover -s tests
node --test tests/
echo "check: PASS"
