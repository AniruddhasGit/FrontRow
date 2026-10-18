# P1 · ECS task definitions: api, frontend, and the one-off `migrate`  (part of prep-queue row 2 · needed by Phase 1)

> Zone C specification (`SRC-002 §6.3.2`). What to build, not how. Every claim about AWS behaviour is
> **reasoned, not observed**.

## 1. What you need to build

- **An api task definition**: one container from the api image, default command (`api`).
- **A frontend task definition**: one container from the frontend image.
- **A `migrate` task definition, its own family**: the api image, command `migrate`, run as a
  standalone task (PRD `P-XCT-19`). Not a service. It connects as the table **owner**, from its own SSM
  parameter, so it needs a task definition of its own: `secrets` cannot be swapped by a run-task
  override, and putting the owner credential on the api task gives the running API the power the
  owner/application split exists to deny it (prep-queue rows 20 and 24). In Phase 1 it applies nothing,
  logs `migrate: no migrations exist in Phase 1; nothing was applied`, and exits 0. Run it once anyway,
  so the procedure is learned before it matters.

Network mode: **bridge** on the instance. `awsvpc` gives each task its own network interface, and a
`t3.micro` has too few to place three services (`04_deployment.md`, AWS-04-06).

## 2. What the application expects

| Setting | api | frontend | Why |
|---|---|---|---|
| container port | **8000** | **8080** | both processes run as a non-root user and cannot bind below 1024 |
| host port | your choice: fixed, or `0` for a dynamic one | same | fixed means two copies cannot run on one host (`P1_ECS_SERVICES.md`). Dynamic means the security group must allow the dynamic port range from the LB |
| memory hard limit | set one (the architecture budgets 200 MiB; ~50 MiB measured idle) | set one (15 MiB budgeted; ~2–3 MiB measured idle) | a container with no limit can take the host down with it (PRD `P-XCT-21`) |
| container health check | **`/health/live`** on port 8000, if you define one | a static file on 8080, if you define one | **never `/health/ready`**. A failing container health check gets the container **killed and replaced**, and a replacement cannot fix the database |
| read-only root filesystem | **on** | **on**, with a writable `/tmp` for nginx's pid and temp files | proved locally: the api changed 0 paths, nginx needs only `/tmp` |
| stop timeout | must satisfy the ordering below | — | otherwise SIGKILL lands mid-drain |
| user | leave as the image's (uid 10001 for the api, `nginx` for the frontend) | same | setting root here undoes the Dockerfile |
| logging | `awslogs` (`P1_CLOUDWATCH_LOGS.md`) | same | |
| `secrets` / `environment` | per `P1_SSM_PARAMETERS.md` | none needed | |

**The container health check command.** The api image has **no `curl`** (it was left out to save
space). The Dockerfile's own `HEALTHCHECK` uses Python's standard library; read it in
`backend/Dockerfile`. **ECS ignores a Dockerfile's `HEALTHCHECK`** (reasoned, not observed), so if you
want a container-level check on ECS you must write one in the task definition. Note that a health check
that starts a Python interpreter every 30 seconds costs a few MB and a little CPU each time.

**The shutdown ordering (PRD `P-XCT-17`), and it fails silently when wrong.** ECS deregisters the
target and waits out the deregistration delay **before** it sends SIGTERM. The stop timeout counts
from SIGTERM to SIGKILL. So the requirement is:

```
ECS stop timeout  >  SHUTDOWN_DRAIN_TIMEOUT_SECONDS (20)  +  time to release holds and exit
```

The stricter safe bound, which holds whichever way the order turns out (the order is reasoned, not
observed), is `stop timeout > deregistration delay + 20`. The container `stopTimeout` on EC2 is
capped at about 120 s (from AWS documentation, not observed), so meeting the strict bound means
lowering the deregistration delay below about 100 s.

Measured locally: SIGTERM 1 s into a 5-second request. The request completed with HTTP 200, the
process exited **0**, and the shutdown took **3742 ms** from signal to exit. An idle api stopped in ~200 ms.

## 3. Acceptance criteria

1. Both task definitions exist. The api's names container port 8000, the frontend's 8080.
2. Both set a hard memory limit, and the api's limit sits within the architecture's budget unless you
   have a measured reason to change it. (Tell the build session the number if you change it.)
3. If the api task definition has a container health check, its command calls `/health/live`.
4. Both declare a read-only root filesystem, and both reach `RUNNING`.
5. The stop timeout exceeds the 20 s drain with margin, and preferably the strict bound too
   (stop timeout > deregistration delay from `P1_ALB.md` + 20). Write both values in the prep queue.
6. A standalone run of the **`migrate` task definition**, its own family and not the api's, exits 0
   and logs its one line. That task definition injects the owner `DATABASE_URL` from its own SSM
   parameter, and the api task definition does not reference that parameter (prep-queue row 24).
7. Stopping a running api task gives exit code **0**, and its log stream ends with `api stopped cleanly`.

## 4. Common mistakes

- **Health check on `/health/ready`.** Every RDS or Redis blip then restarts the api container, and a
  restart loop replaces a ten-second outage.
- **Putting `migrate` in front of `api` in the command** ("so it is always up to date"). That runs
  migrations on every boot, and two tasks starting together race on the same schema change.
  `SRC-002 §7.8` forbids it, and the entrypoint keeps them separate on purpose.
- **Leaving the stop timeout at the default and the deregistration delay at its default.** The
  defaults fail the strict bound (`04_deployment.md`, AWS-04-04). The 30 s default stop timeout meets
  the real requirement with only a few seconds to spare, so a slow drain is SIGKILLed mid-drain. In Phase 1 that only cuts off requests. From Phase 4 it also strands seat holds for
  up to three minutes.
