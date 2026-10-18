"""REPORTING router at /api/reports: the dashboard for managers and admins (EP-RPT-01..03).

READ ONLY. A manager endpoint that writes anything is a defect, not a feature (SRC-003 OPEN-OPS-03).
Mount GET routes only; any other method on a path here is answered 405 by the global handler
(app/api/errors.py), and test_s_xct_10.py walks the route table to prove no write method is mounted.
"""

from fastapi import APIRouter, Depends

from app.api.deps import require_reporting

router = APIRouter(prefix="/api/reports", dependencies=[Depends(require_reporting)])
