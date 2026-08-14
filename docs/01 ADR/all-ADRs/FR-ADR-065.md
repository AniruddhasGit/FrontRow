# No NAT Gateway: a public subnet with strict security groups, and the corrected outbound list

```
ADR id ............ FR-ADR-065
Pack .............. PACK-OPS
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-002 §5.3; SRC-002 §5.4.4; SRC-002 §6.3.4; SRC-002 §6.4.2; SRC-003 OPEN-TMDB-01; SRC-002 §E E-2; SRC-002 §4.11
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §5.3` puts NAT Gateway on the not-available list — it is one of the largest line items in an
AWS bill and there is no free tier for it. `§5.4.4` states the consequence: design the app so it can
run in a public subnet with strict security groups, and **note anywhere the app needs outbound
internet access**.

That list has to be written, and the version currently carried in `CONSTITUTION.md` Art VIII.13 is
**out of date**: it names TMDB, which no longer exists (`SRC-003 OPEN-TMDB-01`, `SRC-002 §E E-2`). A
stale egress list is a security group rule for something that will never connect and a missing rule
for something that will.

## Decision

**The application runs in a public subnet with a public IP and strict security groups. There is no NAT
Gateway and none is designed around.**

**The corrected outbound list — every place this application needs to reach the internet:**

| Destination | Which process | What breaks without it |
|---|---|---|
| **S3** | API | poster upload and the presigned redirect (`FR-ADR-061`) |
| **SQS** | API and worker | receipts are never enqueued or consumed (`FR-ADR-059`) |
| **SES** | worker | no receipt is ever sent — the customer cannot enter the hall (`FR-ADR-060`) |
| **SSM Parameter Store** | ECS agent, at task start | **the task will not start** (`FR-ADR-054`) |
| **ECR** | ECS agent, at task start | the image cannot be pulled |
| **CloudWatch Logs** | Docker log driver | logs are lost, including the crash that caused a restart (`FR-ADR-056`) |

**TMDB is removed from this list.** It appears in `CONSTITUTION.md` Art VIII.13 and that clause is
stale. **`CONSTITUTION.md` is outside this goal's write-set and the build session may not amend it**
(Art XII.1) — the correction is raised for the client rather than made.

**Three of those six are the ECS agent's egress, not the application's**, and that distinction matters
because it is where the mistake happens: SSM, ECR and CloudWatch Logs are needed **before the
application process exists**. A security group that permits only what the application needs produces a
task that never starts, with an error about pulling an image rather than about a security group.

**Inbound: nothing reaches the instance except from the ALB.** The instance's security group permits
inbound only from the ALB's security group, on the container port. Not from `0.0.0.0/0`, not on port
22 from anywhere. **Being in a public subnet is not the same as being publicly reachable**, and the
security group is what makes that true.

**PostgreSQL and Redis are reached over the VPC, not the internet.** RDS and ElastiCache sit in the
VPC with security groups permitting only the application's security group. They need no egress rule
because the traffic never leaves.

**RDS and ElastiCache are not publicly accessible.** `publicly_accessible` is false on the RDS
instance. A database reachable from the internet with a password is a database that will be found.

**All of this is Zone C** (`§6.3.3`, `§6.3.4`). The build session writes none of it and owes the
specification (`§6.4.2`): the egress list above, the inbound rule, the not-publicly-accessible
requirement, and the acceptance criteria that prove each.

**VPC endpoints are not used.** Gateway endpoints for S3 would be free and would remove S3 from the
egress list; interface endpoints for SQS, SES, SSM and ECR are charged per hour per endpoint and are
not in the free tier. **A partial solution — a gateway endpoint for S3 only — leaves the public subnet
requirement in place for everything else and adds a component for no reduction in what has to be
permitted.** It is recorded as a real option the client may take once they are comfortable with the
basic layout, and it is a good second exercise.

## Alternatives rejected

**A private subnet with a NAT Gateway.** Rejected by `§5.3`. It is the conventional answer and it is
the most expensive line item available.

**A private subnet with no egress at all.** Rejected. The task cannot pull its image or read its
secrets, so nothing starts.

**Interface VPC endpoints instead of public egress.** Rejected on cost, above.

**A gateway endpoint for S3 as a partial measure.** Rejected for now, recorded as a later exercise.

**A bastion host for administrative access.** Rejected as another instance against the free tier.
Session Manager over SSM is the route if shell access is needed, and it is Zone C.

**Permit `0.0.0.0/0` inbound on the container port for simplicity.** Rejected outright. It makes the
ALB decorative and exposes the application directly.

## Source

`SRC-002 §5.3` (no NAT Gateway) · `§5.4.4` (public subnet, strict security groups, document every
outbound path) · `§6.3.4` (VPC and subnet layout is Zone C) · `§6.3.3` (security groups are Zone C) ·
`§6.4.2` (the specification owes what the application expects) ·
`SRC-003 OPEN-TMDB-01` and `SRC-002 §E E-2` (TMDB removed) · `§4.11` (the ALB).

The corrected list and the agent-versus-application distinction are the build session's under
Art III.9.

## Consequences

**`CONSTITUTION.md` Art VIII.13 is stale and this record cannot fix it.** It names TMDB as an outbound
dependency of a system that has no TMDB integration. **Raised for the client**, who is the only one who
may amend the Constitution (Art XII.1).

**The agent-versus-application distinction is the single most useful thing in the Zone C
specification** and it goes in the common-mistakes section `§6.4.4` requires: a task that will not
start with an image-pull error is usually a missing egress rule, not a broken image.

**Everything here is `(reasoned, not observed)`.** The build session has never watched this application
run in AWS (Art VIII.3), and its AWS access is read-only (`FR-ADR-003`) — enough to describe a
security group and compare it against this list, which is exactly what that access is for.

Running in a public subnet with a public IP is a weaker posture than a private subnet, and it is a
deliberate, cost-driven trade. The security group is the entire control. It belongs in the
architecture folder's list of accepted weaknesses, not left implicit.
