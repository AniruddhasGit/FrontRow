# P2 · The one-off seed task and the secret it needs  (prep-queue row 19 · needed by Phase 2)

> Zone C specification. What to build, not how (`SRC-002 §6.5`). Every claim about AWS behaviour is
> **(reasoned, not observed)**: this session has never seen the application run in AWS.
> Sources: PRD `P-XCT-30`, `P-XCT-32`, `S7.9`; ledger `S-XCT-46`, `S-XCT-48`, `S-XCT-49`.

## Read this first — it is permanent

**Settle seat labelling before the first seeded showtime write.** The seed inserts 720 showtimes across
all six halls, and a hall's layout freezes the moment any showtime exists on it (`P-ADM-14`). From then on,
renumbering a seat, removing a seat or moving a seat to another category is refused with
**409 LAYOUT_FROZEN**. The labels are what a receipt carries and what the person at the door reads.
The seed prints one `NOTICE:` line just before that write; it does not stop and ask, because a one-off
task has no one to answer.

**The wipe-and-reseed command is never run against the deployed environment. Seeded rows there are permanent, because nothing is ever deleted.**
Locally, `python scripts/seed.py --wipe-and-reseed` (with the owner's `DATABASE_URL`) empties every table
and seeds again. In AWS there is no route back.

The seed writes demonstration data only: `DEMO` names and addresses at `demo.frontrow.invalid`, which can
never receive mail. One password is shared by all 63 seeded accounts; that is accepted **only** because
this environment carries no real customer data (`P-XCT-32`).

## What to build

- **a one-off ECS task**, run once and deliberately by the client, never a service and never on a
  schedule. It starts, seeds, and exits with the seed's status.
- **a task definition family that is the seed's alone** — not the api's family with a command override,
  and not the worker's. Reason: a run-task override can change the command but cannot add a `secrets`
  entry, so a secret that must reach only this task cannot live in a shared family.
- It runs **the same image** as the api, so the seed and the code it seeds for are the same build.
  The container command is `seed`.
- `SEED_DEFAULT_PASSWORD` as an SSM **SecureString** at `/frontrow/<environment>/SEED_DEFAULT_PASSWORD`,
  injected into this task definition's `secrets` block by `valueFrom`. You choose the value; it is
  written nowhere in this repository and the seed never prints it.
- The parameter is read by **the execution role, not the task role** (prep-queue row 15): the ECS agent
  resolves `secrets` before the container starts, so `ssm:GetParameters` on the task role does nothing
  here. Grant the execution role of this family `ssm:GetParameters` on that one parameter.
- `DATABASE_URL` for this task: the application user (`frontrow_app`) is enough — the seed only inserts.
  It never needs the owner's credentials, because the wipe is never run here.
- **The service's task definition never carries the parameter.** The api and the worker never read
  `SEED_DEFAULT_PASSWORD`, so putting it in their `secrets` would hand a credential to two processes that
  have no use for it.
- A hard memory limit on the task (prep-queue row 29 estimates 150 MiB; not measured).

## What the application expects

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | `postgresql://` or `postgres://` |
| `SEED_DEFAULT_PASSWORD` | yes, no default | at least `PASSWORD_MIN_LENGTH` (12) characters and at most 72 bytes; the `.env.example` placeholder is refused by value |
| `SEED_EMAIL_DOMAIN` | no | defaults to `demo.frontrow.invalid` |
| `SEED_CHANGEOVER_MINUTES` | no | defaults to 20 (ASSUMED), 0..50 |
| `BCRYPT_COST`, `PASSWORD_MIN_LENGTH` | no | the api's own defaults (12 and 12); set them the same as the api's if you changed them there |

Exit codes: **0** seeded (or nothing was missing); **78** a variable is missing or refused — nothing was
written; **1** the seed refused part-way — the whole run is one transaction, so nothing was written.
A second run inserts nothing: it is keyed on the seeded names and addresses, and it never resets a
password someone changed by hand.

stdout carries the one `NOTICE:` line, then `admin: 1`, `manager: 12`, `customer: 50`, each followed by
the addresses. It never carries the password.

**Not ready yet, stated rather than discovered.** In the current tree the image's entrypoint accepts
`api` and `migrate` only, and the image does not contain `scripts/`. Both are owed by the build session
(Zone B) before this task can run; until then `seed` exits 64 as an unknown command. Running the seed
from a laptop against RDS is not a substitute: RDS sits behind security groups that should not admit it.

## Acceptance criteria

1. The task definition family is used by this task only; neither the api's nor the worker's task
   definition mentions `SEED_DEFAULT_PASSWORD`.
2. The parameter is a `SecureString` at the path above, and only this family's execution role can read it.
3. One run exits 0 and its log shows the `NOTICE:` line and the three account counts, and no line in
   the log group contains the password.
4. A second run exits 0 and inserts nothing.
5. Acceptance criterion: sign in as admin-01@ with the value that was stored.

## Common mistakes

- **Adding the parameter to the api task definition "so it is all in one place".** The api then holds
  a credential for 63 accounts it never uses, and anyone who can read that task definition's
  environment can sign in as the admin.
- **Granting `ssm:GetParameters` to the task role.** The task dies at `PENDING` with a
  `ResourceInitializationError` and no application log line, because the secret is resolved before the
  container exists.
- **Running the seed before the halls' seat labels are final.** See the first section: after the first
  showtime row there is no undo in this environment.
