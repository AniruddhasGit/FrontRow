# syntax=docker/dockerfile:1
# =====================================================================================================
# FrontRow API image  -  ZONE B (SRC-002 §6.2.1): written by the build session, edited by the client.
#
# Every line that exists for a production reason carries a comment saying WHAT BREAKS WITHOUT IT.
#
# Stages, in order:
#   base     the slim Python runtime both other stages start from
#   builder  compiles/installs the pinned dependencies into a virtualenv
#   test     builder + test tools + tests. `docker build --target test .` runs the suite.
#   runtime  LAST, so a plain `docker build .` produces the deployable image and never the test one
#
# Build:   docker build -f backend/Dockerfile -t frontrow-api .     (from the REPOSITORY ROOT - see below)
# Measure: docker save frontrow-api | gzip | wc -c        <- THE BUDGET: under 150 MB per tag, at most 3 tags kept
#          by an ECR lifecycle policy (council ruling JC-R7-01, 2026-10-18; docs/30 Deployment/P5_ECR_IMAGE_BUDGET.md).
#          Compressed is what a push uploads. `docker images` is reported as a trend only.
#          2026-10-18: 66.3 MB compressed before boto3, 83.6 MB with it (boto3 + botocore, Phase 5);
#          `docker images` 286 MB -> 340 MB. botocore/data is NOT trimmed: trim only if compressed passes 150 MB.
#
# The build context is the repository root, not backend/: the seed command runs scripts/seed.py, and
# scripts/ sits beside backend/ (SRC-002 §11). The root .dockerignore admits only backend/ and scripts/,
# so the context stays small. Building with `backend/` as the context fails at the first COPY.
# =====================================================================================================

# Exact patch tag, not `3.12-slim`: a floating tag silently changes the interpreter under you between
# two builds of the same commit, and "nothing changed" stops being true.
# `slim` (Debian, glibc) rather than `alpine` (musl): the prebuilt manylinux wheels for psycopg and
# pydantic-core are the ones every CI and laptop also uses; musl is a second libc to debug against.
# `trixie` (Debian 13) rather than `bookworm` (Debian 12): measured in Phase 1, bookworm put the image
# at 258 MB by `docker images` and trixie at 239 MB. Since the Phase 2 dependencies the image is 286 MB by
# that measure even on trixie - see the Measure note in the header. trixie is still the smaller base.
FROM python:3.12.15-slim-trixie AS base

# Without PYTHONDONTWRITEBYTECODE Python writes .pyc files next to the source at import time. On a
# read-only root filesystem that fails, and on a writable one it is a file written to disk by a
# container that must be stateless (SRC-002 §7.3, P-XCT-18).
ENV PYTHONDONTWRITEBYTECODE=1 \
    # Without PYTHONUNBUFFERED stdout is block-buffered when it is not a terminal (it never is in a
    # container). The last log lines before a crash sit in the buffer and die with the process, which
    # is exactly the record you need when a task is crash-looping.
    PYTHONUNBUFFERED=1 \
    # Without this pip checks PyPI for its own new version on every install: a network call during a
    # build that can fail the build for a reason unrelated to the code.
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Without this pip keeps a download cache in the layer: tens of MB of the 250 MB budget, for
    # files nothing ever reads again.
    PIP_NO_CACHE_DIR=1


# ----------------------------------------------------------------------------------------- builder
FROM base AS builder

# A virtualenv gives the runtime stage ONE directory to copy. Without it the packages are scattered
# through the system site-packages and the multi-stage copy either misses some or drags in pip and
# the build toolchain, which is the single largest avoidable contribution to image size (P-XCT-21).
# --without-pip: the base image's own pip installs INTO the venv (`pip --python`), so the venv never
# contains pip. Without this, 13 MB of pip ships in the runtime image (measured on this build), for a
# tool the running API never uses - and a package installer inside a production container is a
# capability nobody should have there.
RUN python -m venv --without-pip /opt/venv
# Without it, python below resolves to the system interpreter and runs outside the venv.
ENV PATH="/opt/venv/bin:$PATH"

# Without a WORKDIR, COPY puts requirements.txt in `/` and the build runs in the filesystem root,
# mixing the project's files with the OS's own. /build exists only in this stage and never ships.
WORKDIR /build
# Requirements are copied BEFORE the source so the dependency layer is cached. Without this ordering
# every one-line code change reinstalls every dependency and a build takes minutes instead of seconds.
COPY backend/requirements.txt backend/requirements-dev.txt ./
# The runtime dependencies, into the venv. Without them the runtime stage copies an empty venv and the
# container exits at the first import.
RUN /usr/local/bin/pip --python /opt/venv/bin/python install -r requirements.txt


