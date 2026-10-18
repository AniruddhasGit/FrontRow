# Phase 1 close-out: the skeleton, and what to test on your own deployment

> Written for the client (`SRC-002 §12`, PRD `P-XCT-27`). Phase 1 closes when this file carries the four
> sections below and the steps under *What to test* pass on the environment you built. The build
> session has never seen this application run on AWS; every sentence about AWS behaviour is
> *(reasoned, not observed)*.

## What was built

- **The api container** (`backend/`): Python 3.12 and FastAPI, one process, one uvicorn worker. It
  serves `/health/live` and `/health/ready`, writes one JSON object per log line to stdout with an
  8-character request id, answers every error in one envelope, and drains in-flight requests on SIGTERM
  before exiting 0.
- **Configuration validated at boot**: the whole PRD S7.9 inventory, thirteen variables with no
  default and thirteen cross-field checks. A missing or wrong value exits 78 with one JSON line naming
  it, before the port is bound.
- **The frontend container** (`frontend/`): the React build served by nginx on port 8080. No Node
  process runs in production.
- **`docker-compose.yml`**, for local development only: PostgreSQL 16, Redis 7, the api and the frontend.
- **The Zone C specifications** in this folder, one per item the Phase 1 deployment needs, each queued
  in `AWS_PREP_QUEUE.md` with the phase that needs it.

## Why it is built that way

- **Two health endpoints that behave differently** (`SRC-002 §7.4`): the restart check must not touch a
  dependency, or a database blip restarts every container; the load balancer check must, or traffic is
  sent to an instance that cannot serve it.
- **Exit at boot instead of starting half-configured** (`SRC-002 §7.1`): a container that starts,
  connects to nothing and reports healthy is worse than one that never starts.
- **JSON to stdout, never a file** (`SRC-002 §5.4.5`, `§7.6`): a file dies with the container; stdout is
  collected by the `awslogs` driver.
- **A read-only root filesystem and a non-root user**: the container holds no state, and a code
  execution bug is not root.
- **Migrations are a separate command, never run on boot** (`SRC-002 §7.8`): two tasks starting
  together would race on the same schema change.

## What breaks in production if the deployment is got wrong

- **The target group health check on `/health/live` instead of `/health/ready`**: traffic is routed to
  an instance whose database is down. The reverse wiring on the container check restarts every
  container on every database blip. *(reasoned, not observed)*
- **A target group or security group port that is not `API_PORT` (8000)**: every task starts and
  reports healthy to Docker, and the load balancer drains all of them. *(reasoned, not observed)*
- **A variable missing from the task definition**: the task exits 78 and ECS keeps replacing it. The
  stopped-task reason and the one JSON line in CloudWatch name the variable.
- **An ECS stop timeout shorter than the drain**: SIGKILL lands mid-request. *(reasoned, not observed)*
- **The task role given the SSM permission instead of the execution role**: the task never leaves
  `PENDING` and no application log line is ever written. *(reasoned, not observed)*

## What to test

1. Start the api task with every variable from `P1_SSM_PARAMETERS.md`. Its log stream shows
   `configuration resolved` once, with every URL and secret as `[REDACTED]` and `PAYMENT_PROVIDER`
   reading `simulated`.
2. `GET http://<alb-dns-name>/health/ready` returns 200 with
   `{"status": "ready", "checks": {"postgres": "ok", "redis": "ok"}, "payment_provider": "simulated"}`.
3. Stop RDS (or point `DATABASE_URL` at a wrong host and redeploy). `/health/ready` turns 503 naming
   postgres, the target turns unhealthy, and the container is **not** restarted.
4. Remove `JWT_SECRET` from the task definition and deploy. The task exits 78 and the log names
   `JWT_SECRET`. Put it back.
5. Stop the api service. The alarm in `P1_TASK_COUNT_ALARM.md` goes to `ALARM` and the email arrives.
6. Stop one running api task. Its exit code is 0 and its log stream ends with `api stopped cleanly`.
