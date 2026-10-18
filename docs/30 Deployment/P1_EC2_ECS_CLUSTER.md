# P1 · One `t3.micro` and an ECS cluster on it  (prep-queue row 2 · needed by Phase 1)

> Zone C specification. What to build, not how. Every claim about AWS behaviour is **reasoned, not observed**.
> **Fargate and EKS are forbidden** (`SRC-002 §5.3`).

## 1. What you need to build

- An ECS **cluster** for this project, separate from `spendwise-cluster`.
- **One EC2 `t3.micro`** running an ECS-optimised operating system image, in a public subnet with a
  public IPv4 address, with the container instance role (`P1_IAM_ROLES.md`), registered to that cluster.

## 2. What the application expects

**Memory: 1 GB on the whole host** (`SRC-002 §5.2.1`), shared with the OS, Docker and the ECS agent.
Measured locally on 2026-10-18 at idle, on Docker Desktop, **not on a t3.micro**:

| Container | Resident at idle (measured) | Limit the architecture budgets (`docs/07 Architecture/for_llm/04_deployment.md`) |
|---|---|---|
| api | ~50 MiB | 200 MiB |
| frontend | ~2–3 MiB | 15 MiB |

**Not measured yet: memory under load** (Phase 7's load test) and anything on the real host. The
figures above replace the estimates for idle only. **Nothing measured so far suggests Phase 1 will not
fit in 1 GB.**

**Cost note, said before you start the instance:** free-tier EC2 hours are per account. This account
already holds SpendWise's `t3.micro` (stopped, as observed 2026-10-18). Running both at once uses
twice the hours the free tier covers. The public IPv4 address is also billed hourly (prep-queue
standing note). Both are reasoned, not observed.

## 3. Acceptance criteria

1. The cluster exists and lists exactly one registered container instance, of type `t3.micro`.
2. That instance reports its registered and remaining memory, and the agent is connected.
3. The instance is in a public subnet, has a public IPv4 address, and uses the instance security group
   from `P1_NETWORK_SECURITY_GROUPS.md`.
4. SpendWise's cluster and instance are unchanged.

## 4. Common mistakes

- **A plain Amazon Linux image instead of an ECS-optimised one.** The instance boots, but no agent
  registers it. The cluster shows zero container instances, and every task fails to place with
  "no container instance met all of its requirements".
- **The cluster name is wrong in the instance's agent configuration.** The agent registers to a
  cluster named `default` that you did not create, and yours stays empty.
- **Reading "registered memory" as free memory.** ECS places tasks by comparing task limits with what
  the agent registered. That number does not subtract what the OS and Docker use, so a placement that
  succeeds does not prove the host has room (`04_deployment.md`, AWS-04-10).
