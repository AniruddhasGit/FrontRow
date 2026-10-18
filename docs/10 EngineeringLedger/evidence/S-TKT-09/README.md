# S-TKT-09 — Done

Lane `p5-mail`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/tkt/test_s_tkt_09.py: 3 passed (the plain text matches the published 15-line block byte for byte with LF and the column-11 padding; subject matches; HTML has ₹843.72, the 'See this booking again' anchor and exactly one href with the URL, and no <img, <table or <td; no attachment or image part; a resend is byte-identical; a title changed after the enqueue appears in the sent body).

**Note:** Rendering is in backend/app/workers/render.py, not domain/: S-PAY-01 forbids money formatting in api/domain, and P-TKT-06 says only the worker renders. The cancellation/refund sentence is one constant used in both parts, as S-PAY-11 requires.
