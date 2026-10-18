# S-TKT-08 — Done

Lane `p5-mail`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/tkt/test_s_tkt_08.py: 8 passed (a blocked send is abandoned at exactly T+5000 ms, and at T+1200 ms with SES_SEND_TIMEOUT_MS=1200; the row reads failed,null,null with 'timeout' in last_error and no refusal text; the message is kept; redelivery makes a second call that is asserted as made; a refusal gives failed with the provider's own text; no '5000' under workers; api and worker each exit 78 without MAIL_PROVIDER or SES_SENDER_ADDRESS, carry their own service field, and bind no port).

**Note:** The bound goes through an injectable Worker.within(ms, awaitable). The test's Bound moves the FakeClock to the bound instead of waiting real seconds.
