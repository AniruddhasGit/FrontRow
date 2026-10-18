"""Money at the request boundary: integer paise, or a 422. Never a float, never rounded (P-XCT-02).

Every request field whose name ends in `_paise` is annotated with one of these. They are STRICT:
`25000` is accepted; `250.00`, `"25000"` and `true` are refused with 422 VALIDATION_FAILED and are
never rounded or coerced (S-XCT-05). The ceiling is PostgreSQL's bigint maximum, so a value that
validates here always fits the column it is written to.

The seat-price formula is NOT here: it is app/domain/pricing.py, the only place it exists.
The minor-unit ratio is configuration (CURRENCY_MINOR_UNIT_RATIO, app/core/config.py), never a literal.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, Strict

# PostgreSQL bigint: 2**63 - 1 (P-XCT-02 server-side validation).
BIGINT_MAX = 9_223_372_036_854_775_807

# Zero or more paise.
Paise = Annotated[int, Strict(), Field(ge=0, le=BIGINT_MAX)]
# One or more paise: a price that must not be free (e.g. a showtime's base price, S-XCT-05).
PositivePaise = Annotated[int, Strict(), Field(gt=0, le=BIGINT_MAX)]
