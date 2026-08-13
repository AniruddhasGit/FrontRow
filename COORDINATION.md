# COORDINATION.md — live map for parallel work

Read this when **two or more sessions run at once**. On this project that is the normal case: a
build session writes application code while a DevOps session builds AWS by hand.

When only one session is running, this file is informational.

---

## The two standing lanes

| Lane | Owner | Owns | Never touches |
|---|---|---|---|
| **BUILD** | the application session | `backend/**` · `frontend/**` · `scripts/**` · `docs/**` · `docker-compose.yml` · the production Dockerfiles and entrypoints (Zone B) | anything created in AWS · `.github/workflows/**` · Terraform or CloudFormation · ECS task and service definitions · ALB, target group, listener or security group configuration · VPC and subnet layout · CloudWatch alarms and dashboards |
| **OPS** | the client's separate DevOps session | the AWS console and CLI · `.github/workflows/**` · all Zone C configuration · `docs/30 Deployment/AWS_PREP_QUEUE.md` tick-offs | `backend/**` · `frontend/**` · `scripts/**` · `docs/00`–`docs/15` |

**The lanes are disjoint by design** (`SRC-002 §6.3`). The build session creates nothing in AWS; the
DevOps session writes no application code.

Where they meet is exactly three files:

- **`docs/30 Deployment/AWS_PREP_QUEUE.md`** — BUILD writes the requests with a *needed by* stage,
  OPS marks them done and records what was actually created.
- **`docs/30 Deployment/`** Zone C specifications — BUILD writes what to build, what the application
  expects, the acceptance criteria and the common mistakes. OPS builds against them and records the
  result. **BUILD does not write the answer** (`SRC-002 §6.5`).
- **`.env.example`** — BUILD adds the keys the application needs; OPS supplies the real values into
  `.env` (gitignored) or SSM Parameter Store.

## Zone B is jointly read, singly written

Dockerfiles, entrypoint scripts, health and readiness endpoints, environment validation and graceful
shutdown are **written by BUILD and edited by the client** (`SRC-002 §6.2`). That is the one place
the boundary is deliberately soft.

Consequence: every line in Zone B that exists for a production reason carries a comment saying **what
breaks without it** (`§6.2.6`). A Zone B file without those comments is not finished, regardless of
whether it runs.

## The handshake

**BUILD → OPS.** Anything needed from AWS is added to the prep queue with a *needed by* stage,
**and** said in chat, early enough to be prepared while code is still being written. **Never announce
a dependency on the day it blocks.**

**OPS → BUILD.** When an item is created, report **what actually exists** — endpoint, version, role
name, region, ARN. The build session may then write it down as observed. It cannot write "the RDS
instance exists" because the item is on a list; only because someone said it does.

## Standing facts about the boundary

- The build session has **never observed this application running in AWS.** Every statement it makes
  about AWS runtime behaviour is **reasoned, not observed**, and is labelled that way.
- As of 2026-08-14 the build session holds **read-only AWS credentials** so it can inspect what OPS
  built and check it against the specification. Describe, list, get. **No create, no modify, no
  delete, at any confidence, until the client says otherwise in writing.**
- Read-only inspection does **not** convert a reasoned claim into an observed one about *runtime
  behaviour*. Seeing that a target group exists is an observation. Concluding that traffic reaches
  the container through it is not.
- **The deployed environment is never called production** in any document while it runs without TLS.
- **Destructive AWS actions are always human.** No session, in either lane, deletes a database, drops
  a bucket, or rotates a credential.

## Shared-primitive locks

Claim a shared file **before** editing it; release when done. Both lanes append here.

```
claim log:  <file>  ->  <lane>  @ <time>   (released <time>)
```

*(none open)*

## Rule

A change to the shared spine after the lanes have forked — the data model, the environment contract,
the module layout, the port a container listens on, the health check paths — is a
**stop-the-world**. Announce it here, and the other lane re-reads before continuing.
