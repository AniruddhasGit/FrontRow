# 07 Architecture — index

> **compressed per SRC-004 R-1.** `GOAL_09` ran as one pass of the compressed `GOAL_09`–`13` set the
> client chose on 2026-10-18. Review depth is lighter than the goal file asks for: one writer, one
> mechanical gate (`check_architecture.py`), no fresh zero-context reader round. **No green below
> was faked and no `OPEN` row was answered.** Where the documents needed an answer nobody has given,
> the row is named and the gap is left visible.

Two audiences, two folders. They say the same things at different depths; where they disagree,
`for_llm/` is the more precise and is the one to fix.

| Folder | Reader | What it is for |
|---|---|---|
| `for_llm/` | a code session starting cold | one read gives the module map, the request flows, the lock design, the queue, the failure behaviour |
| `for_humans/` | the client | what was decided, what is still owed by you, and what this design knowingly does not do |

| File | Carries |
|---|---|
| `for_llm/01_system_context.md` | actors, external systems, what does not exist, the invariants and where each is enforced |
| `for_llm/02_container.md` | processes, the `backend/app/{api,core,domain,models,workers,jobs}` module map, import rules, the queue port |
| `for_llm/03_concurrency_model.md` | **the most important file.** Redis hold + PostgreSQL guard, end to end |
| `for_llm/04_deployment.md` | process topology, ports, health wiring, **the 1 GB arithmetic** |
| `for_llm/05_surface_route_map.md` | all 58 endpoints, which router owns each, which dependency guards it |
| `for_llm/06_booking_sequence.md` | hold, confirm, receipt, resend, and the password reset under `SRC-004 R-3` |
| `for_llm/07_state_machines.md` | every stateful thing, its states, and who moves it |
| `for_llm/08_failure_modes.md` | SES first, then every dependency; customer / operator / data-at-risk per row |
| `for_humans/01_executive_overview.md` | the system in plain words |
| `for_humans/02_decisions_owed.md` | every Article X row still open and what it blocks; the questions this goal raised |
| `for_humans/03_the_deliberate_gaps.md` | the accepted weaknesses |
| `check_architecture.py` | the gate. `py "docs/07 Architecture/check_architecture.py"` |

## Two labels used throughout

- **AWS-behaviour tag.** Every sentence that says how something behaves *inside AWS* starts with an
  id like `[AWS-<file>-<nn>]` (for example AWS-04-03 in `for_llm/04_deployment.md`) and ends with the reasoned-not-observed label. This session has never seen
  the application run in AWS (`CONSTITUTION.md` Art VIII.3), so every such sentence is reasoning.
  The gate counts ids against labels; the two numbers must match.
- **`[JUDGMENT CALL]`** — a non-reserved technical decision this goal made, with its alternative.
  Each is reversible and listed again in `for_humans/02_decisions_owed.md` so the client can reverse it.

## What this folder does not contain

No Terraform, no CloudFormation, no ECS task or service definition, no security group, no VPC or
subnet layout, no CI/CD (`SRC-002 §6.5`, `FR-ADR-004`). Where the application expects something of
infrastructure, the expectation is stated; the client builds it.
