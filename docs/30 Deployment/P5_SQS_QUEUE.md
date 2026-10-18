# P5 — The receipts queue, its dead letter queue, and the worker service (prep-queue rows 9, 26, 29)

> **Zone C. The client builds all of it by hand.** This file says what the application expects and how to know it
> is right. It does not give the console clicks (`SRC-002 §6.5`). Everything about AWS here is
> *(reasoned, not observed)*: no part of the worker has run in AWS.

## What the application expects

- The **api** sends one SQS message per confirmed booking, after the commit, bounded by `QUEUE_SEND_TIMEOUT_MS`
  (2000 ms). If that send fails the booking is still committed; the row stays `pending` in `outbox_message` and the
  worker relays it 30 s later (`OUTBOX_RELAY_MIN_AGE_SECONDS`).
- The **worker** (`frontrow-entrypoint worker`, the SAME image as the api) long-polls the queue
  (`QUEUE_POLL_WAIT_SECONDS`, 20 s), claims each receipt in PostgreSQL, sends it through SES, and deletes the message
  only after SES accepted it. **A refused or timed-out send is not deleted**, so SQS redelivers it.
- The message topic travels as a message **attribute** named `topic`. A message whose topic the worker does not
  recognise is never deleted: redelivery carries it to the dead letter queue, which is the evidence of whatever wrote it.
- One variable, `QUEUE_URL`, points the same code at SQS or at ElasticMQ. There is no SQS-only code path.

## What to build

1. A **standard** SQS queue for receipts (not FIFO: the claim row, not the queue, prevents a duplicate).
2. A **dead letter queue**, and a redrive policy on the receipts queue pointing at it.
3. The two orderings below, on the receipts queue.
4. The DLQ's retention **longer** than the source queue's (row 26): SQS keeps a message's original enqueue time when it
   moves it, so an equal retention deletes the evidence on arrival.
5. An ECS service for the worker: the api's image, command `worker`, **no port mapping and no load balancer** (it has
   no HTTP surface), a hard memory limit (row 29), the `awslogs` driver (row 7), and the same SSM parameters as the api.
6. Task-role permissions (row 12): the api needs `sqs:SendMessage` on the receipts queue; the worker needs
   `sqs:ReceiveMessage`, `sqs:DeleteMessage` and `sqs:SendMessage` (the relay) on it, and `ses:SendEmail` from the one
   verified identity. Neither task definition carries AWS keys: the task role supplies credentials.

## The two orderings, and why each one is a rule about two values

| # | Rule | Wrong, and what happens with nothing reporting it |
|---|---|---|
| 1 | **visibility timeout < `RECEIPT_CLAIM_STALE_SECONDS`** (900) | a redelivery arrives while the first send is still running, finds the claim stale, takes it, and a second receipt is sent |
| 2 | **`maxReceiveCount` > `ceil(RECEIPT_CLAIM_STALE_SECONDS / visibility timeout)`** — `ceil(900 / 120) = 8` at a 120 s visibility timeout, so **9 or more** | the message reaches the DLQ before a dead worker's claim goes stale, and the receipt is never sent |

The local `docker-compose.yml` ElasticMQ queue uses the worked pair: visibility 120 s, `maxReceiveCount` 9.

## The worker's stop timeout

On SIGTERM the worker stops polling, finishes the message in hand, and exits 0. A long poll already in flight is waited
out, so **the worker's ECS stop timeout must exceed `QUEUE_POLL_WAIT_SECONDS` + `SES_SEND_TIMEOUT_MS`** (20 s + 5 s).
Measured locally on 2026-10-18: `docker stop` of an idle worker returned in 12 s with exit code 0. Shorter, and SIGKILL
lands mid-send: the claim is left `sending` and the receipt waits 15 minutes for the stale reclaim.

## Measured (local, docker compose, 2026-10-18 — not t3.micro, not AWS)

- worker resident memory, idle and polling, boto3 loaded: **88.3 MiB** of the 150 MiB limit (`docker stats`).
- api resident memory, idle, boto3 not yet loaded (it is imported on the first send): **70.3 MiB** of 200 MiB.
  Importing boto3 and creating the SQS and SES clients adds about **22 MB** to a process (77,632 KB → 100,592 KB
  max RSS for `import app.main` alone versus with both clients), so the api after its first send is about 92 MiB.

## Acceptance criteria

1. A confirmed booking's `outbox_message` row reads `sent` within a second of the 201, and its `receipt_dispatch` row
   reads `sent` with a non-null `ses_message_id` once the worker has run.
2. With the worker stopped, a booking's receipt goes out when it starts again (receipts are delayed, not lost).
3. A message sent by hand with a `topic` attribute of `receipt.print` ends up in the DLQ after `maxReceiveCount` receives
   and is never deleted.
4. `docker stop` / an ECS deploy of the worker records exit code 0, not 137.

## Common mistakes

- **A FIFO queue "to prevent duplicates".** It does not: SES can accept and the delete can still fail. The claim row is
  the guard; FIFO adds a cost and a throughput ceiling and fixes nothing.
- **Giving the worker a port mapping or a target group.** It has no HTTP surface; a target group health check against
  it fails forever and ECS replaces healthy workers in a loop.
- **A DLQ with the default 4-day retention behind a 4-day source queue** — row 26.
