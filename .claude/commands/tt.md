---
description: Close out the current work session — write a dated, named handoff (attributed to the machine's OS user by default), update PROGRESS.md, then commit & push. Scoped to both the project and the current user; works from any session, any repo.
argument-hint: [developer name — optional; defaults to the OS/login user]
---

You are **closing out a work session** in whatever repo this session is running in. Produce a
clean, resumable handoff so any other developer (or a future you) can pick up cold. The handoff is
scoped to **both the project (this repo) and the current user (the person on this machine)**, so
teammates' handoffs never collide. Do the steps below in order.

## 1. Identify the developer (scoped to this machine's user)
Resolve the developer identity automatically — **do not prompt if you can determine it.** Use the
first that yields a non-empty value:
1. `$ARGUMENTS` if non-empty (explicit override).
2. **The OS/login user of this machine** (Windows laptop / Mac / Linux) — cross-platform:
   - try `git config user.name` for a human-friendly name; AND
   - the login account: macOS/Linux `whoami` (or `$USER`); Windows `whoami` → strip the
     leading `DOMAIN\` (or `$env:USERNAME` / `%USERNAME%`).
   Prefer the login-account token for the **filename** (it's the stable per-user key the hook and
   `/ss` match on); you may use `git config user.name` as the display name in the handoff header.
3. Only if BOTH are empty, **ask** with AskUserQuestion: "What name should I attach to this
   handoff?" (free-text). Never invent a name.
Sanitize the chosen filename token to `[A-Za-z0-9-]` (lowercase it for consistency). Record both the
raw display name and the sanitized token; the token goes in the filename, the display name in the header.

## 2. Establish context (run these)
- Repo root: `git rev-parse --show-toplevel` (operate on THIS repo, wherever the session is).
- Timestamp: `date "+%Y-%m-%d_%H%M"` (sortable) and `date "+%A %d %B %Y, %H:%M %Z"` (human).
- Branch: `git rev-parse --abbrev-ref HEAD`.
- State: `git status --short`, `git log --oneline -12`.
- Read `PROGRESS.md` (if present) for the latest session block and its "Open / next" list.

## 3. Write the handoff file
Create `handoffs/HANDOFF_<stamp>_<Name>.md` (create the `handoffs/` folder if missing). Sanitize the
name to a filename-safe token (letters/digits/`-`). Include these sections:
- **Header** — date-time (human + stamp), developer name, repo, branch, latest commit sha+subject.
- **What this session did** — concrete, factual bullets (what was built/decided/fixed). No hype.
- **Current state** — working tree clean or dirty (list dirty files); CI/gate status; infra/secrets
  status; anything deployed.
- **In progress (READ FIRST)** — anything started but not finished, with exactly where it stands and
  how to continue. If a gate is red or a task half-done, say so plainly — never imply done.
- **Next ready steps** — the ordered next actions (pull from PROGRESS.md "Open / next" if present).
- **Blockers / decisions pending** — owner/external dependencies, decisions awaiting a human.
- **Resume protocol** — `git pull`; recover any In-Progress first; read `CLAUDE.md` + `GOTCHAS.md`
  (if the repo has them); then take the next ready unit of work.

## 4. Update PROGRESS.md
If the repo keeps a `PROGRESS.md`, append a one-line close entry under the current session block (or a
new dated block): `- **Session closed <stamp> by <Name>** → handoff: handoffs/HANDOFF_<stamp>_<Name>.md`
(If there is no PROGRESS.md and the project clearly doesn't use one, skip this — don't invent process.)

## 5. Commit & push
- `git add -A`
- Guard: confirm no real secret is staged. Inspect `git diff --cached` for anything that looks like a
  live credential (API keys, DB URLs with passwords, tokens, private keys) and for a committed `.env`.
  If found, unstage it and stop — never commit secrets.
- Commit: `chore(handoff): close-out <stamp> by <Name>` with the standard `Co-Authored-By` trailer.
- Push to the current branch's upstream. If push is rejected, `git pull --rebase` then push.

## 6. Report
Tell the user: the handoff path, the commit sha, working-tree-clean confirmation, and the single most
important "next step" so they can resume instantly. Then the session is safe to close.

## Rules
- Never leave a half-finished task or a red gate undocumented. Honesty over tidiness.
- Operate only on the current git repo; do not touch other repos/worktrees.
- Do not fabricate progress, dates, or a developer name.
- Adapt to the repo you're in: use the artifacts that exist (PROGRESS/CLAUDE/GOTCHAS/ledger) and
  don't manufacture ones it doesn't. The handoff itself is the one required output.
