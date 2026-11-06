# DEPLOY_RENDER: the always-on free copy (Render + Neon + Resend)

This file exists only in `frontrow/` (the Render clone). The binding plan is `SRC-005 D-2`
(`docs/00 SourceOfTruth/SRC-005_client_rulings_2026-10-18_render.md`). The application code is never edited here:
it comes from `git pull aws main`.

| Piece | Where it runs |
|---|---|
| API | Render **free web service** `frontrow-api`, Docker, `backend/Dockerfile`, build context = the repository root, region Singapore. It is the same image as the AWS copy. |
| Frontend | Render **static site** `frontrow-web`, built from `frontend/` (`npm ci && npm run build` -> `frontend/dist`). `/api/*` is rewritten to the API, and everything else falls back to `/index.html`. |
| PostgreSQL | Neon free, project `FrontRow` (aws-ap-southeast-1, PG16, db `neondb`). |
| Redis | The **existing** Render Key Value `frontrow-redis` (Singapore, free). The script reads its internal URL and never creates it. |
| Mail | Resend, called from the API process (`MAIL_PROVIDER=resend`). There is no worker and no queue. |

## 1. Run the script

```sh
python scripts/render_deploy.py            # DRY RUN, the default: GET calls only, prints the plan with secrets masked
python scripts/render_deploy.py --apply    # find-or-create both services by name, set env vars and routes
python scripts/render_deploy.py --deploy   # trigger ONE deploy of each service (not one created in this same run)
```

- **Standard library only.** It runs on the host Python with no project dependencies.
- **Idempotent.**
  - A service that already exists is updated, never duplicated.
  - `PUT env-vars` and `PUT routes` replace the whole list. **The script owns those lists**, so a variable you add by
    hand in the dashboard is removed on the next `--apply`. To keep one, add it to `api_env()`.
- **`JWT_SECRET` survives re-runs.**
  - On the first create, Render generates the value itself (`generateValue`), so it never exists on this machine.
  - Later runs read the live value back and send it unchanged. A new value would sign every customer out.
- **Auto-deploy is off** (`autoDeployTrigger: off`). On the free tier, deploys are triggered by hand and batched.
  - A create already starts the first build.
  - After that, push to `origin main`, then run `--deploy` once.
- **Order on `--apply`:**
  1. The web site first, because the API's `PUBLIC_BASE_URL` is the web URL.
  2. Then the API.
  3. Then the web's `/api/*` rewrite, pointed at the API URL from the create response. Render adds a suffix when a
     subdomain is taken, so the dry run's `*.onrender.com` names are a prediction until the first create.
- **Prerequisite:** Render's GitHub app must have access to `AniruddhasGit/FrontRow`. Without it, the create fails with
  "repository URL is invalid or unfetchable", which is the failure recorded in the 2026-10-19 handoff.

### Health check: `/health/live`, not `/health/ready`

- `/health/live` answers from the process alone.
- `/health/ready` queries Neon and Redis. As Render's probe, it would:
  - spend Neon compute hours on every probe while the instance is up, which breaks the owner's no-polling rule;
  - fail while a suspended Neon compute wakes, so Render would mark a healthy deploy as failed.
- `SRC-002 §7.4` already puts restart decisions on liveness.

## 2. Environment, `frontrow-api`

**No value appears here.** Secrets come from `D:/Project/FrontRow/passwords.txt` and nowhere else. Every variable
with a ruled default in `backend/app/core/config.py` is left to the code.

