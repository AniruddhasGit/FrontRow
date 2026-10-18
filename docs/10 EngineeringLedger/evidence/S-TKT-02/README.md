# S-TKT-02 — Done

Lane `p5-mail`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/tkt/test_s_tkt_02.py: 11 passed (the 4 typed forms give 200; 0/1/7-char/Cyrillic give 404; a 65-char value gives 404 with statements==[]; the statement log has an equality predicate and no like/similarity/~*; the malformed, unknown and other-customer 404s are equal once request_id is removed). Final lane run: 126 passed, 3 failed, none in this file.

**Note:** EP-TKT-01 is new in backend/app/api/receipts.py and registered in main.py. The shape check (isascii, 1..64, alphabet plus check character) runs before the session and the DB, which is how the 0-query clause holds. isascii also blocks Unicode case folding: U+FB00 uppercases to FF.
