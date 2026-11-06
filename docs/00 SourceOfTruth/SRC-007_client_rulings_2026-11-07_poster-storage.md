# SRC-007 — FrontRow client rulings, fifth batch: poster storage per deployment

```
Source type ....... Client ruling, typed in chat
Received .......... 2026-11-07, build session chat
Author ............ Aniruddha Jathar (the client)
Status ............ FROZEN — never edited
Citation form ..... SRC-007 <ROW-ID>
Supersedes ........ nothing (refines SRC-002 §4 "S3, for movie posters the admin uploads" for the free copy only)
```

> **FROZEN INPUT. DO NOT EDIT.** Ruling blocks are the client's words verbatim, or the option they
> selected. Anything under `Filed as` is the build session's reading and is **not** client text.
> The only permitted modification is a clearly marked `ERRATUM` appended at the foot.

## STORE-1 · Posters: Cloudflare R2 on the Render copy, Amazon S3 on AWS · `RULED`

**Ruling (typed):** *"instead change this in docs for render website we will go with r2 and for the frontrow_aws we
will go with s3."*

**Context:** the build session laid out three free-tier choices for the Render copy (Cloudflare R2, Backblaze B2, and
posters stored in Neon). The client chose R2 and is creating the R2 bucket and token himself.

**Filed as:**
- **AWS (`frontrow_aws`, the deployment of record): unchanged.** Posters live in a private S3 bucket (`SRC-002 §4`),
  and every AWS item stays in the client's Zone C.
- **Render (`frontrow`, the free copy): a private Cloudflare R2 bucket,** `frontrow-posters`, reached through R2's
  S3-compatible API.
  - **No R2-specific application code.** boto3 reads `AWS_ENDPOINT_URL_S3` from the environment, so the same S3
    client, upload path and (once built) presigned redirect serve both. The difference is configuration only, and it lives in
    `frontrow/DEPLOY_RENDER.md`.
- **The bucket stays private.** Customers will get the poster through the short-lived presigned redirect that
  `S-BRW-18` specifies (`GET /api/movies/{id}/poster`, not built as of 2026-11-07). It is never public and never
  hotlinked.
- **Credentials:** an R2 API token scoped to that one bucket, Object Read & Write. Its values live in
  `D:/Project/FrontRow/passwords.txt` (`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT`, `R2_BUCKET`) and in
  the Render service environment, never in either repository.
- **Free-tier limits** (Cloudflare's published R2 free tier, not measured): 10 GB stored, 1 million writes and
  10 million reads a month, no egress charge. The demo uses a few megabytes.
