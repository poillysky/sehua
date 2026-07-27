"""DEPRECATED for normal evolution.

Do NOT use this to batch-run many posts. Evolution is one tid at a time
(see docs/识别进化流程.md). Kept only for rare smoke checks with --limit 1.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--persist", action="store_true")
    args = ap.parse_args()
    if args.limit > 1:
        print(
            "REFUSED: evolution must be one post at a time. "
            "Use: python scripts/parse_evolve.py run-one --bucket ... "
            "then deep-analyze, fix parsers, re-verify same tid.",
            flush=True,
        )
        return 2
    py = sys.executable
    script = ROOT / "scripts" / "parse_evolve.py"
    cmd = [py, str(script), "run-one", "--bucket", args.bucket]
    if args.persist:
        cmd.append("--persist")
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
