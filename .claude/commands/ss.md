---
description: Start-of-session orientation — read the latest handoff, PROGRESS, CLAUDE.md, GOTCHAS, and (if present) the execution plan + backlog + engineering ledger, reconcile them against the actual repo, and ground on exactly where to restart. The mirror of /tt. Works from any session, any repo, any developer.
argument-hint: [optional focus — an epic/story id (e.g. "E15") or "just orient"]
---

You are **starting (or resuming) a work session cold** in whatever repo this session is running in.
Your job is to reconstruct full situational awareness from the artifacts `/tt` wrote and the project
canon, **reconcile them against what the repo actually says**, and land on a single, grounded "here is
where we restart" recommendation. This is the inverse of `/tt`: `/tt` serializes a session to disk;
`/ss` rehydrates it.

Be holistic and skeptical. **Narration (PROGRESS/handoff prose) describes intent; the ledger + git +
gates describe reality.** When they disagree, that gap is the most valuable thing you can surface — do
not paper over it. Use your own judgment to connect the dots the files leave implicit.

Do the steps in order. Do not skip the reconciliation step (§3) — it is the point of this command.
**Adapt to the repo you're in**: use whichever of these artifacts exist and don't assume ones that
don't. Discover paths rather than hardcoding them.

## 1. Establish ground truth (run these first)
- Repo root: `git rev-parse --show-toplevel` (operate on THIS repo, wherever the session is).
- **Identify the current user** (this session is scoped to the person on this machine, not just the
  repo): resolve the OS/login user — cross-platform: `whoami` (strip a leading `DOMAIN\` on Windows) /
  `$USER` / `$env:USERNAME` — and `git config user.name`. Hold this as `me` for §2–§4.
- `git pull` on the current branch (fast-forward). If it can't, note why and continue read-only.
- Branch: `git rev-parse --abbrev-ref HEAD`; state: `git status --short`; recent: `git log --oneline -15`.
- Timestamp for the brief: `date "+%A %d %B %Y, %H:%M %Z"`.
- **Recover-first flag:** if the working tree is dirty or a branch looks mid-flight, hold that finding
  for §3 — uncommitted/half-finished work is recovered before any new story is picked.

## 2. Read the resume artifacts (the files `/tt` writes + the canon)
Read enough of each to extract the specific facts noted, not to summarize for its own sake. Skip any
that this repo doesn't have.
- **Latest handoff** — the newest `handoffs/HANDOFF_<stamp>_<user>.md` (sort by the `<stamp>` in the
  filename, not mtime). Extract its **In progress (READ FIRST)**, **Next ready steps**, **Blockers**,
  and **Resume protocol** sections. This is the previous session's own account of where it stopped.
  **User-scoping:** the trailing `<user>` token in the filename is the author. Note whether the newest
  handoff is **yours** (`me`) or a **teammate's**. Also locate *your own* most recent handoff
  (`HANDOFF_*_<me>*.md`) — if you are resuming your own thread it may differ from the global newest.
  Read the newest overall for project state; read your own for where *you* personally left off.
- **PROGRESS.md** — the last dated session block(s) and any "Open / next" bullets. This is the
  running narrative; treat it as claims to verify, not settled fact.
- **CLAUDE.md** — mission, the frozen decisions / ADRs, the **non-negotiable invariants**, the
  execution order & resumability rules, the **Definition of Done**, and the release/governance gates.
  This is the constitution — it overrides narration on *how* to build. Do not reopen frozen ADRs.
- **GOTCHAS.md** — skim the trap list; keep the relevant ones in working memory for whatever comes next.
- **COORDINATION.md** — only if ≥2 sessions run in parallel: the lane map, migration bands, and
  shared-primitive locks. Respect territory before touching shared files.
- **The execution / build plan** — whatever the repo uses to sequence work (e.g. an
  `EXECUTION_PLAYBOOK.md`, a build/game plan, a roadmap): read the milestone sequence, the per-story
  loop, and the win condition. An architecture doc, if present, is an **answer key** to consult for a
  specific question — **not** scope authority.
- **The engineering ledger** — the **single authoritative progress source**: a delimited file
  (usually a `.tsv`) with one row per unit of work and, among its columns, `Milestone` and `Status`
  (other typical columns: `ID Title Epic Lane Classification Risk DependsOn OwnedPaths SourceRef
  GoalRef`). Discover it (look under `docs/backlog/`, `docs/`, or repo root for a `*ledger*.tsv`; honor
  `$CLAUDE_LEDGER_PATH` if set). **Anchor to the column HEADER names, never a fixed position** — the
  column order can change and a hardcoded index would silently mis-read. Compute the per-milestone
  Status matrix with a header lookup, e.g. (adjust the filename to the one you found):
  `awk -F'\t' 'NR==1{for(i=1;i<=NF;i++){if($i=="Milestone")mc=i;if($i=="Status")sc=i};next}{m=$mc;s=$sc;if(s=="")s="(empty)";print m"\t"s}' <ledger.tsv> | sort | uniq -c`
- **The epic/story backlog ("the Bible")** — the frozen-scope CSV: one row per story with its
  `AcceptanceCriteria` (the self-contained spec — no scope beyond it). Discover it (look for a backlog
  `*.csv` alongside the ledger). Pull the AC for the story you land on, once the next story is chosen.

## 3. Reconcile & ground (the heart of this command)
Cross-check the three sources — **ledger Status ↔ PROGRESS/handoff narration ↔ actual git/code** —
and resolve to one grounded picture. Do NOT blindly apply "lowest-milestone ready backlog story"
before this reconciliation; that rule assumes the ledger is trustworthy, and it drifts.
- **Drift hunt.** Flag every mismatch and investigate before trusting either side:
  - Stories the ledger marks `Backlog`/`(empty)` that PROGRESS/handoff/git say are built + merged
    (a *reconcile-down* miss — the code exists, the Status was never flipped). Verify against
    `git log`/the code before concluding; if real, note it as a ledger-hygiene fix, not new work.
  - Stories the ledger marks `Done` with no supporting commit or with a red/absent gate (a *fake
    green* — the integrity failure most projects forbid). Escalate loudly.
  - `In Progress` stories in the ledger (someone stopped mid-story) → these are recovered FIRST.
  - Documented deferrals in the handoff (work explicitly pushed to a later milestone/epic): these are
    intentional, NOT unfinished current-milestone work — do not re-pick them.
- **Compute the next ready story** per CLAUDE.md's execution order, *after* accounting for drift:
  by ascending milestone, then the parent story's `DependsOn`, then ascending task number within a
  story. "Ready" = Status `Backlog`, all `DependsOn` are truly `Done`, no blocker. If a lower
  milestone shows `Backlog` rows that reconciliation proves are actually built (drift), the true
  frontier is the next milestone — say so explicitly and recommend fixing the stale Status.
- **Honor the handoff's pointer, but verify it.** If the latest handoff's "next" and the ledger
  frontier agree, converge. If they conflict, present both and recommend the one the *repo* supports —
  with the reason.
- **Sanity-check the ground isn't stale** (cheap, high-value): working tree really clean? does the
  repo's ledger/gate check (whatever it defines) pass? is `main` green / prod healthy if the handoff
  claims so? Trust the check over the prose. Spot-check only — do not run the full CI suite.

## 4. Report — the orientation brief
Deliver a tight, skimmable brief (no fluff). Structure:
- **Who + where we are** — open with "You are `<me>` on `<repo>` @ `<branch>`." Then milestone/epic
  progress from the *ledger matrix* (e.g. "M1 35/35 Done; M2 0/30; frontier = M2"), latest commit,
  working-tree state, deploy/gate status you verified. (If the repo has no ledger, say so and orient
  from PROGRESS + git instead.)
- **Last session** — 2–4 bullets on what the most recent handoff + PROGRESS block actually did. Say
  whether it was **your** last session or a **teammate's** (by the handoff's `<user>` token), and if
  your own latest differs from the global newest, note both.
- **⚠️ Reconciliation findings** — every drift/discrepancy from §3, or "none — ledger, narration, and
  git agree." This section earns the command its keep; never omit it.
- **Recover-first** — any In-Progress / uncommitted / red-gate work to finish before new work, with
  exactly where it stands. Prioritize **your own** (`me`) unfinished thread first, but surface a
  teammate's in-progress work too (don't silently clobber it — see COORDINATION.md if parallel).
  "Nothing half-finished" is a valid, stated result.
- **▶ Recommended restart point** — THE single next action: the story ID + title, its `GoalRef`/AC
  location, its lane (+ worktree note if parallel per COORDINATION.md), and the one-line why. Frame it
  as ready to become one `/goal` (or a milestone-block goal, if that's the mode in play).
- **Blockers / decisions pending** — owner/external dependencies (keys, counsel, live creds) carried
  from the handoff that gate the recommended work.

## 5. Hand off to action
End by stating the recommended restart point plainly and **ask whether to proceed** (kick off the
`/goal`) or adjust — do not silently start building; grounding is the deliverable of `/ss`. If
`$ARGUMENTS` named a focus (an epic/story id or a theme), orient toward THAT instead: confirm its
`DependsOn` are `Done`, pull its AC, and recommend it as the restart point (or explain why it's blocked).

## Rules
- **Truth over narration.** The repo, ledger, git, and gates win over prose. Surface conflicts; never
  smooth them over. A suspected fake-green is a stop-the-line finding.
- **Read-only.** `/ss` orients; it does not commit, edit code, or flip ledger Status. If it finds a
  Status drift worth fixing, it *recommends* the fix — the ensuing `/goal`/`/tt` does it.
- **Honor the frozen decisions** — whatever ADRs/decisions CLAUDE.md marks settled are settled; never
  reopen them during orientation.
- **Don't fabricate** progress, dates, a next step, or a clean bill of health you didn't verify.
- **Adapt to the repo.** Use the artifacts that exist; if there's no ledger/backlog, orient from the
  handoff + PROGRESS + git and say the ledger-based frontier is N/A. Be concise — the brief exists so a
  human (or a future you) is fully oriented in one read.
