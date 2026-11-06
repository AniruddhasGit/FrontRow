# FrontRow runbook (Phase 7)

SRC-002 §12.8's runbook, kept in `docs/35 Hypercare/` (FR-ADR-008). One operator, no backup decider, no escalation
path (P-XCT-14). Everything about AWS below is *(reasoned, not observed)* until the client has run it there.

## What is watched, and what is not

**One alarm exists: the ECS service's running task count below 1**, through SNS to the operator's own address, with
missing data treated as breaching (`P1_TASK_COUNT_ALARM.md`). Nothing else alerts. In particular:

- **dead letter queue depth** is not alarmed. A message there is a customer who paid and whose receipt never sent.
- **outbox_message pending count** is not alarmed. Rising, it means the relay is stuck and receipts are not enqueued.
- **SES bounce and complaint rate** is not alarmed. Rising, it means receipts are going nowhere.
- The api's `/metrics` exists, but nothing scrapes it (`docs/30 Deployment/P7_METRICS.md`). Read it by hand.

## Receipt: what "sent" means

`receipt_dispatch.status = 'sent'` is **evidence of dispatch, never of receipt**. It is set when SES accepted the
message for delivery, and nothing after that point reports back to this system. A receipt that bounced at the
recipient's server, or was filtered into spam, is indistinguishable from one that reached the inbox: both read `sent`.

The receipts queue depth is not alarmed either, and the dead letter queue depth is not alarmed. A receipt stuck in
either is found only by an operator looking.

**There is no operator re-send:** no endpoint, screen or job in v1 re-sends a receipt on an operator's behalf. The
customer's own resend on the booking page (EP-TKT-02) is the only re-send, and that page shows the reference on screen
too (OPEN-EMAILFAIL-01). And a dead letter redrive is a Zone C console action: the client moves the message back to the
source queue in the SQS console, and the worker's claim makes a second send of an already-sent receipt a no-op.

### Where receipts stand, by status

```sql
SELECT status, count(*)
FROM receipt_dispatch
GROUP BY status
ORDER BY status;
```

`failed` rows are retried by queue redelivery; a row `sending` for longer than `RECEIPT_CLAIM_STALE_SECONDS` (900 s) is
a worker that died mid-send, and the next delivery retakes it.

### What the relay still owes

```sql
SELECT id, topic, created_at, attempts, last_error
FROM outbox_message
WHERE status = 'pending'
ORDER BY created_at;
```

A `receipt.send` row pending for minutes is the relay stuck (the worker down, or `QUEUE_URL` unreachable). A
`password_reset.send` row pending is normal and permanent: its queue send failed once, it is never retried (the token
cannot be rebuilt), and the customer asks again.

## What to look at first, in order

1. The alarm fired: **running task count below 1**. `aws ecs describe-services` shows why the task stopped (a refused
   configuration exits 78 and names the variable in its first log line).
2. Customers report no receipt: the two `sql` queries above, then the dead letter queue's message count in the console.
3. Everything slow: `/metrics` on the host (`curl -s localhost:8000/metrics`), then RDS connections against roughly
   110 on `db.t3.micro`.
