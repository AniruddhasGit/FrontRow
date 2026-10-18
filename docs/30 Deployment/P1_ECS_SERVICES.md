# P1 · ECS services and deployment configuration  (prep-queue row 18 · needed by Phase 1)

> Zone C specification (`SRC-002 §6.3.2`). What to build, not how. Every claim about AWS behaviour is
> **reasoned, not observed**.

## 1. What you need to build

- **Two services** in the cluster, **api** and **frontend**, each with a desired count of **1**, each
  attached to its own target group. A third, the worker, comes in Phase 5 (`SRC-002 §7.2`: the
  processes scale independently, so they are separate services).
- A **deployment configuration** for each that can complete on a single `t3.micro`.

## 2. What the application expects

- **The application is stateless** (`SRC-002 §7.3`). Killing a task mid-request corrupts nothing.
  Measured locally: no file is written; the root filesystem is read-only.
- **A replacement task is identical to the one it replaces.** Nothing about a request depends on which
  task served the previous one.
- **One host, one copy at a time.** With a fixed host port, a second api task cannot start on the same
  instance while the first holds the port. ECS's default deployment then waits for a healthy second
  task that can never be placed, and the deploy hangs rather than failing (prep-queue row 18). The
  usual way through is minimum healthy 0 % and maximum 100 %. **That means a hard downtime window on
  every deploy.** It is a real trade, so choose it deliberately rather than discover it.
- **Graceful stop on every deploy**: SIGTERM, drain (≤ 20 s), exit 0, as proved locally. This only
  holds if the shutdown ordering in `P1_TASK_DEFINITIONS.md` is satisfied.

## 3. Acceptance criteria

1. Two services exist, each with desired 1 and running 1.
2. Each is attached to its target group (api → api, frontend → frontend), on the right container port.
3. Pushing a new image tag and updating the api service completes, with no manual step, within a few
   minutes, and the old task's log stream ends with `api stopped cleanly`.
4. The deployment configuration values are written in the prep queue, with the downtime window you
   accept stated next to them.

## 4. Common mistakes

- **Default deployment settings on one host.** The deploy shows "in progress" indefinitely. Nothing
  fails, so nothing alerts.
- **The api service attached to the frontend's target group** (or on port 80). Every health check then
  fails, and ECS keeps replacing a task that is working.
- **Treating a stuck deploy as a broken image.** If the new task never starts, read the service
  events first. "Unable to place a task" is a capacity or port problem, not an application one.
