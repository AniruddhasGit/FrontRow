# P1 · VPC, subnets and security groups  (prep-queue row 4 · needed by Phase 1)

> Zone C specification (`SRC-002 §6.3.3`, `§6.3.4`). What to build, not how. Every claim about AWS
> behaviour is **reasoned, not observed**.

## What to build

- A VPC with **public subnets in at least two Availability Zones** in `ap-south-1`. The load balancer
  needs two (reasoned, not observed). The EC2 instance needs one of them.
- **No NAT Gateway.** It is forbidden (`SRC-002 §5.3`). The instance therefore sits in a public
  subnet and reaches AWS service endpoints through its own public IPv4 address (`§5.4.4`).
- **Three security groups** with separate jobs. The application does not care what they are named:
  - one for the **load balancer**
  - one for the **EC2 container instance**
  - one for **each data store** when it exists (RDS, ElastiCache)
- A rule set in which **the only inbound path to a container is from the load balancer's security group**.

## What the application expects

| Traffic | From | To | Port | Why |
|---|---|---|---|---|
| browser → load balancer | the internet | LB security group | **80** (HTTP only; TLS is blocked on a domain, row 14) | the only public entry point |
| LB → api container | LB security group | instance security group | **8000**, or the host-port range you choose (see `P1_TASK_DEFINITIONS.md`) | health checks and requests |
| LB → frontend container | LB security group | instance security group | **8080**, or the host-port range | same |
| instance → AWS endpoints | instance security group | the internet | **443** | pull from ECR, push logs, read SSM, ECS agent |
| api → PostgreSQL | instance security group | RDS security group | **5432** | `/health/ready` and, from Phase 2, everything |
| api → Redis | instance security group | ElastiCache security group | **6379** | `/health/ready` and, from Phase 4, seat holds |

**Outbound internet access the application needs, by phase.** This answers `§5.4.4`'s "note anywhere
the app needs outbound internet access":

| Phase | Destination | Who makes the call |
|---|---|---|
| 1 | ECR, CloudWatch Logs, SSM, ECS control plane | the **ECS agent and Docker**, not the application. The app itself makes **no** outbound AWS call in Phase 1 |
| 5 | SQS, SES | the application |
| 6 | S3 | the application |

## Acceptance criteria

1. No security group in this project has an inbound rule from `0.0.0.0/0` (or `::/0`) except the load
   balancer's, on port 80.
2. The instance security group's inbound rules name the **load balancer's security group** as their
   source, not a CIDR block.
3. The RDS and ElastiCache security groups, when they exist, allow inbound only from the instance
   security group, on 5432 and 6379.
4. The account has **no NAT Gateway** for this project (forbidden, `SRC-002 §5.3`) (`describe-nat-gateways` shows none).
5. The instance has a public IPv4 address. Without one it cannot pull its image, and the task never starts.

## Common mistakes

- **Opening 8000 to the internet "to test it".** The container is then reachable without the load
  balancer, and every later rule you add to the load balancer (rate limiting by client IP, TLS) can be
  walked around. Test through the load balancer's DNS name instead.
- **Putting the instance in a private subnet because that is "best practice".** Without a NAT Gateway (forbidden) a
  private subnet has no route to ECR. The task sits in `PENDING` and then fails with an image-pull or
  `ResourceInitializationError`, and the application never logs a line, because it never started.
- **Allowing SSH (22) from anywhere.** It does not affect the application. It does put a public login
  prompt on the only host you have. If you need a shell, prefer one that does not open an inbound port.
