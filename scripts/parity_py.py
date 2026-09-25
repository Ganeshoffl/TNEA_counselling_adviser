#!/usr/bin/env python3
"""
Runs the Python engine over the same student profiles as scripts/parity_js.mjs and
prints the result as JSON, so the two implementations can be diffed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.engine import recommend  # noqa: E402


def main() -> int:
    profiles = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = [recommend(**profile) for profile in profiles]
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
