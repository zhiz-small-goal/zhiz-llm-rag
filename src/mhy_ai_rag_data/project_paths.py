from __future__ import annotations

from pathlib import Path
from typing import Optional


def find_project_root(root: Optional[str] = None, *, start: Optional[Path] = None) -> Path:
    """Resolve project root.

    Policy (stable, low magic):
    - If `root` is provided, use it.
    - Else start from current working directory and walk upwards until a marker is found.
    - Markers: data_raw/, inventory.csv, pyproject.toml, README.md.

    This makes scripts resilient to src-layout while keeping the default "run from repo root" workflow.
    """
    if root:
        return Path(root).resolve()

    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / "data_raw").exists():
            return p
        if (p / "inventory.csv").exists():
            return p
        if (p / "pyproject.toml").exists():
            return p
        if (p / "README.md").exists():
            return p
    return cur
