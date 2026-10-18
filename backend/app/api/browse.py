"""PUBLIC router at /api: movies, showtimes, the seat map, reference data (EP-BRW-01..07).
No session dependency - a guest browses. GET only: Lax cookies ride on cross-site GETs (P-XCT-06)."""

from fastapi import APIRouter

router = APIRouter(prefix="/api")
