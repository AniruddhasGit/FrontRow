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


# ---- S-XCT-03 (CR-002 A-2): the row-lock allow-list, which S-PAY-07 also requires to hold ---------------------

LOCK_ALLOW_LIST = {
    "api/bookings.py": {"showtime"},  # the confirm
    "domain/admin/": {"screen", "seat", "showtime", "movie", "cinema", "users", "seat_category",
                      "language", "certification", "genre", "format"},  # version-checked admin edits (P-ADM-13)
    "workers/__init__.py": {"outbox_message"},  # with SKIP LOCKED (S-TKT-06)
    "api/receipts.py": {"receipt_dispatch"},  # P-TKT-05
}
SEAT_OCCUPANCY = {"booking_seat", "showtime_seat"}
LOCK = re.compile(r"FOR UPDATE|with_for_update\(")


def _not_code_lines(source: str) -> set[int]:
    """Comment lines and docstring lines: they take no lock, so the allow-list does not count them."""
    import ast

    lines = {n for n, ln in enumerate(source.splitlines(), 1) if ln.lstrip().startswith("#")}
    for node in ast.walk(ast.parse(source)):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body \
                and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            lines |= set(range(body[0].lineno, body[0].end_lineno + 1))
    return lines


def locked_table(rel: str, lines: list[str], n: int) -> set[str]:
    """The table(s) the lock on line n takes, read from the statement ending on that line (at most 4 lines up)."""
    window = " ".join(lines[max(0, n - 4):n])
    if "with_for_update(" in lines[n - 1]:
        name = re.findall(r"select\((\w+)", window)[-1]
        if rel == "domain/admin/lookups.py" and re.search(rf"^\s*{name} = table\(kind\)$", "\n".join(lines), re.M):
            from app.domain.admin.lookups import KINDS  # `t = table(kind)`: one of the four lookup tables
            return {t.name for t in KINDS.values()}
        return {name}
    alias = re.search(r"FOR UPDATE OF (\w+)", lines[n - 1])
    if alias:
        return {re.search(rf"(?:FROM|JOIN)\s+(\w+)\s+(?:AS\s+)?{alias[1]}\b", window, re.I)[1]}
    return {re.findall(r"FROM\s+(\w+)", window, re.I)[-1]}


def row_locks() -> list[tuple[str, int, set[str]]]:
    """Every code hit of rg -n 'FOR UPDATE|with_for_update\\(' backend/app, with the table(s) it locks."""
    app = REPO / "backend" / "app"
    out = []
    for f in sorted(app.rglob("*.py")):
        source = f.read_text(encoding="utf-8")
        skip, lines, rel = _not_code_lines(source), source.splitlines(), f.relative_to(app).as_posix()
        out += [(rel, n, locked_table(rel, lines, n)) for n, ln in enumerate(lines, 1) if n not in skip and LOCK.search(ln)]
    return out


def lock_violations(locks=None) -> list[tuple[str, int, set[str]]]:
    """Hits off the allow-list, and any lock of a seat-occupancy table. Empty when the allow-list holds."""
    def allowed(rel: str) -> set[str]:
        return next((v for k, v in LOCK_ALLOW_LIST.items() if rel == k or (k.endswith("/") and rel.startswith(k))), set())
    return [(rel, n, t) for rel, n, t in (row_locks() if locks is None else locks)
            if t & SEAT_OCCUPANCY or not t <= allowed(rel)]
