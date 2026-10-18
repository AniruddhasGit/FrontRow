"""THE seat-price formula (P-PAY-03, FR-ADR-038). Written once; every caller imports it.

    seat_price_paise = (base_price_paise * (10000 + uplift_basis_points) + 5000) // 10000

Integer half-up: adding half the basis-point denominator before an integer floor division rounds an
exact half UP (33332.5 -> 33333; half-even would give 33332). A booking total is the SUM of these
already-rounded per-seat prices and is never rounded itself (P-PAY-04): three seats at 33333 total
99999, never 99998. Two implementations of this formula is the failure mode, so there is no second one.
"""


# One basis point is 0.01%, so 10000 basis points is 100%. Named, never a literal in a money expression.
_BASIS_POINTS_PER_WHOLE = 10_000
# Half the denominator: the half-up rounding term.
_HALF_UP = _BASIS_POINTS_PER_WHOLE // 2


def seat_price_paise(base_price_paise: int, uplift_basis_points: int) -> int:
    # `type(x) is int`, not isinstance: bool is a subclass of int, and a float argument must be a type
    # error rather than a silently rounded result (P-PAY-03 server-side validation).
    if type(base_price_paise) is not int or type(uplift_basis_points) is not int:
        raise TypeError("seat_price_paise takes two ints")
    if base_price_paise < 0 or uplift_basis_points < 0:
        raise ValueError("base_price_paise and uplift_basis_points must be >= 0")
    return (base_price_paise * (_BASIS_POINTS_PER_WHOLE + uplift_basis_points) + _HALF_UP) // _BASIS_POINTS_PER_WHOLE
