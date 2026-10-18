"""S-SCP-09 (P-SCP-01, SRC-001 §6.1): one responsive web interface; no native or installable artefact.

Not here (browser harness): the 375-pixel and 1280-pixel viewport geometry - the map container scrolling while
the body does not, and the seat cell's computed 24px width at both.
"""

from __future__ import annotations

import json
import os
import re

from tests.xct._support import REPO, rg

ARTEFACT = re.compile(r"(^|/)(ios|android)/|\.xcodeproj(/|$)|(^|/)AndroidManifest\.xml$|\.webmanifest$|(^|/)capacitor\.config\.[^/]+$")
SKIP = {".git", "node_modules", "dist", "__pycache__", ".pytest_cache", ".venv", "venv"}


def _paths() -> list[str]:
    found = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP]
        rel = os.path.relpath(root, REPO).replace(os.sep, "/")
        for name in [*dirs, *files]:
            path = name if rel == "." else f"{rel}/{name}"
            found.append(path + ("/" if name in dirs else ""))
    return found


def test_no_native_or_installable_artefact_is_in_the_tree():
    paths = _paths()
    assert len(paths) > 100  # the walk saw the repository, not an empty mount
    assert [p for p in paths if ARTEFACT.search(p)] == []


def test_no_native_wrapper_dependency():
    pkg = json.loads((REPO / "frontend" / "package.json").read_text(encoding="utf-8"))
    names = set(pkg.get("dependencies", {})) | set(pkg.get("devDependencies", {}))
    assert names and not [n for n in names if re.search(r"react-native|capacitor|cordova|expo", n)]


def test_no_service_worker_and_no_install_prompt():
    assert rg(r"serviceWorker|beforeinstallprompt", "frontend/src", ignore_case=True) == []
