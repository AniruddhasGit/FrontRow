# Project Build Brief — Movie Ticket Booking Platform

**Read this entire file before writing any code.**

---

## 1. Who I am and what I am trying to achieve

I am a developer learning **DevOps** and **systems design**. I am not building this
product to sell it. I am building it so that deploying and operating it teaches me
real infrastructure skills.

My split of work is deliberate:

- **You write the application.** I do not want to spend my time on business logic,
  React components, or SQL schemas.
- **I do the deployment.** Docker builds, ECR pushes, ECS services, load balancers,
  networking, CI/CD pipelines, monitoring. That is the part I want to struggle with.

So your job is not only to produce working code. Your job is to produce an application
whose **shape forces me to learn DevOps properly** when I deploy it.

You have full autonomy over implementation choices inside the constraints below. If you
believe a different approach teaches me more, take it, but write down why in
`docs/decisions.md`.

---

## 2. How I want things explained to me

- Explain at the level of a 22 year old who can code but has never run production infrastructure.
- No figures of speech, no analogies, no metaphors. Say the literal thing.
- Prefer short paragraphs over long bulleted instruction dumps.
- When you finish a phase, write a short explanation file in `docs/` covering what you
  built, why it is built that way, and what will break in production if I get the
  deployment wrong.

---

## 3. The product in one paragraph

A movie ticket booking website. Users browse movies currently showing, pick a cinema,
pick a showtime, see a live seat map for that show, select seats, and confirm a booking.
Selected seats are locked for a short window while checkout happens, and released
automatically if checkout is abandoned. Movie data is pulled automatically from a public
movie API on a schedule, so the site always shows current releases. Admins manage cinemas,
screens, showtimes, and pricing.

---

## 4. Technology stack (fixed)

| Layer | Choice |
|---|---|
| Frontend | React + Vite, TypeScript |
| Backend | Python 3.12, FastAPI |
| Database | PostgreSQL (AWS RDS in production, container locally) |
| Cache and locks | Redis (AWS ElastiCache in production, container locally) |
| Async work | A separate worker process consuming AWS SQS |
| Scheduled jobs | A scheduler process, or a Lambda invoked by EventBridge |
| Migrations | Alembic |
| Auth | Own email + password with JWT. Do not use Cognito |
| Object storage | S3 for movie posters we cache ourselves |
| Container runtime | Docker, run on ECS backed by EC2 |
| Load balancing | AWS Application Load Balancer |

Do not introduce Kubernetes, Fargate, service meshes, or any managed service outside
this list without asking me first.

---

## 5. Hard constraint: AWS Free Tier

Everything must be able to run inside AWS Free Tier limits.

**Available to me for free:**
- One `t3.micro` EC2 instance, 750 hours a month, 1 GB RAM
- One `db.t3.micro` RDS PostgreSQL instance, 20 GB storage
- One `cache.t3.micro` ElastiCache Redis node, 750 hours
- Application Load Balancer, 750 hours
- S3 5 GB, ECR 500 MB, SQS 1M requests, SNS, Lambda 1M requests
- CloudWatch basic metrics and 5 GB of logs

**Not available, do not design around them:**
- EKS, Fargate, NAT Gateway, AWS Secrets Manager, Managed Grafana, OpenSearch

**What this means for your code:**
1. Total memory budget across all my containers is about 1 GB. Set explicit memory
   limits. Keep the Python image slim. Prefer `RQ` or `Dramatiq` over Celery.
2. ECR only stores 500 MB, so use multi-stage Docker builds and a slim base image.
   Target a final image under 250 MB.
3. Use **SSM Parameter Store** for secrets, not Secrets Manager.
4. Because I have no NAT Gateway, design the app so it can run in a public subnet with
   strict security groups, and note anywhere the app needs outbound internet access.
5. Log to stdout as JSON. Do not write log files to disk.

---

## 6. Work zones — this is the most important section

### Zone A — You build this completely

