# CR-001 — Six distinct halls, four films, and a 3D view of the hall you booked

| | |
|---|---|
| **Raised** | 2026-11-06, by the owner (Aniruddha), in a working session |
| **Status** | Part A **accepted by the owner** (it changes `ASSUMED` values only). Part B **APPROVED by the client 2026-11-06**, with its dependencies: `FR-ADR-074`. |
| **Wireframes** | <https://claude.ai/artifact/RtysgcqRtqo4RhBoJbRurZ> (private to the owner until shared) |
| **Inspiration** | A 3D cinema-booking demo seen in a short video. **The idea is borrowed, not the design**: no layout, branding, colours or assets are copied. FrontRow keeps its own "half-light" system (`docs/05 B DesignSystem`). |

---

## Part A — Programming and halls (owner decision, inside existing rulings)

### A.1 Why the owner can decide this alone

Both numbers this changes are `ASSUMED`, not `RULED`:

- `OPEN-SCALE-02` (hall sizes): the client said *"pick random"* (`SRC-003`).
- The demo programme (eight films rotating over every screen) is a seed choice in `scripts/seed.py`, not a ruling.

The client's ruling that stays fixed is `OPEN-SCOPE-01`: **one theatre with six cinema halls**.

### A.2 Four films on six screens

Every film plays in its **own** screen(s). A film never moves between halls from one day to the next.

| Film | Screens | Why |
|---|---|---|
| Film 1 (the biggest release) | **Screen 6** (220) and **Screen 5** (200) | the two largest halls |
| Film 2 | **Screen 4** (180) and **Screen 3** (150) | the next two |
| Film 3 | **Screen 2** (120) | |
| Film 4 | **Screen 1** (90) | |

That gives 4 different films on 6 screens, with 2 films each showing on two screens.

**Times.**
- Each screen keeps the four daily slots the seed uses today: 11:00, 14:30, 18:00 and 21:30.
- **Proposed:** the second screen of a two-screen film starts **105 minutes later** (12:45, 16:15, 19:45, 23:15), so customers get eight start times for that film instead of four identical pairs.
- If the owner prefers the pairs to run side by side, drop the offset.

### A.3 Six halls, six different seating plans

The hall sizes stay exactly as `SRC-003 OPEN-SCALE-02` records them. **The shapes are new**: each hall has its own layout instead of a plain rectangle.

| Screen | Seats | Rows | Shape | Seats per row, front (A) to back |
|---|---|---|---|---|
| 1 · Studio | 90 | 9 | One straight block, no centre aisle; side aisles only | 10 × 9 |
| 2 · Centre aisle | 120 | 10 | Two blocks split by a centre aisle | 6 \| 6 × 10 |
| 3 · Twin aisle | 150 | 10 | A wide centre block between two side blocks | 4 \| 7 \| 4 × 10 |
| 4 · Fan | 180 | 12 | Rows widen towards the back, with a centre aisle | 10, 11, 12, 13, 14, 15, 15, 16, 17, 18, 19, 20 |
| 5 · Stadium | 200 | 10 | Two blocks with a walkway (cross-aisle) between rows D and E: four flat rows at the front, six raked rows behind | 5 \| 10 \| 5 × 10 |
| 6 · Grand | 220 | 11 | Short front rows, a wide middle, and a recliner back row | A–B: 4 \| 8 \| 4 · C–J: 4 \| 14 \| 4 · K: 12 recliners |

The counts are checked: 90, 120, 150, 180, 200 and 220.

**Seat categories** keep the seed's existing rule, `bands(rows)`: Standard is the front ⌈rows × 0.5⌉ rows, Premium the next ⌈rows × 0.3⌉, and Recliner the rest. Category is still shown as a band with a dashed rule, never as a colour.

**How the shapes are stored.** No schema change is needed. Every seat already has `grid_row` and `grid_col`, and the seat-map API already sends them (`seatmap.py`, `model.ts`).
- An aisle is an empty grid column.
- The Stadium walkway is an empty grid row: `bands()` already treats a row with no seat as a "void" row inside a band.
- In Screen 6, each recliner takes **two grid columns** so it draws wider.
- Shorter rows are centred on the hall's widest row.

