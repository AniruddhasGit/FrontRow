"""Helpers the M1 story tests share: the repository root, an `rg`-equivalent, and markdown parsing.

The acceptance criteria are written as `rg` commands. The test image has no ripgrep, so `rg()` below
re-implements the subset the criteria use - a regex per line over a set of paths - with the same
case-insensitive and fixed-string switches. Run the suite with the repository mounted:

    docker run --rm -v "<repo>:/repo:ro" -w /repo/backend frontrow-api-test python -m pytest
"""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO = Path(os.environ.get("FRONTROW_REPO_ROOT") or Path(__file__).resolve().parents[3])
DEPLOY = REPO / "docs" / "30 Deployment"

_SKIP_DIRS = {"node_modules", "dist", "__pycache__", ".git", ".venv", "venv", ".pytest_cache"}


def _files(path: Path):
    if path.is_file():
        yield path
        return
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for f in files:
            yield Path(root) / f


def rg(pattern: str, *paths: str, ignore_case: bool = False, fixed: bool = False) -> list[tuple[str, int, str]]:
    """Return (relative path, line number, line) for every matching line under the given repo paths."""
    flags = re.IGNORECASE if ignore_case else 0
    rx = re.compile(re.escape(pattern) if fixed else pattern, flags)
    hits: list[tuple[str, int, str]] = []
    for p in paths:
        base = REPO / p
        if not base.exists():
            # As rg itself does (exit 2): a moved or mistyped path must never make a zero-hits check pass vacuously.
            raise FileNotFoundError(f"rg: {p}: no such file or directory under {REPO}")
        for f in _files(base):
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue  # binary files: rg skips them too
            for n, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append((f.relative_to(REPO).as_posix(), n, line))
    return hits


def md_table_after(text: str, heading: str) -> list[dict[str, str]]:
    """Parse the first Markdown table after the exact heading line into a list of row dicts."""
    lines = text.splitlines()
    i = lines.index(heading)
    rows: list[list[str]] = []
    for line in lines[i + 1 :]:
        if line.startswith("#"):
            break
        if line.startswith("|"):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
        elif rows:
            break
    header, body = rows[0], [r for r in rows[2:]]
    return [dict(zip(header, r)) for r in body]


def prep_queue() -> list[dict[str, str]]:
    return md_table_after((DEPLOY / "AWS_PREP_QUEUE.md").read_text(encoding="utf-8"), "## Queue")


_LINK = re.compile(r"\[[^\]]*\]\(([^)]+\.md)\)")


def spec_files(cell: str) -> list[str]:
    """The files a queue row's Spec cell names, as Markdown links."""
    return _LINK.findall(cell)


def strip_md(cell: str) -> str:
    return cell.replace("**", "").replace("`", "")


def mounted_routes(app) -> set[tuple[str, str]]:
    """Every (method, path) the application serves, HEAD excluded (Starlette adds it to every GET).

    FastAPI 0.143 wraps each included router in an `_IncludedRouter` whose routes are its
    `effective_candidates`; walking `app.routes` alone would see none of them and pass vacuously.
    """
    pairs: set[tuple[str, str]] = set()

    def walk(routes) -> None:
        for r in routes:
            nested = []
            for attr in ("effective_candidates", "effective_low_priority_routes"):
                found = getattr(r, attr, ())
                nested.extend(found() if callable(found) else found)
            if nested:
                walk(nested)
                continue
            path, methods = getattr(r, "path", None), getattr(r, "methods", None)
            if path and methods:
                pairs.update((m, path) for m in methods if m != "HEAD")

    walk(app.routes)
    return pairs


def zone_c(*paths: str) -> list[str]:
    """Trees the CLIENT writes (Zone C, e.g. .github/workflows) that a criterion sweeps and that may not exist yet.
    Only these may be absent; every other path given to rg() must exist."""
    return [p for p in paths if (REPO / p).exists()]
