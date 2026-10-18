# 01 — Executive overview

> **compressed per SRC-004 R-1.** Written for someone who can code but has never run infrastructure
> (`SRC-002 §2`): plain statements, no analogies. Precise versions of everything here are in
> `../for_llm/`.

## What gets built

Three programs run all the time, from two Docker images:

1. **api** — the Python FastAPI server. Every request from a browser goes to it, except requests for
   the web page files themselves. It talks to PostgreSQL, Redis, the queue and S3.
2. **worker** — the same Python image started with a different command. It reads jobs from the queue
   and sends emails through SES: booking receipts and password-reset links. It never answers web
   requests.
3. **frontend** — a small web server that hands out the built React files. It runs no application
   code.

Two more commands run once and exit: **migrate** (changes the database schema; never runs on its own
when the api starts) and **seed** (writes the starting halls, seats and accounts).

## How a seat is protected from being sold twice

There are two separate protections, in two separate systems, and the second one is the one that
cannot be switched off.

- **Redis holds the seat for 3 minutes.** When a customer picks seats, the api writes one Redis key per
  seat, in one command that both claims the key and sets it to delete itself after 180 seconds. The
  key holds a random value only that customer's browser knows. Only a request carrying that value can
  release it early. If two customers click the same seat in the same millisecond, Redis accepts exactly
  one of the two writes.
- **PostgreSQL refuses a second sale.** The table of sold seats has a rule that one showtime and one
  seat may appear only once. If Redis ever loses or mis-hands a key — a restart, an expiry at the wrong
  moment, a bug — two customers can both reach payment, and the database then refuses the second
  booking. That customer is told the seat was taken and is not charged.
- **The proof.** A script fires 50 simultaneous requests for one seat and checks, by counting rows in
  the database, that exactly one booking exists. Then the database rule is removed on purpose on a local
  copy, Redis is made to lose a key by hand, and the script must show **two** bookings for one seat —
  proving the database rule is what stops it. The rule is restored and checked.

## What happens after a customer pays

1. The booking, the payment record, a receipt-tracking row and a queue job are all written in one
   database transaction. Either all of them exist or none do.
2. Right after that, the api puts the job on the queue and returns the booking. The booking reference
   is shown on screen at once, whether or not the email ever arrives.
3. The worker takes the job, marks the receipt as being sent (so no second worker sends it again), and
   calls SES.
4. If putting the job on the queue failed, the worker finds the unsent job in the database within about
   half a minute and sends it then. **Nothing runs on a timer** — this check happens each time the
   worker goes back to wait for jobs.

## What changed on 2026-10-18 (`SRC-004`)

- **Password reset links**: the secret in the link now travels inside the queue message, as you ruled.
  The database keeps only a fingerprint of it (its SHA-256). To keep the queue copy short-lived, this
  design uses **a second queue just for reset links**, which you configure to keep a message no longer
  than 30 minutes — the same time the link stays valid. Receipts keep their own queue with a long retention. The price of your
  ruling: if the api cannot reach the queue at the moment someone asks for a reset, that email is never
  sent and they have to ask again. The build session accepted that under `SRC-004 R-6` (`JC-R6-01`); you may reverse it — see
  `02_decisions_owed.md`.
- **Seat row labels** are stored in capitals, and the database enforces it. `I` is allowed.
- **Booking references** use 26 characters (no `0 1 I L O U Z S B G`) — seven random ones plus one
  check character at the end, eight in total, printed `FR-XXXX-XXXX` as before. The check character catches every single mistyped
  character and every pair of swapped neighbours — **when software reads the reference**. At the door
  nobody runs software, so there it catches nothing unless a person works it out.
- One correction this goal found: the note filed under `SRC-004 R-5` said a weighted sum over 26
  characters would catch both kinds of mistake. It cannot — this was checked by trying every
  possibility. A different, standard method (a dihedral-group check, the same family as the Verhoeff
  check digit) was picked and checked over 620,212 test mistakes on 8-character references with none missed. The note needs a
  formal correction (an `ERRATUM`), which is asked of the governance lane.

## Does it fit in 1 GB?

**On estimates, yes.** The operating system, Docker and the ECS agent are estimated at 300–400 MiB;
the three programs are capped at 365 MiB together; that leaves 259–359 MiB unused, and 109–209 MiB
while a migration runs. **None of these numbers has been measured** — nothing has run yet. If the api
turns out to need 300 MiB instead of 200, a migration run alongside it would no longer fit in the worst
case, and you will be told that with the measured number. Full arithmetic: `../for_llm/04_deployment.md`.

## What you build (Zone C), and what this folder gives you instead

You build the load balancer, the ECS cluster and services, the task definitions, the VPC and security
groups, the queues, the alarm, and everything else in AWS. This folder states what the application
needs from each — for example: the load balancer's health check must call `/health/ready`; the ECS stop
timeout must be longer than the api's 20-second drain (the load balancer's deregistration delay runs
before the api is signalled, `../for_llm/04_deployment.md` AWS-04-12; adding the delay to the 20 seconds is the stricter safe bound); the
reset queue must keep messages no longer than 30 minutes — and what goes wrong if it does not. The
resource list with the phase each is needed by is `docs/30 Deployment/AWS_PREP_QUEUE.md`. **This goal
found six AWS needs**, A-1 to A-6 in `02_decisions_owed.md`, which maps each to its prep-queue row.
Most were already rows (21, 22, 23, 24, 25, and 3 with 28). The parts that were not are now rows
**29** (worker and migrate/seed memory limits), **30** (the frontend's second target group and the
`/api/*` listener rule) and **31** (the reset queue's visibility timeout under 900 s).

**Nothing here has run in AWS.** Every statement about how AWS will behave is reasoning and is
labelled that way where it appears.
