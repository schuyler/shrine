#!/usr/bin/env python3
"""Run refiretest.pd headless and verify the beat-driven re-fire gate.

Usage:
    uv run python pd/test/run_refiretest.py

Expects pd (Pure Data) on PATH. Runs the patch with:
    pd -nogui -noaudio -stderr -path pd pd/test/refiretest.pd

The patch drives refire.pd from a fake 16th-note clock (metro 100) with a
quarter-note grid (refire=4): touch at 250 ms, release at 1250 ms, quit at
2000 ms. refire.pd should emit a bang immediately on touch and then on each
quarter-note grid position while held, and NOTHING after release.

We assert the observable contract (order-independent of Pd's fan-out):
  - at least 2 ADVANCE lines before release (immediate + >=1 on-grid)
  - exactly 0 ADVANCE lines after release (the gate closes)

NOTE: Pd is not available in the dev container, so this is run on a Pd-equipped
host (target/CI), exactly like run_modetest.py.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def check(stderr: str) -> tuple[bool, str]:
    """Return (passed, message) from parsed Pd stderr."""
    before = 0
    after = 0
    released = False
    for raw in stderr.splitlines():
        line = raw.strip()
        if line.startswith("MARK:") and "RELEASED" in line:
            released = True
        elif line.startswith("ADVANCE:"):
            if released:
                after += 1
            else:
                before += 1

    problems = []
    if before < 2:
        problems.append(f"expected >=2 advances while held, got {before}")
    if after != 0:
        problems.append(f"expected 0 advances after release, got {after}")
    if not released:
        problems.append("never saw MARK: RELEASED (patch did not run to release)")

    if problems:
        return False, "; ".join(problems)
    return True, f"{before} advances while held, 0 after release"


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    patch = repo_root / "pd" / "test" / "refiretest.pd"
    if not patch.exists():
        print(f"ERROR: patch not found at {patch}")
        return 2

    cmd = [
        "pd", "-nogui", "-noaudio", "-stderr",
        "-path", str(repo_root / "pd"),
        str(patch),
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    stderr = result.stderr
    if not stderr.strip():
        print("ERROR: no output from pd (is pd installed and on PATH?)")
        return 2

    print("\n--- relevant pd stderr ---")
    for line in stderr.splitlines():
        s = line.strip()
        if s.startswith("ADVANCE:") or s.startswith("MARK:"):
            print(f"  {s}")
    print("--- end ---\n")

    passed, message = check(stderr)
    print(("PASS: " if passed else "FAIL: ") + message)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
