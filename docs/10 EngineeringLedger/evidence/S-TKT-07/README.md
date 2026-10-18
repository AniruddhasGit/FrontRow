# S-TKT-07 — Done

Lane `p5-mail`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/tkt/test_s_tkt_07.py: 10 passed (two deliveries give 1 call and (sent,1); a sending claim 120 s old gives 0 calls, is deleted, keeps attempts and logs one INFO; at 960 s it is reclaimed with attempts+1 and 1 call; sent, suppressed and a stale seq each give 0 calls and are deleted, and suppressed logs one WARNING with booking_id; topic receipt.print stays in the queue stub; an unknown booking_id is deleted and logs ERROR; no 'insert into receipt_dispatch' and no now()/CURRENT_TIMESTAMP in workers; prep row 9 carries all 6 literals). Red-proof: removing the stale branch from CLAIM_RECEIPT failed [960-True]; the file was then restored.

**Note:** The claim is a conditional UPDATE using parameters from the injected clock. The clock is called through self.instant, so no 'now()' text appears under workers/.