- All backend application code, routers, services, models, migrations
- All frontend code and styling
- The seat locking and booking logic
- The movie sync job that calls the third party API
- Unit and integration tests
- Database seed scripts with sample cinemas, screens, and showtimes
- `docker-compose.yml` for **local development only**
- A load testing script (see section 9)

### Zone B — You write it, but heavily commented, because I must understand and edit it

- The production `Dockerfile` for each service
- Container entrypoint scripts
- Health check and readiness endpoints
- Environment variable configuration and validation
- Graceful shutdown handling

Every line in Zone B that exists for a production reason gets a comment saying what
breaks without it.

### Zone C — Do NOT write these. This is my homework.

- Terraform or CloudFormation
- ECS task definitions and service definitions
- ALB, target group, listener rule, or security group configuration
- VPC and subnet layout
- GitHub Actions or any CI/CD pipeline
- CloudWatch alarms and dashboards
- Any `aws` CLI commands that create infrastructure

Instead of writing these, produce **`docs/deployment-tasks.md`** containing, for each
Zone C item:
1. What I need to build
2. What the application expects from it (ports, health check paths, env vars, IAM
   permissions needed)
3. Acceptance criteria so I know when I got it right
4. Two or three common mistakes people make on that step

Do not give me the answer. Give me the specification and let me fail against it.

---

## 7. Application design requirements that exist purely to teach me DevOps

Build the app so that it is impossible to deploy without learning these things.

1. **Twelve-factor config.** Every setting comes from environment variables. The app
   must crash on startup with a clear message if a required variable is missing.
2. **Separate processes.** The API and the background worker must be different
   containers from the same or different images, scaled independently.
3. **Stateless containers.** No local session state, no local file uploads. Killing any
   container mid-request must not corrupt data.
4. **Health endpoints.** `/health/live` returns 200 if the process is alive.
   `/health/ready` returns 503 if the database or Redis is unreachable. These must behave
   differently, because the load balancer treats them differently.
5. **Graceful shutdown.** On SIGTERM, stop accepting new requests, finish in-flight ones,
   release Redis locks held by that instance, then exit.
6. **Structured logging.** JSON to stdout, with a request ID propagated through every
   log line, including worker jobs triggered by that request.
7. **A `/metrics` endpoint** in Prometheus format, exposing request counts, latency,
   seat lock counts, and queue depth.
8. **Database migrations run as a separate step**, never automatically on app boot.
   I need to learn why that distinction matters.
9. **Fail loudly on dependency loss.** If Redis is down, do not silently fall back to
   the database for locks. Return an error. I need to see the failure.

---

## 8. Systems design requirements

These are the concepts I want to learn by operating this app.

**Seat locking**
- When a user selects seats, place a lock in Redis with a TTL of 7 minutes, keyed per
  showtime and seat.
- The lock must be acquired atomically. Two users clicking the same seat at the same
  millisecond must produce exactly one winner.
- Use a lock token so a client can only release a lock it owns.
- On lock expiry, the seat becomes available again with no cleanup job needed.
- Confirming a booking must also take a database-level guard, so that Redis being wrong
  cannot oversell a seat. Use a unique constraint on `(showtime_id, seat_id)` plus
  optimistic locking or `SELECT ... FOR UPDATE`.

**Caching**
- Cache the seat map per showtime with a short TTL, invalidated on any booking or lock
  change. Use cache-aside.
- Cache the movie list and showtime list, which are read constantly and change rarely.
- Document in code where a cache stampede could happen and how you prevented it.

**Idempotency**
- The booking confirmation endpoint takes an `Idempotency-Key` header. Retrying the same
  key returns the original result rather than creating a second booking.

**Rate limiting**
- Token bucket in Redis on seat selection and booking endpoints, per user and per IP.
- Return 429 with a `Retry-After` header.

**Queueing**
- After a booking is confirmed, push a message to SQS. The worker sends the confirmation
  email and generates the ticket QR code.
- Handle retries and configure a dead letter queue path. Make failures visible.