**What stays excluded.** `P-SCP-13` still holds, so none of these layouts adds paired seats, accessible-seat marking or a gap rule. The shapes are only geometry.

### A.4 Impact

| Where | Change |
|---|---|
| `scripts/seed.py` | `LAYOUT` becomes a per-row block list (the table above). `insert_halls` places seats on `grid_row`/`grid_col` with aisles and voids. `FILMS = 4`. `schedule()` maps each screen to its fixed film, plus the optional offset. |
| Seed tests / scope tests | Update the counts that assume 8 films and 720 rectangular-hall showtimes. The showtime total stays 6 screens × 4 slots × 30 days = 720. |
| Seat map (2D) | Must render the voids and aisles from `gr`/`gc`. The data path exists; verify it with a render test per hall shape. |
| Seat-freeze notice | The seed's NOTICE already warns that the first showtime write freezes every hall's layout. **Re-seed Neon after this change, not before.** |
| Ledger | No new story for the 2D part. It lands as a seed change plus tests in the next build round. |

---

## Part B — The 3D hall and "view from your seat" (approved 2026-11-06, FR-ADR-074)

### B.1 What it is

- The seat page (`/showtimes/{id}`) gains a live 3D model of **the hall that showtime plays in**, built from that hall's own seat map. It is not a stock room.
- Picking a different film or showtime can therefore put the customer in a different-shaped room.
- There are three camera views:
  - **Hall overview**
  - **View from my seat**: the camera moves to the chosen seat's real position and distance
  - **From the screen**
- Seats chosen in 3D and on the 2D map stay in sync.

### B.2 Per-hall rules

- Each hall's room is generated from its `gr`/`gc` grid: the screen width, the rake (flat for Screen 5's front four rows), the aisles and the walkway.
- The "view from your seat" stills on the movie, checkout and ticket pages are rendered from **that** hall.
- The admin halls screen previews the same 3D room while a layout is edited.
- **Each seat category has its own 3D seat model**, matching the bands in A.3:
  - **Standard** (front rows): a classic fold-up cinema seat.
  - **Premium** (middle rows): a wider, more padded seat with a headrest.
  - **Recliner** (back rows): a full recliner with a footrest.
- Category is still never shown by colour alone (`P-BRW-16`). The seat shape is extra information, not the only signal.

### B.3 What it does not change

- **It changes presentation only.** The hold, the seat lock, payment and every invariant stay exactly as specified.
- The 2D map stays complete and always available. It is the version used on phones, by keyboard and screen-reader users, and on browsers without WebGL.

### B.4 What needs approval before it is built

1. A **scope amendment** from the client: the PRD has no 3D feature, and the backlog's acceptance criteria limit scope.
2. **Permission for new dependencies** under `SRC-002 §13.1`: `three`, `@react-three/fiber`, `@react-three/drei`, `@react-three/postprocessing`, and two web fonts (Inter Tight, JetBrains Mono).
3. An **ADR** recording the 3D layer as presentation only.
4. **Runway assets** for the demo films: posters, on-screen key-art, short motion loops and texture sources. The demo films are invented, so they need no rights. Every prompt and file is logged under `claude_leash/Graphics/FrontRow/`.

### B.5 Quality bar

- **Speed:** 60 fps on a mid laptop, with a 30 fps floor on a mid phone.
- **Download size:** the 3D files stay under 3 MB gzipped, and the 3D code loads only on the seat page.
- **Camera:** moves take 900 ms (`--fr-motion-change`). With `prefers-reduced-motion` set, the view cuts instead of gliding.
- **Fallback:** without WebGL, or on a weak GPU, the 2D map loads on its own and nothing is lost.
- **Hosting:** stays on Render's free plan. The 3D files are static, so there are no new services and no extra Neon queries.
