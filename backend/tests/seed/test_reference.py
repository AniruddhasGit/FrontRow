"""Self-check of app/domain/reference.py: the booking reference under SRC-004 R-5 and its D13 check character.

The architecture (docs/07 Architecture/for_llm/01_system_context.md, 'The check algorithm') requires the code
to carry an EXHAUSTIVE test of both error classes. Both are exhaustive here, not sampled:

- single substitution: every position x every replacement character, over references whose payload is every
  character in turn (so every character appears at every position at least once);
- adjacent transposition: in a group product, swapping the factors at positions i and i+1 is undetected
  exactly when sigma^i(a) * sigma^(i+1)(b) == sigma^i(b) * sigma^(i+1)(a). That equality does not depend on
  the other characters, so checking every ordered pair a != b at every one of the 7 adjacent position pairs
  (7 x 650 = 4,550 cases) covers every reference there is.
"""

from __future__ import annotations

import random
import re

from app.domain import reference

ALPHABET = "23456789ACDEFHJKMNPQRTVWXY"


def test_the_alphabet_is_the_ruled_26_characters_with_no_z_s_b_g():
    assert reference.ALPHABET == ALPHABET
    assert len(set(reference.ALPHABET)) == 26
    assert not set("ZSBG") & set(reference.ALPHABET)


def test_a_generated_reference_is_8_characters_that_pass_the_schema_check_and_the_check_character():
    rng = random.Random(7)  # a seeded generator: the test never depends on real randomness
    for _ in range(500):
        ref = reference.new_reference(rng)
        assert re.fullmatch(r"[23456789ACDEFHJKMNPQRTVWXY]{8}", ref), ref  # ck_booking__reference_charset
        assert reference.is_valid(ref)


def test_the_check_character_is_the_last_character_and_is_computed_from_the_seven_before_it():
    rng = random.Random(11)
    for _ in range(200):
        ref = reference.new_reference(rng)
        assert ref[-1] == reference.check_character(ref[:7])


def test_the_group_tables_are_a_group_and_sigma_is_a_permutation():
    n = 26
    e = 0
    for a in range(n):
        assert reference._mul(e, a) == a == reference._mul(a, e)
        assert reference._mul(a, reference._inv(a)) == e
        for b in range(n):
            for c in range(n):
                assert reference._mul(reference._mul(a, b), c) == reference._mul(a, reference._mul(b, c))
    assert sorted(reference._SIGMA) == list(range(n))


def test_every_single_substitution_is_detected_exhaustively():
    undetected = checked = 0
    for ch in ALPHABET:
        ref = ch * 7
        ref += reference.check_character(ref)
        assert reference.is_valid(ref)
        for pos in range(8):
            for other in ALPHABET:
                if other == ref[pos]:
                    continue
                checked += 1
                if reference.is_valid(ref[:pos] + other + ref[pos + 1:]):
                    undetected += 1
    assert checked == 26 * 8 * 25
    assert undetected == 0


def test_every_adjacent_transposition_is_detected_exhaustively():
    undetected = checked = 0
    for i in range(7):  # positions from the right, 0 = the check character
        for a in range(26):
            for b in range(26):
                if a == b:
                    continue
                checked += 1
                left = reference._mul(reference._sigma_pow(i, a), reference._sigma_pow(i + 1, b))
                right = reference._mul(reference._sigma_pow(i, b), reference._sigma_pow(i + 1, a))
                if left == right:
                    undetected += 1
    assert checked == 4550
    assert undetected == 0


def test_a_swapped_pair_inside_a_real_reference_is_refused():
    rng = random.Random(3)
    for _ in range(300):
        ref = reference.new_reference(rng)
        for p in range(7):
            if ref[p] != ref[p + 1]:
                assert not reference.is_valid(ref[:p] + ref[p + 1] + ref[p] + ref[p + 2:])


def test_malformed_input_is_not_a_reference():
    for bad in ["", "2345678", "234567892", "2345678Z", "abcdefgh", "FR-2345-6789", None, 12345678]:
        assert reference.is_valid(bad) is False
