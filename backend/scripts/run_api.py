#!/usr/bin/env python3
"""Run FastAPI BFF for 98tang collector/parsers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn


def main() -> None:
    uvicorn.run("api.main:app", host="0.0.0.0", port=8080, reload=True)


if __name__ == "__main__":
    main()
