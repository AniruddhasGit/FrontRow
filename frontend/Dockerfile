# syntax=docker/dockerfile:1
# =====================================================================================================
# FrontRow static frontend image  -  ZONE B (SRC-002 §6.2.1). Edited by the client.
# Two stages: Node builds the static files, nginx serves them. NO Node process runs in production.
# Every production line says what breaks without it.
# =====================================================================================================

# -------------------------------------------------------------------------------------------- build
# Exact patch tag (22.23.3, verified with `docker pull` on 2026-10-18; it resolves to the same image
# ID as `node:22-alpine` did that day). A floating `22-alpine` moves to a new patch release between
# two builds of the same commit, and "nothing changed" stops being true. Only used to build; nothing
# from this stage ships except dist/.
FROM node:22.23.3-alpine AS build
# Without a WORKDIR the COPY and RUN lines below work in `/`, so `npm ci` writes node_modules at the
# filesystem root next to /bin and /etc, and the `COPY --from=build /build/dist` in the runtime stage
# finds nothing at /build and fails the build.
WORKDIR /build
# Manifests first, so the dependency layer is cached: without this order every source edit reinstalls
# every package.
COPY package.json package-lock.json ./
# `npm ci`, not `npm install`: ci installs EXACTLY the lockfile and fails if it disagrees with
# package.json. `install` may resolve different versions on a different day.
RUN npm ci --no-audit --no-fund
# The build inputs, AFTER `npm ci`, so editing a component reuses the cached dependency layer.
# Without any one of these files the build fails: tsc needs tsconfig.json, vite needs its config and
# the index.html entry point, and src is the application.
COPY tsconfig.json vite.config.ts index.html ./
# The application source. Without it the build has nothing to compile.
COPY src ./src
# Type-checks and builds. A type error fails the image build instead of shipping.
RUN npm run build

# ------------------------------------------------------------------------------------------ runtime
# Exact patch tag (1.27.5, verified with `docker pull` on 2026-10-18; same image ID as `1.27-alpine`
# that day). A floating `nginx:alpine` or `1.27-alpine` changes the server under you between two builds.
# The alpine OS packages inside the tag are still rebuilt by the publisher under the same tag, so
# only an image digest (@sha256:...) is truly immutable; the tag pins the nginx version, not the bytes.
FROM nginx:1.27.5-alpine AS runtime
# Replaces the image's own nginx.conf. Without it nginx runs as the image ships it: logging to files,
# a pid in /var/run and port 80 - none of which work as a non-root user on a read-only filesystem.
COPY nginx.conf /etc/nginx/nginx.conf
# Only the built static files cross from the build stage. Without the multi-stage copy the image
# would carry Node and node_modules (hundreds of MB) to serve a few hundred kB of files.
COPY --from=build /build/dist /usr/share/nginx/html
# Run as the image's unprivileged `nginx` user. Without this nginx's master process runs as root,
# and a bug in it is root inside the container.
USER nginx
# Documentation only. The target group and security group must use 8080 (Zone C).
EXPOSE 8080
# Container-level liveness: can nginx serve a static file? (PRD S7.7: "a static web server that can
# serve a file is working.") busybox wget ships in alpine, so nothing is installed for this.
# ECS ignores this line; the task definition needs its own healthCheck (Zone C).
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/index.html"]
# Bypass the image's /docker-entrypoint.sh. Without this its start-up scripts try to rewrite files
# in /etc/nginx/conf.d, which fails (and logs non-JSON noise) as a non-root user on a read-only
# filesystem. `daemon off` keeps nginx in the foreground as PID 1, so it receives SIGTERM directly.
ENTRYPOINT ["nginx", "-g", "daemon off;"]
# nginx treats SIGTERM as "fast shutdown" and SIGQUIT as "graceful". Without this, `docker stop`
# and ECS (both send STOPSIGNAL) would cut off responses in flight.
STOPSIGNAL SIGQUIT
