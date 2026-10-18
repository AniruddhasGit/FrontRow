"""THE seat-price formula (P-PAY-03, FR-ADR-038). Written once; every caller imports it.

    seat_price_paise = (base_price_paise * (BASIS_POINT_SCALE + uplift_basis_points) + BASIS_POINT_HALF)
                       // BASIS_POINT_SCALE

Integer half-up: adding half the basis-point denominator before an integer floor division rounds an
exact half UP. Worked case (S-ADM-13): base 25000 at 3333 basis points has the exact value 33332 and a
half paise; this formula gives 33333, where half-even would give 33332. A booking total is the SUM of these
already-rounded per-seat prices and is never rounded itself (P-PAY-04): three seats at 33333 total 99999,
never 99998. Two implementations of this formula is the failure mode, so there is no second one.
Every category, the zero-uplift one included, goes through the same expression: there is no special case.
This module is also the only reader of a category's uplift column outside app/models (S-XCT-05), so no
caller can do uplift arithmetic of its own.
"""

from app.domain.money import BIGINT_MAX

# One basis point is 0.01%, so this many basis points is 100%. Named, never a literal in a money expression.
BASIS_POINT_SCALE = 10000
# Half the denominator: the half-up rounding term.
BASIS_POINT_HALF = 5000
# The same two constants under the names S-PAY-02 asserts. Aliases, never second literals: S-ADM-13 allows the
# bare figures on the two definitions above and nowhere else.
BASIS_POINTS_DENOMINATOR = BASIS_POINT_SCALE
ROUNDING_HALF_NUMERATOR = BASIS_POINT_HALF


def seat_price_paise(base_price_paise: int, uplift_basis_points: int) -> int:
    """The price of one seat in paise. Raises OverflowError when the formula's numerator does not fit
    PostgreSQL bigint: the same pair priced in SQL would overflow, so it is refused here as well, and the
    admin ceiling check (P-ADM-10/11) asks this function rather than repeating the expression."""
    # `type(x) is int`, not isinstance: bool is a subclass of int, and a non-integer argument must be a type
    # error rather than a silently rounded result (P-PAY-03 server-side validation).
    if type(base_price_paise) is not int or type(uplift_basis_points) is not int:
        raise TypeError("seat_price_paise takes two ints")
    if base_price_paise < 0 or uplift_basis_points < 0:
        raise ValueError("base_price_paise and uplift_basis_points must be >= 0")
    numerator = base_price_paise * (BASIS_POINT_SCALE + uplift_basis_points) + BASIS_POINT_HALF
    if numerator > BIGINT_MAX:
        raise OverflowError("the seat-price numerator does not fit bigint")
    return numerator // BASIS_POINT_SCALE



# The seat_category column the formula's second argument is read from. Readers select it by this name, so the
# column name appears in this module and app/models only (S-XCT-05) and no caller does uplift arithmetic.
UPLIFT_COLUMN = "uplift_basis_points"
