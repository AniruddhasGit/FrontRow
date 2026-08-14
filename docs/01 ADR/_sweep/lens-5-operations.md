# Lens 5 — Operations · raw sweep return

```
Run ........ 2026-08-14, GOAL_02
Method ..... independent sub-agent, read SRC-001 + SRC-002 + SRC-003 in full including both §E,
             plus CONSTITUTION.md Art VIII
Status ..... RAW. Not deduped, not merged, not adjudicated.
Format ..... <decision statement> | SOURCE: <clause id or NONE> | <RULED|PROVISIONAL|OPEN|ASSUMED>
```

Every setting is read from an environment variable and the process crashes at startup with a clear message when a required one is absent | SOURCE: SRC-002 §7.1 | RULED
The concrete required-vs-optional environment variable list, their types and their safe defaults is not enumerated anywhere | SOURCE: NONE | OPEN
The mechanism for config validation (pydantic-settings versus hand-rolled) is unchosen and any new library needs the client's prior permission | SOURCE: SRC-002 §13.1 | OPEN
A complete `.env.example` ships and no secret is ever committed | SOURCE: SRC-002 §13.4 | RULED
The seat-hold TTL is 3 minutes read from a configuration value, never a constant | SOURCE: SRC-002 E-1 | RULED
Currency minor-unit ratio 100 and timezone Asia/Kolkata are named configuration values, not literals | SOURCE: SRC-003 OPEN-LOCALE-01 | RULED
Secrets live in SSM Parameter Store and never in AWS Secrets Manager | SOURCE: SRC-002 §5.4.3 | RULED
How SSM values reach the container — ECS task-definition `valueFrom` versus an entrypoint that fetches at boot — is undecided and straddles the Zone B/Zone C line | SOURCE: NONE | OPEN
SSM parameter path naming, String versus SecureString, and which KMS key are unspecified | SOURCE: NONE | OPEN
The JWT signing secret's storage, length and rotation procedure is unspecified | SOURCE: NONE | OPEN
`/health/live` returns 200 while the process is alive and `/health/ready` returns 503 when Postgres or Redis is unreachable; they may not be collapsed | SOURCE: SRC-002 §7.4 | RULED
Whether readiness also probes SQS, SES or S3, or only Postgres and Redis, is unstated | SOURCE: NONE | OPEN
Readiness probe timeout, and whether dependency checks are cached so ALB polling does not hammer the database, is unspecified | SOURCE: NONE | OPEN
How the worker container and the static frontend container report health, neither having the API's HTTP surface, is unspecified | SOURCE: NONE | OPEN
ALB health-check path, interval, healthy/unhealthy thresholds and grace period are Zone C values the client must be given as a specification | SOURCE: SRC-002 §6.4.2 | RULED
On SIGTERM the API stops accepting, drains in-flight requests, releases the Redis locks held by that instance, then exits | SOURCE: SRC-002 §7.5 | RULED
The drain timeout, and its required relationship to the ALB deregistration delay and the ECS stop timeout, is undetermined | SOURCE: NONE | OPEN
Releasing an instance's Redis locks on shutdown contradicts locks expiring on their own with no cleanup, and which behaviour wins for a customer mid-checkout is unresolved | SOURCE: SRC-002 §7.5 vs §8.1.4 | OPEN
Worker shutdown semantics — finish the in-flight message versus let visibility timeout return it — are unspecified | SOURCE: NONE | OPEN
Logs are JSON on stdout and never written to disk | SOURCE: SRC-002 §5.4.5 | RULED
A request id is propagated through every log line, including worker jobs triggered by that request | SOURCE: SRC-002 §7.6 | RULED
The request-id header name, and whether an inbound header from the ALB is trusted or a fresh id is always generated, is undetermined | SOURCE: NONE | OPEN
The structured-log field schema and the default log level per environment are unspecified | SOURCE: NONE | OPEN
No card-shaped data appears in any log line, column, fixture or seed script | SOURCE: SRC-003 OPEN-PAY-01 | RULED
CloudWatch log retention and how log volume is kept inside the 5 GB free allowance is undetermined | SOURCE: SRC-002 §5.2.6 | OPEN
A `/metrics` endpoint in Prometheus format exposes request counts, latency, seat lock counts and queue depth | SOURCE: SRC-002 §7.7 | RULED
Nothing in the approved stack scrapes Prometheus metrics — Managed Grafana is forbidden and no scraper is named — so who consumes `/metrics` is undetermined | SOURCE: NONE | OPEN
Whether `/metrics` is reachable through the ALB or restricted to the host is undetermined | SOURCE: NONE | OPEN
Whether the worker also exposes metrics, and how counters are shared across multiple uvicorn workers, is undetermined | SOURCE: NONE | OPEN
Queue-depth metric source — SQS `ApproximateNumberOfMessages` versus a locally tracked counter — is undetermined | SOURCE: NONE | OPEN
Rate limiting is a Redis token bucket on seat-selection and booking endpoints, keyed per user and per IP | SOURCE: SRC-002 §8.4.1 | RULED
Rate-limited requests return 429 with a `Retry-After` header | SOURCE: SRC-002 §8.4.2 | RULED
Bucket capacity and refill rate for each limited endpoint are unspecified | SOURCE: NONE | OPEN
How the real client IP is derived behind the ALB, and whether `X-Forwarded-For` is trusted, is undetermined | SOURCE: NONE | OPEN
Whether the rate limiter fails open or fails closed when Redis is unreachable is undetermined, and the fail-loudly rule is written only about locks | SOURCE: SRC-002 §7.9 | OPEN
Whether login and registration endpoints are rate limited at all is unstated | SOURCE: NONE | OPEN
AWS SQS is the queue in AWS and ElasticMQ is the local stand-in, with the worker coded against one queue interface that does not know which is behind it | SOURCE: SRC-003 OPEN-QUEUE-01 | RULED
A dead letter queue exists and failures are made visible | SOURCE: SRC-002 §8.5.2 | RULED
The redrive policy values — `maxReceiveCount`, visibility timeout, message retention — are undetermined and owed to the client as a Zone C specification | SOURCE: NONE | OPEN
Standard versus FIFO queue is unchosen, and the receipt-email job's ordering and exactly-once needs are unstated | SOURCE: NONE | OPEN
The queue message schema, its version field, and worker-side idempotency against redelivery are undetermined | SOURCE: NONE | OPEN
Long-poll wait time and the empty-receive cost against the 1M-request free allowance are undetermined | SOURCE: NONE | OPEN
Nothing watches the dead letter queue and no alarm on non-empty DLQ is ruled | SOURCE: NONE | OPEN
The mandate both prefers RQ or Dramatiq over Celery and specifies a worker consuming SQS; which library, if any, sits over the queue interface is unresolved | SOURCE: SRC-002 §5.4.1 vs §4.5 | OPEN
Retry count and backoff schedule for a failed receipt-email job are unspecified | SOURCE: NONE | OPEN
Amazon SES is an approved service and is load-bearing, since the emailed receipt is the only proof of purchase and the only way into the hall | SOURCE: SRC-002 E-6 | RULED
SES starts in sandbox and the client requests production access | SOURCE: SRC-003 OPEN-EMAIL-01 | RULED
What the customer is shown, and what state the booking is left in, when SES fails after payment is captured is genuinely unruled and reserved | SOURCE: SRC-003 OPEN-EMAILFAIL-01 | OPEN
The booking confirmation screen shows the unique reference on screen as well as emailing it | SOURCE: SRC-003 OPEN-EMAIL-01 | RULED
The SES sender identity, its verified domain, and DKIM/SPF setup are undetermined and blocked behind the unsettled domain | SOURCE: SRC-003 OPEN-TLS-01 | OPEN
Bounce and complaint handling for SES is undetermined | SOURCE: NONE | OPEN
The local development stand-in for SES is unchosen and would be a new dependency needing permission | SOURCE: SRC-002 §13.1 | OPEN
S3 holds movie posters and the application serves its own URLs, never hotlinking | SOURCE: SRC-002 §10.6.3 (survives E-2) | RULED
The admin uploads posters by hand rather than a job downloading them | SOURCE: SRC-003 OPEN-TMDB-01 | RULED
Whether posters are served from a public-read bucket, by presigned GET, or proxied through the API is undetermined | SOURCE: NONE | OPEN
Whether upload is a browser presigned PUT or a multipart POST through the API is undetermined, and the stateless-container rule forbids buffering to local disk | SOURCE: SRC-002 §7.3 | OPEN
Maximum poster size, permitted content types and image validation are unspecified | SOURCE: NONE | OPEN
No CDN is used for posters because CloudFront is outside the approved service list | SOURCE: SRC-002 §4.12 | ASSUMED
The local development stand-in for S3 is unchosen | SOURCE: NONE | OPEN
Database migrations are Alembic and run as a separate step, never automatically on application boot | SOURCE: SRC-002 §7.8 | RULED
How the migration step is actually executed in AWS — a one-off ECS task, a manual `docker run`, or an entrypoint flag — is undetermined and owed as a Zone C specification | SOURCE: NONE | OPEN
Migration ordering relative to a deploy, down-migration policy, and a lock preventing two concurrent runs are undetermined | SOURCE: NONE | OPEN
Each service has a production Dockerfile written by the build session but heavily commented, with every production-motivated line stating what breaks without it | SOURCE: SRC-002 §6.2.1, §6.2.6 | RULED
Container entrypoint scripts are Zone B and carry the same commenting obligation | SOURCE: SRC-002 §6.2.2 | RULED
Images use multi-stage builds on a slim base and target under 250 MB final, because ECR's free tier holds 500 MB in total | SOURCE: SRC-002 §5.4.2 | RULED
The specific base image, non-root user, and read-only root filesystem are unchosen | SOURCE: NONE | OPEN
Whether the API and worker ship as one image with two commands or as two images is left to the build session | SOURCE: SRC-002 §7.2 | OPEN
The static frontend is served from a small static container rather than a Node process, at roughly 15 MB | SOURCE: NONE | ASSUMED
Image tagging strategy and an ECR lifecycle policy to stay under 500 MB are undetermined | SOURCE: NONE | OPEN
Exactly three long-running processes run — API, worker and static frontend — and no scheduler exists | SOURCE: SRC-002 E-4 | RULED
Roughly 1 GB of RAM covers every container together and explicit memory limits are set on each | SOURCE: SRC-002 §5.4.1 | RULED
The per-container split of roughly 200 MB API, 150 MB worker, 15 MB frontend is an estimate to be replaced with measurements in Phase 1 | SOURCE: NONE | ASSUMED
Uvicorn or gunicorn worker count inside the API's memory budget is undetermined | SOURCE: NONE | OPEN
Anything that will not fit in 1 GB is reported to the client rather than quietly worked around | SOURCE: SRC-002 §13.6 | RULED
Containers run on ECS backed by a single t3.micro EC2 instance behind an Application Load Balancer | SOURCE: SRC-002 §4.10, §4.11 | RULED
Kubernetes, Fargate, service meshes, EKS, NAT Gateway, Secrets Manager, Managed Grafana and OpenSearch are forbidden and must not be designed around | SOURCE: SRC-002 §4.12, §5.3 | RULED
With no NAT Gateway the application must be able to run in a public subnet behind strict security groups | SOURCE: SRC-002 §5.4.4 | RULED
Every outbound internet path is documented; the standing list still names TMDB and must be re-derived to S3, SQS, SES, SSM, ECR and CloudWatch Logs | SOURCE: CONSTITUTION Art VIII.13 | PROVISIONAL
Whether VPC endpoints are used instead of public-subnet egress is undetermined, and interface endpoints are not on the free-tier list | SOURCE: NONE | OPEN
How the ALB routes between the static frontend container and the API — path rules, host rules, or the frontend proxying — is undetermined | SOURCE: NONE | OPEN
Container port assignments and whether ECS dynamic port mapping is used are undetermined | SOURCE: NONE | OPEN
A light load test is pointed at the ALB to observe autoscaling, though a single free-tier t3.micro leaves nothing to scale out to | SOURCE: SRC-002 §9.2 | PROVISIONAL
The concurrency script runs against local Docker and the deployed environment by changing only a base URL | SOURCE: SRC-002 §9.1 | RULED
The seat map is polled every 3 seconds, with a documented note on what changes at the load balancer if WebSockets are adopted later | SOURCE: SRC-002 §8.6.1, §8.6.2 | RULED
The request load that 3-second polling places on one t3.micro and on the ALB is unquantified | SOURCE: NONE | OPEN
Containers are stateless with no local session state and no local file writes, and killing one mid-request corrupts nothing | SOURCE: SRC-002 §7.3 | RULED
If Redis is down the application returns an error and never falls back to the database for locks | SOURCE: SRC-002 §7.9 | RULED
Nothing is ever deleted — no pruning job, no retention window, no cascade that destroys a booking record | SOURCE: SRC-003 OPEN-OPS-02 | RULED
RDS backup retention, snapshot schedule and a tested restore procedure are undetermined against a 20 GB free-tier volume and forever-retention | SOURCE: NONE | OPEN
Redis holds only locks and cache and is treated as losable, with no persistence requirement stated | SOURCE: NONE | ASSUMED
TLS is unsettled pending a domain and certificate, and the deployed environment is never called production while it runs without TLS | SOURCE: SRC-003 OPEN-TLS-01 | OPEN
The session cookie `Secure` flag is environment-driven and stays off in the deployed environment until TLS exists | SOURCE: SRC-003 OPEN-TLS-01 | RULED
The single ruled alarm is CloudWatch running-task-count below 1, delivered via SNS to the client's email | SOURCE: SRC-003 OPEN-OPS-01 | RULED
The alert email address is never committed; it lives in the SNS subscription and local `.env` only | SOURCE: SRC-003 OPEN-OPS-01 | RULED
No alarm is ruled for 5xx rate, latency, DLQ depth, RDS free storage, memory pressure or SES bounce rate | SOURCE: NONE | OPEN
There is one operator and no backup decider, so no escalation path or on-call rotation exists | SOURCE: SRC-003 OPEN-NAME-01 | RULED
`docker-compose.yml` is for local development only and is never deployed | SOURCE: SRC-002 §6.1.7 | RULED
Local compose stands up Postgres, Redis and ElasticMQ | SOURCE: SRC-003 OPEN-QUEUE-01 | RULED
Whether local development needs an SSM stand-in or simply reads a `.env` file is undetermined | SOURCE: NONE | ASSUMED
The seed script generates structural data only — one theatre, six halls with layouts, showtimes and bookings spanning about a month | SOURCE: SRC-003 OPEN-SEED-01 | RULED
Seeded movie rows carry obvious placeholders such as `DEMO MOVIE 01`; no titles or posters are invented | SOURCE: SRC-003 OPEN-SEED-01 | RULED
Whether the seed script is idempotent and whether it may ever be run against the deployed environment is unstated | SOURCE: NONE | OPEN
Hall sizes of 90, 120, 150, 180, 200 and 220 seats are an assumption and never harden into a constraint | SOURCE: SRC-003 OPEN-SCALE-02 | ASSUMED
The build session may run only `describe`, `list` and `get` against AWS and creates, modifies and deletes nothing until the client says otherwise in writing | SOURCE: SRC-003 OPEN-AWSREAD-01 | RULED
The AWS account id and region the read credentials belong to are unknown and are to be read from the credentials at first use, never guessed | SOURCE: SRC-003 OPEN-AWSREAD-01 | OPEN
Every statement about AWS runtime behaviour is labelled reasoned, not observed | SOURCE: CONSTITUTION Art VIII.3 | RULED
The build session writes no Terraform, CloudFormation, ECS task or service definition, ALB or security group configuration, VPC layout, CI/CD pipeline, or CloudWatch alarm | SOURCE: SRC-002 §6.3 | RULED
`docs/30 Deployment` owes, per Zone C item, what to build, what the application expects of it (ports, health paths, env vars, IAM permissions), acceptance criteria, and two or three common mistakes | SOURCE: SRC-002 §6.4 | RULED
The specification is given and the answer withheld, so the client fails against it | SOURCE: SRC-002 §6.5 | RULED
Every AWS dependency is entered in `docs/30 Deployment/AWS_PREP_QUEUE.md` with a needed-by stage and announced in chat before it blocks | SOURCE: CONSTITUTION Art VIII.4 | RULED
The exact IAM policy the task role needs — SSM read, S3 object put/get on one bucket, SQS send/receive/delete, SES send — is not yet written and is owed under the Zone C specification duty | SOURCE: SRC-002 §6.4.2 | OPEN
The mandate's flat `docs/deployment-tasks.md`, `docs/decisions.md` and `docs/runbook.md` paths conflict with the repository's numbered folders, and the mapping is not recorded | SOURCE: SRC-002 §11 | PROVISIONAL
A runbook is delivered in Phase 7 alongside metrics, rate limiting and the load test | SOURCE: SRC-002 §12.8 | RULED
A short explanation file is written at the end of every phase covering what was built, why, and what breaks in production if the deployment is wrong | SOURCE: SRC-002 §2.4 | RULED
CI/CD is Zone C, so no automated test gate exists on merge and all verification is local and manual until the client builds a pipeline | SOURCE: SRC-002 §6.3.5 | RULED
Nothing in the system runs on a schedule, so no EventBridge rule, cron container or scheduler process is designed or specified | SOURCE: SRC-002 E-4 | RULED
The admin-token-protected HTTP job trigger and the CLI sync command are withdrawn with the whole TMDB section | SOURCE: SRC-002 E-2 | RULED
The simulated payment provider is unreachable in a deployed environment without a deliberate, visible flag | SOURCE: SRC-003 OPEN-PAY-02 | RULED
