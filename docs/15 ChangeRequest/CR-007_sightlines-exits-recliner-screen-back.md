# CR-007: Every seat sees the screen, doors in pairs, two-armed recliners, a true 2D screen, and a Back button

| | |
|---|---|
| **Raised** | 2026-11-22, by the owner, in a working session (screenshots of Screen 5 seat E11, a recliner, the 2D map) |
| **Status** | **Asked for by the owner** 2026-11-22 (their words, below). Built and checked locally; not pushed or deployed. |
| **Amends** | CR-003 (the rev 5 hall shells: straight walls, Hall 6 balcony +0.3 m, one more rear exit in Halls 3-6). S-BRW-17: the screen bar keeps its top and height across the seat-map response; its x and width now follow the seat block. SCR-XCT-05: the header gains a Back control. |

## What the owner asked for (their words)

- "Screen 5 Row E seat 11 looks this view. it is blocked. dont make the theatre shape so weird." / "check for similar errors in all theatre halls."
- "all the recliner seats are missing the side parts on their right side. while they still have the left part"
- "some theatre halls have entry and no exits, some have exits and no entry, they must have equal entry and exits sign"
- "In this 2 D map the screen is static and not showing the true relative position of the screen with the chairs."
- "no matter where i click and go inside into I need there to be proper button to move further or come back to the previous screens so i need to have a dedicated back button."

## What was built

| Piece | Cause | Change |
|---|---|---|
| **Straight side walls** (all halls) | The wall stepped out at each wider row; the step's face stood between the end seats of the wider row and the screen (Hall 5 E1/E11 saw no screen at all). | `hall_build.py` `wall_half()` is one width per hall: the widest aisle edge. The front wall spans it. |
| **Hall 6 balcony +0.3 m** | Found by the new sightline check: row J (stalls, under the balcony) lost the top third of the screen behind the balcony front. | `halls_rev5.json`: balcony floor, rows, walkway, doors and balcony speakers raised 0.3 m (underside 4.45 m). |
| **Doors in pairs** | Halls 3, 4, 5 and the Hall 6 stalls had two entries and one exit. | A mirrored rear exit on the other wall. Every level now has as many EXIT signs as ENTRY signs. |
| **Two-armed recliner** | `prep_seats.py` cut the source two-seat sofa at x 0.80-9.30: the left arm and seat 1, never a right arm. | Cut at seat 1's centre (x 6.315) and mirrored. Same 1.11 m overall: `SEAT_FIT` R x 1.30 → 1.0044; the site's `BAKED_SCALE` recliner (1.946, 1.677, 1.676) → (1.946, 2.17, 2.17). |
| **2D screen** | The bar and label sat outside the map's sideways scroll, at a fixed 60 % of the panel. | Inside the scroll box, on the seat grid's own columns (`computeHall`'s seat block, recliners two columns), so it is centred where the 3D hall centres it and scrolls with the seats. |
| **Back** | No way back but the browser's. | `← Back` first in the header on every screen but home. It undoes the last in-app step (`history.state.frDepth`, written by `navigate`); on a deep link it goes up to the nearest registered parent (`nav.ts` `parentOf`), else home. The five `replaceState` calls keep the state so the count survives filters. "Move further" stays each screen's own primary action. |

## Checks

- **Sightlines** (`claude_leash/Graphics/FrontRow/Logic/scripts/check_sightlines.py`): a ray from every seat's eye to 9 screen points, against the architecture.
  - **Before:** Hall 5 2 seats blocked (E1, E11: 9/9 points); Hall 6 10 seats (J1-J10: 3/9).
  - **After:** 0 seats blocked in all six halls (960 seats).
- Unit tests: `nav.test.mjs` (new `parentOf` case), seatmap and hall3d suites, `tsc -b`.
- e2e S-BRW-17 assertion changed to the bar's top and height.
