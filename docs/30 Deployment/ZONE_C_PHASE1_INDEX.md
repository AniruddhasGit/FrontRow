# Zone C, Phase 1: what to build on AWS, in what order, and how you will know it works

> **Specifications only** (`SRC-002 §6.4`, `§6.5`). Each file says what to build, what the application
> expects of it, how to check it, and the two or three mistakes people usually make. **None of them
> gives you the answer.** No console clicks, no CLI create commands, no JSON task definition. Those
> are yours to write and to get wrong.
>
> **The build session has never seen this application run in AWS.** Every sentence here about how an
> AWS service behaves is **(reasoned, not observed)**. What *is* observed is the application's side,
> measured locally on 2026-10-18 (GOAL_14 gate). Those figures are quoted, and labelled as local
> measurements.
>
> Written by GOAL_14 (Phase 1 skeleton), 2026-10-18.

## What Phase 1 deploys

Two images, built from this repository:

| Image | Built from | Listens on | Liveness | Measured locally |
|---|---|---|---|---|
| `frontrow-api` | `backend/Dockerfile` (default target `runtime`) | `API_PORT`, default **8000** | `GET /health/live` | 239 MB by `docker images`, 56.5 MB compressed · ~50 MiB resident at idle |
| `frontrow-frontend` | `frontend/Dockerfile` | **8080** | `GET /index.html` | 73.9 MB by `docker images`, 21.0 MB compressed · ~2–3 MiB resident at idle |

The worker is not part of Phase 1. It arrives in Phase 5.

## The specifications, in the order to build them

| # | File | Prep-queue row | What it covers |
|---|---|---|---|
| 1 | [`P1_NETWORK_SECURITY_GROUPS.md`](P1_NETWORK_SECURITY_GROUPS.md) | 4 | VPC, public subnets, the security groups |
| 2 | [`P1_IAM_ROLES.md`](P1_IAM_ROLES.md) | 12, 15 | the instance role, the execution role, the task role |
| 3 | [`P1_ECR.md`](P1_ECR.md) | 1 | two image repositories and the 500 MB limit |
| 4 | [`P1_CLOUDWATCH_LOGS.md`](P1_CLOUDWATCH_LOGS.md) | 7 | log group, retention, the `awslogs` driver |
| 5 | [`P1_SSM_PARAMETERS.md`](P1_SSM_PARAMETERS.md) | 6 | where `DATABASE_URL` and `REDIS_URL` live |
| 6 | [`P1_EC2_ECS_CLUSTER.md`](P1_EC2_ECS_CLUSTER.md) | 2 | one `t3.micro` registered to an ECS cluster |
| 7 | [`P1_TASK_DEFINITIONS.md`](P1_TASK_DEFINITIONS.md) | (part of 2) | api, frontend, and the one-off `migrate` task |
| 8 | [`P1_ALB.md`](P1_ALB.md) | 3 | load balancer, two target groups, health check paths |
| 9 | [`P1_ECS_SERVICES.md`](P1_ECS_SERVICES.md) | 18 | two services, and what a deploy costs |
| 10 | [`P1_TASK_COUNT_ALARM.md`](P1_TASK_COUNT_ALARM.md) | 13 | the one alarm, and who it emails |

## Read this before you start: Phase 1 on AWS cannot pass readiness without a database and a Redis

`/health/ready` returns 200 only when PostgreSQL answers `SELECT 1` **and** Redis answers `PING`
(`SRC-002 §7.4`). The load balancer's target group health check must point at `/health/ready`. So:

- **With no RDS instance and no ElastiCache node, the api target is never healthy**, and the load
  balancer returns errors for every request routed to it. This is the application behaving correctly.
- The prep queue lists RDS as *needed by Phase 2* (row 5) and ElastiCache as *needed by Phase 3*
  (row 8). Those stages describe when the **application's features** need them. For **a healthy api
  target in Phase 1**, both are needed by Phase 1. The queue rows now say so.

