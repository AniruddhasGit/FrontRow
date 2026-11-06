# CR-003 — The approved hall plans (revision 5) and baked 3D halls

| | |
|---|---|
| **Raised** | 2026-11-06, by the owner, in a working session |
| **Status** | **Accepted by the owner** 2026-11-06. It changes `ASSUMED` values only (`OPEN-SCALE-02` hall shapes, `OPEN-SEAT-01` category placement) and the 3D presentation approved in CR-001 Part B. |
| **Supersedes** | CR-001 **A.3** (the hall shape table). CR-001 A.1, A.2 and Part B stand. |
| **Plans** | <https://claude.ai/artifact/AXvp8S9B47jRisgkfJ3viJ> (revision 5, private to the owner). The source of record is `claude_leash/Graphics/FrontRow/Logic/hall_plans/halls_rev5.json`. |
| **Demo** | <https://claude.ai/artifact/EKVipvhTaJzVPNsnCC79Xt>. The owner tried Hall 1 and said "i like it make it for the rest of the halls". |

## What the owner approved

1. **Hall shapes, revision 5.** The seat totals stay 90 / 120 / 150 / 180 / 200 / 220.
   - Rows, blocks and aisles follow the plans' "stairs first" geometry: constant 1.15 m aisles, straight stairs, and walls that follow the seating.
   - Hall 6 has a balcony (rows K–N) with its own entry and exit.
2. **Category by row, as drawn**, replacing the computed bands (P-XCT-30's `ceil(rows × 0.5)` / `ceil(rows × 0.3)`).
   - Every hall still has Standard nearest the screen and at least one Recliner row.
   - Hall 5 puts its Recliner row (E) on the rail behind the flat front section, as drawn.
3. **Baked 3D halls.** The 3D view (CR-001 Part B, `FR-ADR-074`) shows each hall's Blender-baked room:
   - `/halls/hallN.glb` for the room
   - `/halls/hallN.json` for seat positions and cameras
   - `/halls/hallN_intro.mp4`, an entrance clip ending on the live camera

   The seats remain live (state colour, hover price, click to choose and to see from). If the file and the API disagree on any seat, the procedural hall is drawn instead.

## The layouts (typed from the plans; the seed and the tests are each written from this table, never from each other)

Row: label, category (S/P/R), seat blocks between aisles. "—" is a walkway (no row letter).

| Hall | Rows |
|---|---|
| 1 Studio (90) | A[11] S · B–D[12] S · E–F[12] P · G[13] P · H[6] R |
| 2 Centre aisle (120) | A–C[5,5] S · — · D[6,6] S · E–K[6,6] P · L[3,3] R |
| 3 Twin aisle (150) | A[3,8,3] S · B[4,8,4] S · — · C–D[4,8,4] S · E–J[4,8,4] P · K[2,4,2] R |
| 4 Fan (180) | A[1,10,1] · B–C[2,10,2] · D–E[3,10,3] · F[4,10,4] S · — · G[4,10,4] P · H–J[5,10,5] P · K[5,10,6] P · L[3,5,3] R |
| 5 Stadium (200) | A–D[7,7] S · — · E[3,5,3] R · F–L[3,10,3] P · M[4,10,4] P · N[4,10,5] P |
| 6 Grand (220) | A–C[3,10,3] S · — · D–E[4,10,4] S · F–H[4,10,4] P · J[2,5,3] R · — · balcony K–N[4,10,4] P |

Seat numbers run left to right facing the screen across the whole row. Grid columns come from the plan's x positions on a 0.6 m grid: a Recliner is two columns, and an aisle about two.

## Consequences

- **The seed writes these layouts.** Running it still freezes the seat layout (P-ADM-14).
- **The live database (Neon) still holds the CR-001 layouts** until the owner decides to re-seed it. Re-seeding replaces every seeded seat and booking, so it is irreversible for that data and **reserved: not done by this CR.** Until then the live 3D view falls back to the procedural hall (the labels differ), which is the designed fallback.
- **Tests amended by this CR:**
  - `tests/seed/test_cr001_halls.py` is re-typed from the table above.
  - The S-XCT-44 band tests read row categories from the regenerated oracle.

  No test is skipped or deleted to reach green.
- **Asset weight:** about 4 MB per hall model and about 2 MB per clip, all static files.

## Mobile (owner, 2026-11-06: "make sure the whole website is mobile compatible")

- **The 3D hall now shows on phones too.** The old rule that it only appears at least 48rem wide is removed; WebGL is still required.
- **Holding a phone upright:** the live camera opens to a lens up to 95° tall, so the hall's width fits. The entrance clip plays whole, letterboxed.
- **Touch wording:** prompts say "Tap", not "Click".
- **The rest of the site** is audited at 390 px wide in a browser, and fixes are listed in the handoff.
