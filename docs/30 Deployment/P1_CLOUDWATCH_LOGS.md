# P1 · CloudWatch Logs and the `awslogs` driver  (prep-queue row 7 · needed by Phase 1)

> Zone C specification. What to build, not how. Every claim about AWS behaviour is **reasoned, not observed**.

## 1. What you need to build

- A **log group** for this project, and the containers' stdout and stderr sent to it through the
  `awslogs` log driver in each task definition.
- A **finite retention** on the log group. The default is to keep logs forever (reasoned, not
  observed), and the free tier is 5 GB (`SRC-002 §5.2.6`). The retention period is a cost decision and
  therefore yours. What a shorter one loses: the ability to answer "what happened to this booking"
  for a booking older than the retention.

## 2. What the application expects

- **Without this item, every log line the application writes is lost when the container stops.** The
  application writes only to stdout (`SRC-002 §5.4.5`). It writes no file, by design and as proved
  locally: a read-only root filesystem, 0 paths changed. With the default log driver, the record of a
  crash loop is destroyed by the restart that caused it.
- **What arrives**: one JSON object per line. Every line carries `timestamp`, `level`, `logger`,
  `message`, `request_id` (8 hex characters), `service` (`api` or `frontend`) and `instance_id`.
  Locally, 26 of 26 api lines across boot, traffic, two dependency outages and SIGTERM parsed as JSON
  and carried a `request_id` (GOAL_14 gate, proof 5).
- **Volume**: successful `/health/live` and `/health/ready` polls are **not** logged. One line is
  written per other request. A failed readiness check writes three lines.
- **A config failure is one line on stdout and exit code 78.** If it does not appear in the log group,
  the log configuration is wrong. The application is not.
- The frontend's nginx writes one JSON line per request on stdout. Its rare error lines on stderr are
  plain text and cannot be made JSON.

## 3. Acceptance criteria

1. The log group exists, belongs to this project, and has a retention period that is not "never expire".
2. Both task definitions use the `awslogs` driver pointed at it.
3. After one request to the api, its log stream holds a line whose `message` is `request completed`
   and whose `request_id` matches the `x-request-id` response header of that request.
4. A CloudWatch Logs Insights query on `request_id` finds that line.
5. After a deliberate config failure (index acceptance item 9), the log stream holds the
   `configuration invalid` line.

## 4. Common mistakes

- **The execution role cannot create the log stream.** The task fails at start, and because logging
  is what failed, there is no log explaining why. The reason is in the stopped task's
  `stoppedReason`. Read that first.
- **Never-expire retention.** Nothing breaks for months. Then the 5 GB is exceeded and the bill is the
  first notice.
- **Blocking log delivery.** By default the driver's delivery is blocking (reasoned, not observed). If
  CloudWatch cannot be reached, the application's write to stdout waits, and requests wait with it.
  The non-blocking mode drops lines under pressure instead. Choose deliberately. It is a trade
  between losing log lines and stalling requests.