# -------------------------------------------------------------------------------------------- test
# Not deployed. Exists so the tests run on the same interpreter, OS and wheels as production.
FROM builder AS test
# The test tools, in this stage only. Without them there is no pytest; installed here, they never reach
# the runtime image.
RUN /usr/local/bin/pip --python /opt/venv/bin/python install -r requirements-dev.txt
# psql, TEST STAGE ONLY: the database tests run docs/06 DataModel/checks/roles_local.sql and
# verify_invariants.sql verbatim, and both are psql scripts (\set, :'var'). Without it those checks
# would have to be re-typed in Python, and a re-typed check can drift from the file of record.
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
# The same non-root user as runtime, so a test that only passes as root cannot pass here.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin frontrow
# The same /srv as runtime, so `import app` resolves from the same directory in tests as in production.
# Without it pytest runs from /build, finds no tests and no pyproject.toml, and exits "no tests ran".
WORKDIR /srv
# pytest's configuration (test paths, pythonpath, no cache directory). Without it pytest finds no tests.
COPY backend/pyproject.toml ./
# The code under test, the same files the runtime stage copies.
COPY backend/app ./app
# The migration revisions, so the database tests can run the real `migrate` command.
COPY backend/migrations ./migrations
# The entrypoint, so the database tests run `migrate` through it exactly as the task does.
COPY backend/entrypoint.sh ./entrypoint.sh
# The tests themselves. Without them `docker run` of this stage reports "no tests ran".
COPY backend/tests ./tests
# The non-root user created above, so a test that only passes as root fails here.
USER 10001
# `docker run` of this stage runs the suite.
CMD ["python", "-m", "pytest"]


# ----------------------------------------------------------------------------------------- runtime
FROM base AS runtime

# A non-root user created here. Without it the process runs as root: a code-execution bug becomes
# root inside the container, and P-XCT-18 requires both images to run unprivileged.
# Consequence you will meet: a non-root process cannot bind a port below 1024, which is why
# API_PORT defaults to 8000 and the target group must point at 8000, not 80.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin frontrow

# Only the virtualenv crosses over from builder: no pip cache, no build artefacts, no test tools.
# Without the multi-stage copy the image carries everything the build needed and nothing the
# process uses, and ECR's 500 MB free tier holds fewer image versions (SRC-002 §5.2.5).
COPY --from=builder /opt/venv /opt/venv
# Without the venv on PATH, `python` is the system interpreter, which has none of the dependencies,
# and the container exits at the first import.
ENV PATH="/opt/venv/bin:$PATH"

# Without WORKDIR /srv the process starts in `/`, `COPY app ./app` lands at /app, and the
# entrypoint's `python -m app` (which finds the `app` package in the current directory) fails with
# "No module named app". WORKDIR also creates /srv owned by root, which the next comment relies on.
WORKDIR /srv
# Owned by root and not writable by the runtime user: the application has no reason to modify its
# own code, and a process that cannot write here cannot be tricked into persisting anything here.
COPY backend/app ./app
# The revisions the entrypoint's `migrate` command applies. Same image as the code, so the migration
# and the code it serves are always the same build (P-XCT-19). Without it `migrate` finds nothing.
COPY backend/migrations ./migrations
# The seed, for the entrypoint's `seed` command (P-XCT-32). Same image as the code, so the seed writes rows
# the code it ships with can read. Without it `seed` exits "can't open file 'scripts/seed.py'" and the
# one-off seed task can never succeed.
COPY scripts/seed.py ./scripts/seed.py
# The placeholder poster the seeded films point at: the seed refuses to run without it. 1.5 KB.
COPY scripts/assets ./scripts/assets
# 0555 = executable and read-only for everyone. Without the exec bit the container fails at start
# with "permission denied"; without read-only, the runtime user could rewrite its own entrypoint.
COPY --chmod=0555 backend/entrypoint.sh /usr/local/bin/frontrow-entrypoint
# Without this, a checkout on Windows with git's CRLF conversion produces "#!/bin/sh\r", and the
# container dies at start with the baffling "/bin/sh^M: not found" (or "no such file or directory").
RUN sed -i 's/\r$//' /usr/local/bin/frontrow-entrypoint

# Drop to the non-root user created above. Without it the API runs as root (P-XCT-18).
USER 10001

# Documentation only: EXPOSE opens nothing. The port the process binds is API_PORT (default 8000).
# The target group, the security group ingress rule and the container port mapping are all built
# against this number (Zone C). If they disagree, the container looks healthy in its own logs and
# fails every load balancer health check.
EXPOSE 8000

# Container-level LIVENESS check -> /health/live, never /health/ready (SRC-002 §7.4, PRD S7.7).
# Wiring a restart check to /health/ready turns a recoverable database blip into a restart loop.
# Note: ECS IGNORES a Dockerfile HEALTHCHECK. It applies to `docker run` / docker compose only.
# On ECS the same check must be written into the task definition's healthCheck (Zone C, yours).
# Python's urllib, because the slim image has no curl, and installing curl for this costs MB.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/health/live' % os.environ.get('API_PORT','8000'), timeout=2).status == 200 else 1)"]

# ENTRYPOINT in exec form, so the entrypoint is PID 1 and receives SIGTERM directly. In shell form
# (`ENTRYPOINT frontrow-entrypoint api`) PID 1 is /bin/sh, which does not forward SIGTERM: the app
# never drains, and after the stop timeout ECS sends SIGKILL mid-request.
ENTRYPOINT ["frontrow-entrypoint"]
# The default command starts the API. `migrate` is a separate, explicit command and is NEVER the
# default (SRC-002 §7.8): an image whose default runs migrations runs them on every task start, and
# two tasks starting together race on the same schema change.
CMD ["api"]
