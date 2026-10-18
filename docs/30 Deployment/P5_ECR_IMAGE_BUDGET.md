# P5 — The image budget and the ECR lifecycle policy (prep-queue row 32)

> **Zone C. The client builds it by hand.** Ruled by the council, `JC-R7-01` (2026-10-18, reversible): boto3 goes into
> the single api/worker image, and the budget is measured as the **compressed** size, because compressed is what an ECR
> push uploads and what ECR's 500 MB free tier counts. *(The free-tier accounting is reasoned, not observed.)*

## What the application expects

One image serves the api, the worker, `migrate` and `seed` (`SRC-003 OPEN-PROC-01`); the task definitions differ only
in their command. The budget below is a property of that one image.

## The budget

- **Under 150 MB compressed per image tag**, measured as `docker save <image> | gzip | wc -c`.
- **At most 3 tags retained per repository**, enforced by an ECR lifecycle policy: the running image, the one before it
  to roll back to, and one spare. **At the ceiling this does NOT fit the free tier**: 3 × 150 MB = 450 MB, plus the
  frontend's 3 × ~21 MB (row 1) = ~513 MB, over 500 MB. At today's measured 83.6 MB it is 3 × 83.6 + 3 × 21 ≈ 314 MB,
  which fits. The free tier runs out once the api image passes about 145 MB compressed ((500 − 63) / 3), a little
  before the 150 MB ceiling. *(reasoned, not observed)*
- `docker images` (uncompressed, on disk) is reported as a **trend only**. It is not the budget.

## Measured (local, 2026-10-18)

| Image | `docker save \| gzip \| wc -c` | `docker image inspect` Size | `docker images` |
|---|---|---|---|
| api, before boto3 | **66,250,561 bytes (66.3 MB)** | 66,671,399 | 286 MB |
| api, with boto3 1.43.100 + botocore | **83,604,944 bytes (83.6 MB)** | 84,030,031 | 340 MB |

boto3 costs about **17.4 MB compressed** (54 MB on disk, most of it `botocore/data`, the service models). At 83.6 MB the
image is well under 150 MB, so `botocore/data` is **not trimmed** (`JC-R7-01`: trim only above 150 MB).

## What to build

An ECR **lifecycle policy** on the api repository (and the frontend's, row 21) with one rule: *image count more than 3 →
expire*, applied to any tag status. Exact JSON is yours to write.

## Acceptance criteria

1. After a fourth push to the api repository, `aws ecr describe-images` lists exactly 3 images.
2. The running task's image digest is among them.
3. Each listed image's `imageSizeInBytes` is under 150,000,000.

## Common mistakes

- **Counting only tagged images.** Untagged images (a re-pushed tag leaves its old digest untagged) count against the
  500 MB too; the rule must cover them.
- **Expiring the running image.** Count-based expiry removes the oldest; an old, still-running task's image can go if
  you deploy four times without the service moving. Deploy, verify, then push again.
