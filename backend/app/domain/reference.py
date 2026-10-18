"""The booking reference: 7 random characters plus 1 check character (SRC-004 R-5, OPEN-REFCHAR-01).

Stored as 8 upper-case characters over the 26-character alphabet below, no prefix and no hyphens;
displayed FR-XXXX-XXXX. The database's ck_booking__reference_charset checks the alphabet and the length;
it cannot check the arithmetic, which is here. The UNIQUE constraint on booking.reference, not this
module, is the collision guard (P-TKT-01). The application and scripts/seed.py both issue references
through new_reference(), so there is one generator.

[JUDGMENT CALL] (SRC-004 R-5 leaves the arithmetic to the build session; reasoning in
docs/07 Architecture/for_llm/01_system_context.md 'The check algorithm'): a Verhoeff-type check over the
dihedral group D13, which has 26 elements, one per alphabet character. No weighted sum mod 26 can catch
every single substitution AND every adjacent transposition; this does both, and the tests in
backend/tests/seed/test_reference.py prove it exhaustively.

Conventions (standard Verhoeff):
- element index i < 13 is the rotation r^i; i >= 13 is the reflection r^(i-13)s. Character k of the
  alphabet is element k, so '2' is the identity.
- positions are counted from the RIGHT starting at 0; the check character sits at position 0.
- the character at position p contributes sigma^p(element), multiplied left to right from position 0,
  where sigma(r^k) = r^(-k) and sigma(r^k s) = r^(k+1) s.
- a reference is valid when that product is the identity.
"""

from __future__ import annotations

import secrets
from typing import Protocol

ALPHABET = "23456789ACDEFHJKMNPQRTVWXY"  # SRC-003 OPEN-TICKET-01's 30 characters minus Z S B G
LENGTH = 8  # 7 random + 1 check (SRC-004 R-5: "the length stays 8")
_N = 13  # D13: 13 rotations and 13 reflections
_INDEX = {c: i for i, c in enumerate(ALPHABET)}


def _mul(a: int, b: int) -> int:
    """The group product a * b in D13, on element indices 0..25."""
    ar, a_ref = a % _N, a >= _N
    br, b_ref = b % _N, b >= _N
    if not a_ref:  # r^x * r^y = r^(x+y);  r^x * r^y s = r^(x+y) s
        return (ar + br) % _N + (_N if b_ref else 0)
    # r^x s * r^y = r^(x-y) s;  r^x s * r^y s = r^(x-y)
    return (ar - br) % _N + (0 if b_ref else _N)


def _inv(a: int) -> int:
    # A rotation's inverse is the opposite rotation; every reflection is its own inverse.
    return (-a) % _N if a < _N else a


# sigma, as a table: r^k -> r^(-k), r^k s -> r^(k+1) s.
_SIGMA = tuple([(-k) % _N for k in range(_N)] + [_N + (k + 1) % _N for k in range(_N)])


def _sigma_pow(p: int, a: int) -> int:
    for _ in range(p):
        a = _SIGMA[a]
    return a


def _product(elements_right_to_left: list[int], first_position: int) -> int:
    c = 0  # identity
    for p, x in enumerate(elements_right_to_left, start=first_position):
        c = _mul(c, _sigma_pow(p, x))
    return c


def check_character(payload: str) -> str:
    """The check character for the 7 random characters (they take positions 1..7)."""
    if len(payload) != LENGTH - 1 or any(ch not in _INDEX for ch in payload):
        raise ValueError("payload must be 7 characters from the reference alphabet")
    return ALPHABET[_inv(_product([_INDEX[ch] for ch in reversed(payload)], 1))]


def is_valid(ref: object) -> bool:
    """True only for 8 alphabet characters whose check character is right. Called before any database
    read wherever software reads a typed reference (EP-TKT-01, EP-ACC-08, EP-TKT-02)."""
    if not isinstance(ref, str) or len(ref) != LENGTH or any(ch not in _INDEX for ch in ref):
        return False
    return _product([_INDEX[ch] for ch in reversed(ref)], 0) == 0


class _Choice(Protocol):
    def choice(self, seq: str) -> str: ...


def new_reference(rng: _Choice | None = None) -> str:
    """A fresh reference. `rng` is for tests only; production uses the secrets module (26^7 = 8,031,810,176
    possible references, so the unique constraint, not luck, settles a collision)."""
    pick = (rng or secrets.SystemRandom()).choice
    payload = "".join(pick(ALPHABET) for _ in range(LENGTH - 1))
    return payload + check_character(payload)