| Variable | Value comes from |
|---|---|
| `DATABASE_URL` | `FRONTROW_NEON_APP_URL`, with `-pooler` removed from the host (the direct endpoint). The engine sends `options=-c statement_timeout=…` when it connects, and Neon's pooler refuses that startup parameter. The application role (`frontrow_app`), never the owner. |
| `REDIS_URL` | Render API: `GET /key-value/{id}/connection-info` -> `internalConnectionString` of `frontrow-redis` |
| `JWT_SECRET` | Render-generated on create, then preserved |
| `RESEND_SECRET` | `RESEND_API_KEY`. It is named `RESEND_SECRET` in the app because S-SCP-03 refuses any setting named `…API_KEY`. |
| `MAIL_PROVIDER` | constant `resend` |
| `SES_SENDER_ADDRESS` | constant `FrontRow <onboarding@resend.dev>`. Resend's shared sender, which until a domain is verified delivers only to the Resend account's sign-up address. |
| `SES_SEND_TIMEOUT_MS` | constant `1500`. Check 15 requires it to be below `QUEUE_SEND_TIMEOUT_MS` (2000). |
| `QUEUE_URL` | constant `http://no-queue.invalid/…`. `config.py` requires it, and nothing reads it when `MAIL_PROVIDER=resend`. |
| `S3_BUCKET_NAME`, `AWS_REGION` | constants (`no-bucket-on-render`, `ap-southeast-1`). Both are required, and no bucket exists (section 6). |
| `AWS_EC2_METADATA_DISABLED` | constant `true`. Without it, boto3 probes the EC2 metadata address before reporting that there are no credentials. |
| `PUBLIC_BASE_URL` | the static site's URL (`serviceDetails.url`) |
| `COOKIE_SECURE` | constant `true`. Both Render URLs are https. |
| `FORWARDED_ALLOW_IPS` | constant `10.0.0.0/8`, Render's private network (section 6) |
| `PAYMENT_PROVIDER` | constant `simulated` |
| `PAYMENT_SIMULATOR_FAIL_KEY_PREFIX` | constant `simfail-`. It is not UUID-shaped, so a browser-minted key never starts with it. |
| `DB_CONNECT_TIMEOUT_MS` | constant `5000`. The default of 1 s is shorter than a Neon compute takes to wake. |
| `PORT` | constant `8000`. Render routes to `$PORT`, and the image binds `API_PORT` (8000). |

`frontrow-web` has one variable, `NODE_VERSION=24`. Vite 8 and TypeScript 7 need a current Node.

**Checked:** this exact variable set (with dummy secrets) passed `load_settings()`, including every cross-field check,
against this clone's `config.py`, inside the backend image.

## 3. One-time: migrate and seed Neon (from the host, through the backend image)

Run this once, before the first deploy is used. Both commands are idempotent: `alembic upgrade head` skips revisions
already applied, and the seed skips rows that exist.

- Both run as the **owner** role, on the **direct** host.
- Neither ever uses `--wipe-and-reseed`, because seeded rows on a deployed database are permanent.
- First add a line `SEED_DEFAULT_PASSWORD=<12+ chars>` to `passwords.txt`. The seeded customers' password is needed
  again by the stress test.

```sh
# from D:/Project/FrontRow/frontrow, Git Bash
docker build -f backend/Dockerfile -t frontrow-api:render .
P=D:/Project/FrontRow/passwords.txt
export DATABASE_URL="$(grep '^FRONTROW_NEON_OWNER_URL=' $P | cut -d= -f2- | sed 's/-pooler\././')"
export SEED_DEFAULT_PASSWORD="$(grep '^SEED_DEFAULT_PASSWORD=' $P | cut -d= -f2-)"
docker run --rm -e DATABASE_URL frontrow-api:render migrate
docker run --rm -e DATABASE_URL -e SEED_DEFAULT_PASSWORD frontrow-api:render seed
unset DATABASE_URL SEED_DEFAULT_PASSWORD
```

`-e NAME` with no `=value` passes the variable from the shell, so no secret appears on a command line or in
`docker inspect` history.

## 4. Cold start: what to expect

- **The free web service sleeps after about 15 minutes with no inbound request.**
  - The first request after that waits while the container starts, about 30 to 60 seconds.
  - The static site never sleeps, so the page loads and its first `/api/*` call is the slow one.
- **Neon autosuspends when idle** and wakes in about a second on the first query. `DB_CONNECT_TIMEOUT_MS=5000` covers
  that.
- **Nothing keeps either one awake**, by rule: no pings and no cron jobs.

## 5. Post-deploy checks

```sh
API=https://frontrow-api.onrender.com     # the URLs --apply printed
WEB=https://frontrow-web.onrender.com
curl -s $API/health/live                  # {"status":"live"}            (wakes the instance)
curl -s $API/health/ready                 # 200, checks db + redis ok    (one Neon query, on purpose, once)
curl -s $WEB/api/movies | head -c 300     # the rewrite reaches the API
curl -sI $WEB/some/deep/link | head -1     # 200: SPA fallback to index.html
```

Then, in a browser on `$WEB`:

1. Sign in as a seeded customer.
2. Hold and confirm a seat.
3. Confirm the session cookie survives the rewrite: a reload stays signed in.
4. Confirm the receipt is sent. It arrives only if the customer address is the Resend sign-up address. Otherwise the
   Resend dashboard shows the refusal, and the booking screen still shows the reference.

**The concurrency proof** (`SRC-002 §9.1`) is never waived and must also be run against this copy:

- 50 seeded customers hold one seat at once, and exactly one may win, counted in PostgreSQL.
- `--base-url` is the web URL, so the race goes through the real path (static site -> rewrite -> API).
- Pick a showtime and seat in the future:

```sh
export DATABASE_URL="$(grep '^FRONTROW_NEON_OWNER_URL=' $P | cut -d= -f2- | sed 's/-pooler\././')"
export SEED_DEFAULT_PASSWORD="$(grep '^SEED_DEFAULT_PASSWORD=' $P | cut -d= -f2-)" STRESS_OPERATOR="$USER"
docker run --rm -e DATABASE_URL --entrypoint python frontrow-api:render -c "import os,psycopg; print(psycopg.connect(os.environ['DATABASE_URL']).execute(\"SELECT ss.showtime_id, ss.seat_id FROM showtime_seat ss JOIN showtime s ON s.id = ss.showtime_id WHERE s.starts_at > now() + interval '1 hour' ORDER BY s.starts_at, ss.seat_id LIMIT 1\").fetchone())"
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD/scripts:/srv/stress:ro" -e DATABASE_URL -e SEED_DEFAULT_PASSWORD -e STRESS_OPERATOR \
  --entrypoint sh frontrow-api:render -c 'python stress/stress_seats.py --base-url '"$WEB"' --showtime <id> --seat <id> --n 50 --database-url "$DATABASE_URL"'
unset DATABASE_URL SEED_DEFAULT_PASSWORD
```

- **Pass:** exactly one 201, 49 × 409 `SEAT_UNAVAILABLE`, and one `booking_seat` row.
- **Wake the API first** with the `/health/live` curl above. A cold start inside the measured window is not a fair race.
- **The warm-up can be slow.** All 50 sign-ins come from one address, and the login bucket allows 30 per IP per
  15 minutes. The script waits out each 429 and retries, so the warm-up can take up to 15 minutes. That is expected,
  not a failure.
- **Stage B** (the red proof with the constraint dropped) is local only, and the script refuses a non-loopback URL.

## 6. What the free copy does NOT have

- **No poster storage.** There is no S3 bucket and no AWS credentials. Per the p6 lane's `[JUDGMENT CALL]` in
  `backend/app/domain/posters.py`:
  - Admin poster upload, and the admin poster read (`/api/admin/movies/{id}/poster`), answer
    **503 `DEPENDENCY_UNAVAILABLE`** with "The system cannot reach its file storage right now. The poster was not
    saved.…". It is never a bare 500.
  - Every other film action works: create, edit, publish, showtimes.
  - The customer poster route `GET /api/movies/{id}/poster` is not mounted. The image fails to load, and the client
    draws the film's title in the poster frame (`Poster.tsx`).
  - So **every film on the free copy shows a title card, never an image**, including the seeded films, whose key
    `posters/seed/placeholder-poster.png` points at a bucket that does not exist.
  - Upgrade path, no code change: an S3-compatible bucket, plus `AWS_ENDPOINT_URL_S3` and credentials in the env.
  - (`posters.py` comes with Round 4 batch 1, which this clone receives on its next `git pull aws main`. Until then
    the admin poster routes do not exist here.)
- **No worker and no queue.**
  - The receipt and reset emails are sent inline by the API after commit, bounded by `QUEUE_SEND_TIMEOUT_MS`.
  - A failed send is not retried by anything. The outbox row stays pending or failed until the customer presses
    resend. This is the `ponytail:` in `backend/app/workers/__init__.py`.
  - `/metrics` `queue_depth` renders NaN.
- **Mail reaches one address only** (the Resend sign-up address) until a domain is verified in Resend.
- **No Redis persistence.** Free Key Value loses its data on restart. A 3-minute hold does not need it, and the
  database still guards double-selling.
- **Client IPs for rate limiting are approximate.**
  - `FORWARDED_ALLOW_IPS=10.0.0.0/8` trusts Render's private network. The exact proxy hop is not published.
  - Behind the static site's rewrite, the rightmost `X-Forwarded-For` entry may be Render's rewrite proxy rather than
    the browser. In that case all visitors share one IP bucket, and, for example, the seat-map limit of 120/min is
    shared.
  - This is `ponytail:` in `scripts/render_deploy.py`. Upgrade path: log `client_ip` on a live request, then narrow
    or widen the trust from what is observed.
- **Cold starts, and one instance.** There is no graceful rolling deploy: a deploy restarts the only instance.