You have two legitimate ways through Phase 1. This is your choice; neither is a defect:

1. **Build RDS and ElastiCache now**, set `DATABASE_URL` and `REDIS_URL` to them, and see the
   api target go healthy. Check the cost first: free-tier hours for `db.t3.micro` and
   `cache.t3.micro` are per account and are shared with SpendWise in this account
   (`OPS_SESSION_BRIEF.md`), and the ElastiCache free tier only covers accounts in their first 12 months.
2. **Deploy without them first and watch the 503.** Point `DATABASE_URL` and `REDIS_URL` at
   placeholder hostnames. The container starts, `/health/live` passes, `/health/ready` is 503 naming
   both dependencies, and the target stays unhealthy. That is the readiness/liveness split doing its
   job. Then build RDS and ElastiCache and see it recover without a redeploy.
   **This is not "pointing the health check at `/health/live` to make it go green".** Doing that is
   the mistake every one of these specifications warns about.

Either way, **the frontend target becomes healthy on its own**. It has no dependencies.

## Phase 1 acceptance, end to end

Phase 1 on AWS is done when all of these hold. The build session checks each one with read-only
`describe` / `list` / `get` calls and records the output.

1. Both images are in ECR, tagged with something other than only `latest`.
2. One `t3.micro` is registered to the cluster and reports its remaining memory.
3. Two services, api and frontend, each run exactly one task.
4. The frontend target group shows its target `healthy`, and `http://<alb-dns>/` returns the Phase 1 page.
5. The api target group's health check path is `/health/ready`. The target is `healthy` if you took
   option 1, or `unhealthy` with reason "health checks failed with these codes: [503]" if you took option 2.
6. The api task definition's container health check, if one is set, calls `/health/live`.
7. The api's log lines appear in CloudWatch Logs as JSON, each with a `request_id`.
8. Stopping the api task by hand, then reading its log stream, shows `stop signal received` followed
   by `api stopped cleanly`, and the stopped task's exit code is **0**.
9. Removing `DATABASE_URL` from the task definition makes the next task stop with exit code **78**.
   CloudWatch then holds one line: `DATABASE_URL is required and is not set`. Put it back afterwards.
10. Nothing in the account belonging to SpendWise was changed.

## The application's contract, in one place

| The app expects | Value | Where it is specified |
|---|---|---|
| api container port | `8000` (`API_PORT`; must be ≥ 1024, because the process is not root) | task definitions, ALB, security groups |
| frontend container port | `8080` | same |
| load balancer health check, api | `GET /health/ready`, 200 = healthy, 503 = not | `P1_ALB.md` |
| restart / container health check, api | `GET /health/live`, never `/health/ready` | `P1_TASK_DEFINITIONS.md` |
| health check, frontend | `GET /index.html` (any static file) | `P1_ALB.md` |
| SIGTERM to drain | up to `SHUTDOWN_DRAIN_TIMEOUT_SECONDS` = 20 s | `P1_TASK_DEFINITIONS.md`, `P1_ALB.md` |
| readiness cache | `READINESS_CACHE_TTL_SECONDS` = 3 s | `P1_ALB.md` |
| required variables | the thirteen with no default (`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `QUEUE_URL`, `COOKIE_SECURE`, ...): exit 78 if any is missing, and 78 if any of thirteen cross-field checks fails | `P1_SSM_PARAMETERS.md` |
| logs | JSON on stdout. The app never writes a file | `P1_CLOUDWATCH_LOGS.md` |
| filesystem | read-only root works. Measured locally: 0 paths changed | `P1_TASK_DEFINITIONS.md` |
| outbound AWS calls made by the app in Phase 1 | **none**. The app calls no AWS API until Phase 5 | `P1_IAM_ROLES.md` |
| migrations | never on boot. A separate `migrate` command, a one-off task. In Phase 1 it applies nothing and exits 0 | `P1_TASK_DEFINITIONS.md` |
