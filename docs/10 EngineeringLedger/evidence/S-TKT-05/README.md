# S-TKT-05 — Done

Lane `p5-mail`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/tkt/test_s_tkt_05.py: 7 passed (one pending dispatch row (pending,1,0,null x4) and one outbox row (receipt.send,pending,0); payload keys exact, no @, no seat label, no amount; receipt.render, a fifth key and a missing message_version each raise CheckViolation with counts at 0; the 4-key reset payload commits; the reset payload with reset_token raises; a relay cycle sends 0 password_reset.send and the row stays pending; a forced outbox failure leaves 0 booking and 0 booking_seat; a second dispatch row raises UniqueViolation).

**Note:** DependsOn not yet Done: E-PAY. The confirm transaction (the pay lane's) already wrote both rows. This row adds the proof and the relay's topic filter. The outbox failure is forced by raising from confirm_observer at the 'outbox_message insert' step.
