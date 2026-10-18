# P1 · IAM roles: instance, execution, task  (prep-queue rows 12 and 15 · needed by Phase 1)

> Zone C specification. What to build, not how. Every claim about AWS behaviour is **reasoned, not observed**.

## 1. What you need to build

**Three roles, each used by a different piece of software at a different time.** Mixing them up is the
single most common Phase 1 failure on ECS with EC2 (prep-queue row 15).

| Role | Used by | When |
|---|---|---|
| **container instance role** (an instance profile on the EC2 host) | the ECS agent on the host | all the time. It registers the instance with the cluster and polls for work |
| **task execution role** | the ECS agent, acting for one task | **before your container starts**: pulling the image from ECR, creating the log stream, reading SSM parameters injected as `secrets` |
| **task role** | **your application code** inside the container | while it runs. Only used when the code calls an AWS API |

## 2. What the application expects

- **Execution role, Phase 1:** permission to pull the two ECR images; to create log streams and put
  log events in the project's log group; and `ssm:GetParameters` on the project's parameter path
  (`/frontrow/<environment>/*`), plus decrypt through the **AWS-managed** SSM key (PRD `P-XCT-16`).
  Do not create a customer-managed KMS key for this. It has a monthly charge (reasoned, not observed).
- **Task role, Phase 1: no permissions at all.** The Phase 1 application makes **no AWS API call**.
  It reads environment variables, talks to PostgreSQL and Redis over their own protocols, and nothing
  else. A task role with permissions in Phase 1 is a permission nobody uses.
- **Task role, later**, added in the phase that first needs it (row 12): SQS send/receive on two queues
  (Phase 5), SES send from one verified identity (Phase 5), S3 put/get on one prefix (Phase 6).
- **Scope every statement to this project's resources by ARN.** This account also holds SpendWise
  (`OPS_SESSION_BRIEF.md`). A `"Resource": "*"` grant lets FrontRow's task read SpendWise's secrets.

## 3. Acceptance criteria

1. The EC2 instance has an instance profile, and the cluster lists the instance as a registered
   container instance.
2. The api and frontend task definitions each name an **execution role**, and it is not the instance role.
3. The execution role's policy names this project's ECR repositories, log group and SSM path by ARN.
   It does not name SpendWise's.
4. In Phase 1 the task role is either absent or has no policy statements.
5. A task that injects `DATABASE_URL` from SSM reaches `RUNNING` (proves the execution role can read it).

## 4. Common mistakes

- **Putting `ssm:GetParameters` on the task role instead of the execution role.** The parameter is read
  *before* the container exists, by the agent, with the execution role. The task stops at `PENDING`
  with a `ResourceInitializationError`, and **no application log line ever appears**, because the
  log stream is created with the same role and the container never started.
- **Reusing the instance role as the execution role** "because it already has ECR access". It works
  until you scope it. After that every task on the host has every permission any task needed.
- **Granting `*` resources to get unstuck.** It will make the error go away, and it will also give this
  project access to the other project in this account. Read the denied action and its resource in the
  error, and grant exactly that.
