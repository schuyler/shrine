#!/usr/bin/env python3
"""Run modetest.pd headless and verify state-table / mode-table output.

Usage:
    uv run python pd/test/run_modetest.py

Expects pd (Pure Data) on PATH. Runs the patch with:
    pd -nogui -noaudio -stderr -path pd pd/test/modetest.pd

The patch sequences shrine-state 0-4, printing STATE-MODE, MODE-SIZE, and
INTERVAL-0..6 for each. This script parses the output and checks against
the design-specified modal arc.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# -- Expected arc (from DESIGN-mode-progression.md) --

@dataclass
class ModeExpectation:
    state: int
    mode: str
    size: int
    intervals: list[int]

EXPECTED = [
    ModeExpectation(0, "major-penta", 5, [0, 2, 4, 7, 9, 0, 0]),
    ModeExpectation(1, "major-penta", 5, [0, 2, 4, 7, 9, 0, 0]),
    ModeExpectation(2, "dorian", 7, [0, 2, 3, 5, 7, 9, 10]),
    ModeExpectation(3, "mixolydian-b6", 7, [0, 2, 4, 5, 7, 8, 10]),
    ModeExpectation(4, "ionian", 7, [0, 2, 4, 5, 7, 9, 11]),
]


@dataclass
class ModeObservation:
    """Collected output for one state transition."""
    state: int
    mode: str | None = None
    size: int | None = None
    intervals: list[int | None] = field(default_factory=lambda: [None] * 7)


def parse_output(stderr: str) -> list[ModeObservation]:
    """Parse Pd print output into per-state observations.

    Lines before the first TEST-STATE marker are ignored (loadbang output).
    """
    observations: list[ModeObservation] = []
    current: ModeObservation | None = None

    for raw_line in stderr.splitlines():
        line = raw_line.strip()
        if line.startswith("TEST-STATE:"):
            state_num = int(float(line.split(":")[1].strip()))
            current = ModeObservation(state=state_num)
            observations.append(current)
        elif current is None:
            continue  # ignore loadbang output
        elif line.startswith("STATE-MODE:"):
            current.mode = line.split(":")[1].strip()
        elif line.startswith("MODE-SIZE:"):
            current.size = int(float(line.split(":")[1].strip()))
        elif line.startswith("INTERVAL-"):
            # e.g. "INTERVAL-3: 5"
            idx = int(line.split("-")[1].split(":")[0])
            val = int(float(line.split(":")[1].strip()))
            current.intervals[idx] = val

    return observations


def check(observations: list[ModeObservation]) -> tuple[int, int]:
    """Check observations against expectations. Returns (passed, failed)."""
    passed = 0
    failed = 0

    if len(observations) != len(EXPECTED):
        print(
            f"FAIL: expected {len(EXPECTED)} state groups, got {len(observations)}"
        )
        failed += 1

    for exp in EXPECTED:
        matches = [o for o in observations if o.state == exp.state]
        if not matches:
            print(f"FAIL state {exp.state}: no output captured")
            failed += 1
            continue
        obs = matches[-1]  # use last observation for this state

        # Check mode symbol
        if obs.mode == exp.mode:
            print(f"  ok   state {exp.state} mode: {obs.mode}")
            passed += 1
        else:
            print(
                f"  FAIL state {exp.state} mode: "
                f"expected {exp.mode!r}, got {obs.mode!r}"
            )
            failed += 1

        # Check mode size
        if obs.size == exp.size:
            print(f"  ok   state {exp.state} size: {obs.size}")
            passed += 1
        else:
            print(
                f"  FAIL state {exp.state} size: "
                f"expected {exp.size}, got {obs.size}"
            )
            failed += 1

        # Check intervals
        if obs.intervals == exp.intervals:
            print(f"  ok   state {exp.state} intervals: {obs.intervals}")
            passed += 1
        else:
            print(
                f"  FAIL state {exp.state} intervals: "
                f"expected {exp.intervals}, got {obs.intervals}"
            )
            failed += 1

    return passed, failed


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    patch = repo_root / "pd" / "test" / "modetest.pd"
    if not patch.exists():
        print(f"ERROR: patch not found at {patch}")
        return 2

    cmd = [
        "pd", "-nogui", "-noaudio", "-stderr",
        "-path", str(repo_root / "pd"),
        str(patch),
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=10
    )

    stderr = result.stderr
    if not stderr.strip():
        print("ERROR: no output from pd (is pd installed and on PATH?)")
        return 2

    # Show raw output for debugging
    print("\n--- raw pd stderr ---")
    for line in stderr.splitlines():
        # Filter to our test output (skip Pd boilerplate)
        stripped = line.strip()
        if any(
            stripped.startswith(p)
            for p in (
                "TEST-STATE:", "STATE-MODE:", "MODE-SIZE:", "INTERVAL-",
            )
        ):
            print(f"  {stripped}")
    print("--- end raw output ---\n")

    observations = parse_output(stderr)
    if not observations:
        print("ERROR: no TEST-STATE groups found in output")
        print("Full stderr:")
        print(stderr)
        return 2

    passed, failed_count = check(observations)
    print(f"\n{passed} passed, {failed_count} failed")
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