**Live seat map**
- Start with polling every 3 seconds, because it is simple and works behind any load
  balancer.
- Structure the code so I can switch to WebSockets later as a second exercise, and write
  a note in `docs/` explaining what changes on the load balancer when I do.

---

## 9. Concurrency proof

Write a script, `scripts/stress_seats.py`, that fires 50 simultaneous requests for the
same seat and asserts exactly one succeeds. This must run against local Docker and
against my deployed environment by changing a base URL.

Also write a light load test I can point at the ALB to see autoscaling behaviour.

---

## 10. Movie data sync

Use **TMDB** (The Movie Database).

- Free developer API key, and it is free for non-commercial use provided TMDB is
  credited as the data and image source. Put that attribution in the site footer.
- Base URL `https://api.themoviedb.org/3`
- Useful endpoints: `/movie/now_playing`, `/movie/upcoming`, `/movie/{id}`,
  `/discover/movie`. Support a `region` parameter so I can point it at one country.
- Read the key from an environment variable. Never commit it.

Requirements for the sync job:
1. Runs on a schedule, roughly daily. Implement it so it can be triggered three ways:
   a CLI command, an HTTP endpoint protected by an admin token, and a scheduled trigger.
   That way I can wire it to EventBridge or a cron container and compare the two.
2. Upsert by TMDB movie ID. Running it twice must not create duplicates.
3. Download posters once, store them in S3, and serve our own URLs. Do not hotlink.
4. Handle TMDB rate limits with backoff, and log every sync run with counts of created,
   updated, and skipped records.
5. New movies land in a `pending` state. An admin publishes them before they appear.
   Showtimes are never created automatically.
6. If TMDB is unreachable, the sync fails cleanly and the site keeps working with
   existing data.

---

## 11. Repository layout

Use a monorepo. Make the boundaries obvious, because I need to be able to point a
Dockerfile at each service independently.

```
.
├── backend/
│   ├── app/
│   │   ├── api/            # routers
│   │   ├── core/           # config, logging, security
│   │   ├── domain/         # booking, locking, pricing logic
│   │   ├── models/
│   │   ├── workers/        # SQS consumer
│   │   ├── jobs/           # TMDB sync
│   │   └── main.py
│   ├── migrations/
│   ├── tests/
│   └── Dockerfile
├── frontend/
│   ├── src/
│   └── Dockerfile
├── scripts/
│   ├── seed.py
│   └── stress_seats.py
├── docs/
│   ├── architecture.md
│   ├── decisions.md
│   ├── deployment-tasks.md
│   └── runbook.md
├── docker-compose.yml       # local development only
├── .env.example
└── README.md
```

---

## 12. Build order

Do not build everything at once. Stop at the end of each phase and tell me what to test.

1. **Phase 1** — Repo skeleton, config loading, health endpoints, structured logging,
   local docker-compose with Postgres and Redis. Nothing else. I deploy this to ECS
   before we go further, so I learn the pipeline against something trivial.
2. **Phase 2** — Data model, migrations, seed data, admin CRUD for cinemas, screens,
   showtimes, and pricing.
3. **Phase 3** — Public browsing pages, movie list, showtime list, seat map read path,
   with caching.
4. **Phase 4** — Seat locking, booking confirmation, idempotency, the concurrency test.
5. **Phase 5** — SQS worker, confirmation emails, QR tickets, dead letter handling.
6. **Phase 6** — TMDB sync job and admin publishing flow.
7. **Phase 7** — Metrics endpoint, rate limiting, load testing script, runbook.

---

## 13. Rules

- Ask me before adding any dependency that is not obviously necessary.
- Do not run any `aws` command.
- Do not write anything listed in Zone C.
- Do not commit secrets. Ship a complete `.env.example`.
- When you make a decision I did not specify, record it in `docs/decisions.md` with the
  reason and the alternative you rejected.
- If a requirement in this file will not fit in 1 GB of RAM, tell me instead of quietly
  working around it.
