"""ADMIN router at /api/admin, role admin only (EP-ADM-01..29). Every privileged write lives here.

Each admin lane adds ONE module to this package (movies.py, showtimes.py, ...) exposing
`router = APIRouter()` with NO prefix and NO dependency of its own; it is included below automatically
and inherits /api/admin and require_admin. Nobody edits this file or main.py to add a route.
The role check runs before the body is validated, so a manager's PATCH is 403, never 422 (S-XCT-10) - for a
body that PARSES. A body that is not JSON at all is refused by FastAPI while it reads the body, before any
dependency runs, so a guest or a manager sending '{not json' gets 400 REQUEST_INVALID, not 401/403. Nothing
is read or written on that path and nothing about any row is revealed; it is a known ordering, not a bypass.

Every module in this package must expose `router`: the loop below imports each one and a module without it
stops the app from importing at all (fail-closed). Put helpers in app/domain/admin/, not here.
"""

import importlib
import pkgutil

from fastapi import APIRouter, Depends

from app.api.deps import require_admin

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])

# Sorted, so route order (and therefore matching) does not depend on the filesystem.
for _info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
    router.include_router(importlib.import_module(f"{__name__}.{_info.name}").router)
