# SRC-005 — FrontRow client rulings, third batch: the always-on free deployment

```
Source type ....... Client rulings, typed in chat and four structured answers
Received .......... 2026-10-18 (night), build session chat
Author ............ Aniruddha Jathar (the client)
Status ............ FROZEN — never edited
Citation form ..... SRC-005 <ROW-ID>
```

> **FROZEN INPUT. DO NOT EDIT.** Ruling blocks are the client's words verbatim, or the option they
> selected. Anything under `Filed as` is the build session's reading and is **not** client text.
> The only permitted modification is a clearly-marked `ERRATUM` appended at the foot.

## D-1 · Two deployments, two repositories

**Ruling (typed):** *"even if we made this project end to end on AWS this project will also be made
on neon and hosted on render for free. Since i want my website to be runninig all the time it will
just be hopsted on things which will cost me nothing and when i will go for an interview and
recuruter asks then only i will deploy thhis and restart all the things that we are going to build
on AWS for short period of time. so inside the frontrow make 2 folders frontrow_aws and frontrow,
and do the same on githuhb"*

**Filed as:**
- `frontrow_aws/` → GitHub `AniruddhasGit/FrontRow_AWS`. The build this repository's documents
  describe, unchanged: `SRC-002 §4` still binds it.
- `frontrow/` → GitHub `AniruddhasGit/FrontRow`. The same application, deployed at $0. It is a
  **deployment variant**, not a second product. Its differences from `SRC-002 §4` are listed in D-2
  and nowhere else.
- The Render copy tracks the AWS copy's `main` as a git remote; Render-only files are commits on top.
  One codebase, so a fix lands once.

## D-2 · Where the free copy runs

**Ruling (selected):** frontend → *"Render static site"*. Receipt email → *"Send from the API via
Resend"*. Repository access → *"I'll grant it now"* (the client installs Render's GitHub app on the
private repo). **Authorised tonight, free plans only:** *"Neon project 'FrontRow', Render services,
Push code to GitHub FrontRow"*.

**Filed as** — the free copy substitutes, against `SRC-002 §4`:

| SRC-002 §4 (AWS) | Free copy | Why |
|---|---|---|
| ECS on EC2 behind an ALB | Render free web service (Docker), same image | $0; sleeps after ~15 min idle, ~30–60 s cold start |
| nginx frontend container | Render static site, `/api/*` rewritten to the API | $0, never sleeps |
| RDS PostgreSQL | Neon free, project `FrontRow`, aws-ap-southeast-1 | $0; autosuspends, wakes in about a second |
| ElastiCache Redis | Render free Key Value | $0; no persistence, which 3-minute holds do not need |
| SQS + worker | none: the free tier has no background worker | the email is sent from the API process (Phase 5 work) |
| SES | Resend, a send-only API key | $0 for 3,000/month; only the sign-up address until a domain is verified |

The two invariants that are never waived hold on the free copy too: the database guard against
double-selling, and the 50-request concurrency proof (run against the free copy's URL).

Secrets: the Neon, Render and Resend keys and every connection string live in the client's local
`passwords.txt`, never in either repository.
