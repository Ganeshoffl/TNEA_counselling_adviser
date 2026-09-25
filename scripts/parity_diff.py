#!/usr/bin/env python3
"""
Deep-compares the Python and JavaScript engine outputs.

The engine is implemented twice: in Python (which backs the documented API) and in
JavaScript (which lets the app run with no server on static hosting). That is a
real maintenance risk, so this check turns it into a guarded invariant: every
number, string, verdict and ordering must agree.

Floats are compared with a tiny tolerance because the two runtimes can differ in
the last bit of a double. Everything else must match exactly.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

TOLERANCE = 1e-9
MAX_REPORTED = 20


def compare(left, right, path: str, problems: list[str]) -> None:
    if len(problems) >= MAX_REPORTED:
        return

    if isinstance(left, bool) or isinstance(right, bool):
        if left is not right:
            problems.append(f"{path}: python={left!r} js={right!r}")
        return

    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if left is None or right is None:
            if left != right:
                problems.append(f"{path}: python={left!r} js={right!r}")
            return
        if math.isnan(float(left)) and math.isnan(float(right)):
            return
        if abs(float(left) - float(right)) > TOLERANCE:
            problems.append(f"{path}: python={left!r} js={right!r}")
        return

    if left is None or right is None:
        if left is not right:
            problems.append(f"{path}: python={left!r} js={right!r}")
        return

    if isinstance(left, str) and isinstance(right, str):
        if left != right:
            problems.append(f"{path}: string differs\n      python: {left[:150]!r}\n      js:     {right[:150]!r}")
        return

    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            problems.append(f"{path}: list length python={len(left)} js={len(right)}")
            return
        for index, (a, b) in enumerate(zip(left, right)):
            compare(a, b, f"{path}[{index}]", problems)
        return

    if isinstance(left, dict) and isinstance(right, dict):
        missing_in_js = sorted(set(left) - set(right))
        missing_in_py = sorted(set(right) - set(left))
        if missing_in_js:
            problems.append(f"{path}: keys missing in js: {missing_in_js}")
        if missing_in_py:
            problems.append(f"{path}: extra keys in js: {missing_in_py}")
        for shared in sorted(set(left) & set(right)):
            compare(left[shared], right[shared], f"{path}.{shared}", problems)
        return

    problems.append(f"{path}: type python={type(left).__name__} js={type(right).__name__}")


def summarise(payload: list[dict]) -> str:
    bits = []
    for result in payload:
        inp = result["input"]
        counts = "/".join(str(result["modes"][m]["option_count"]) for m in ("safe", "optimal", "risk"))
        bits.append(f"rank {inp['rank']} {inp['community']} R{inp['current_round']} -> {counts}")
    return "; ".join(bits)


def main() -> int:
    py = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    js = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

    problems: list[str] = []
    compare(py, js, "$", problems)

    if problems:
        print(f"  FAIL  engines disagree ({len(problems)} difference(s) shown, first {MAX_REPORTED} max)")
        for problem in problems:
            print(f"        {problem}")
        return 1

    scored = sum(r["scored_candidates"] for r in py)
    options = sum(
        r["modes"][m]["option_count"] for r in py for m in ("safe", "optimal", "risk")
    )
    print(
        f"  PASS  Python and JavaScript engines agree exactly across "
        f"{len(py)} profiles, {scored:,} scored candidates and {options} ranked options"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
