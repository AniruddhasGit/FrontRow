# P1 · ECR repositories  (prep-queue row 1 · needed by Phase 1)

> Zone C specification. What to build, not how. Every claim about AWS behaviour is **reasoned, not observed**.

## 1. What you need to build

- **One private repository per image**: one for the api image, one for the frontend image. A worker
  image is not needed. From Phase 5 the worker runs from the **api image** with a different command.
- A rule that keeps total storage **under the 500 MB free tier** (`SRC-002 §5.2.5`). The usual tool is
  a lifecycle policy that expires old images. How many to keep is your decision.
- Tags that identify a build. The commit SHA is the usual choice. `latest` alone does not, because the
  same tag then means different code on different days.

## 2. What the application expects

| Image | Built with | `docker images` (local, containerd store) | Compressed content (what a registry stores) |
|---|---|---|---|
| api | `docker build -t <repo>:<tag> backend/` | **239 MB** | **56.5 MB** (56,498,125 bytes) |
| frontend | `docker build -t <repo>:<tag> frontend/` | **73.9 MB** | **21.0 MB** (21,046,395 bytes) |

Measured locally on 2026-10-18 (GOAL_14 gate), and re-measured the same day after a rebuild: the compressed column is the sum of the gzip layer and config sizes in each image's manifest, which are the blobs a push uploads. A rebuild moves the byte count by a few kB. **Which of the two columns ECR counts against the
500 MB is reasoned, not observed.** The compressed figure is the likely one, which would make one
api+frontend pair about 77.5 MB, roughly six versions of both images. Check the repository's reported
image size after your first push, and write the real number into the prep queue.

The images are built for **linux/amd64**, which is what a `t3.micro` runs. If you build on an Apple
Silicon machine, the default build is `arm64`, and the task fails at start with `exec format error`.

## 3. Acceptance criteria

1. Two repositories exist, named for this project, separate from SpendWise's `spendwise` repository.
2. Each holds at least one image whose tag is not only `latest`.
3. A rule exists that stops storage growing past 500 MB without you remembering to delete things.
4. The image size ECR reports for the api image is written into the prep queue's "What exists" column.

## 4. Common mistakes

- **Pushing an `arm64` image from a laptop.** The image pulls, the container starts, and it exits
  immediately with `exec format error`. Nothing in ECR warns you.
- **Mutable `latest` as the only tag.** A task definition pointing at `:latest` pulls whatever was
  pushed most recently. A rollback is then impossible, because the old image no longer has a name.
- **No expiry rule.** Every push adds ~77 MB. The seventh deploy is the one that starts costing money,
  and nothing tells you it did.
