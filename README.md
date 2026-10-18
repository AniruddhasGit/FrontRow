# FrontRow

A movie ticket booking platform. A customer browses what is playing, picks a cinema and a showtime,
sees a live seat map, chooses seats, pays, and arrives with a ticket on their phone.

**A seat is never sold twice.** That is the product's central promise and the reason most of the
engineering here exists.

Built end to end from documents, by LLMs, using the AI-SDLC method proved on
[SpendWise](https://github.com/AniruddhaDynpro/SpendWise). **The build session writes application
code. The client builds all AWS by hand**, because the point of this project is that deploying and
operating it teaches DevOps.

---

## Status — 2026-10-18

**Phase 1 code exists** (`goals/GOAL_14_phase-1-skeleton.txt`): the repo skeleton, configuration
validation, `/health/live` and `/health/ready`, JSON logging with request ids, graceful shutdown, and
a local `docker-compose.yml`. **Nothing else.** No data model, no auth, no movie. The client deploys
this to ECS before Phase 2 begins (`SRC-002 §12.2`). The Zone C specifications for that deploy are in
`docs/30 Deployment/ZONE_C_PHASE1_INDEX.md`.

## Run Phase 1 locally

Needs Docker. **`docker-compose.yml` is for local development only.**

```
docker compose up -d --build
```

| What | URL |
|---|---|
| API liveness | <http://localhost:8000/health/live> → `{"status":"live"}` |
| API readiness | <http://localhost:8000/health/ready> → 200, or 503 naming `postgres` / `redis` |
| Frontend | <http://localhost:8080/> |
| PostgreSQL | `localhost:55433` (user `frontrow`, local-only password in the compose file) |
| Redis | `localhost:56379` |

Things to try, and what you should see:

- `docker compose stop redis`, wait 4 s, then call `/health/ready`: **503** `redis: unreachable`. `/health/live` stays **200**.
- `docker run --rm frontrow-api:phase1` with no variables set: **exit 78** and one JSON line naming `DATABASE_URL` and `REDIS_URL`.
- `docker compose stop api`, then `docker compose logs api`: the log ends with `stop signal received` followed by `api stopped cleanly`, and the exit code is 0.

Tests run inside the same Python 3.12 image as production:

```
docker build --target test -t frontrow-api-test backend
docker run --rm frontrow-api-test
```

## How this repository works

Documents are written in a fixed order, each one derived only from the ones before it, and code is
written last — from documents, not from a conversation. Every sentence downstream cites a clause of
a frozen, hashed source.

```
00 SourceOfTruth ──► 02 BRD ──► 03 PRD ──► 05 Bible ──► 06 DataModel ──► code
       │                                                      ▲
       └──► 01 ADR ────────────────────────────────────────────┘
            every ruling, and proof it landed in each document above
```

`docs/README.md` is the index. `docs/` folders are numbered in **dependency order**, which is not
the same as the order they get written in.

## The session loop

```
/ss                    orient — reads the newest handoff, PROGRESS, CLAUDE.md, GOTCHAS,
                       reconciles them against git, recommends ONE restart point
      ↓
write a goal           goals/GOAL_<nn>_<slug>.txt — a write-set and a binary Definition of Done
      ↓
build                  the session works the goal until its DoD is met
      ↓
/tt                    writes handoffs/HANDOFF_<stamp>_<user>.md, appends PROGRESS.md,
                       commits and pushes
```

**GitHub is the source of truth.** Nothing important lives in a chat history, on one laptop, or in
one model's context. The test of that rule: a session starting cold on a different machine, under a
different account, with `/ss` and this repository alone, must reach full situational awareness.

A session that ends without `/tt` has lost its memory.

## Where to start reading

| If you want to know | Read |
|---|---|
| what a session must know first | `CLAUDE.md` |
| the rules the project itself obeys | `CONSTITUTION.md` |
| what has already bitten someone | `GOTCHAS.md` |
| what is undecided and who owns it | `CONSTITUTION.md` Article X |
| what the client actually asked for | `docs/00 SourceOfTruth/SRC-001` |
| how it must be built, and by whom | `docs/00 SourceOfTruth/SRC-002` |
| what happened last session | `PROGRESS.md`, then the newest file in `handoffs/` |
| what to build next | `goals/README.md` |
| who owns which files when two sessions run | `COORDINATION.md` |

## Stack

React + Vite + TypeScript · Python 3.12 + FastAPI · PostgreSQL · Redis · SQS · Alembic · Docker on
ECS backed by EC2, behind an Application Load Balancer · S3 · SSM Parameter Store.

Fixed by `SRC-002 §4`. Not substitutable, even for something better. Everything must fit inside AWS
Free Tier, which means roughly **1 GB of RAM across every container** and a final image under
**250 MB**.

## Attribution

Movie data and images come from [TMDB](https://www.themoviedb.org/). This product uses the TMDB API
but is not endorsed or certified by TMDB. The attribution is a licence condition, not a design
choice.

## Licence

Not yet decided. Until it is, all rights reserved.
