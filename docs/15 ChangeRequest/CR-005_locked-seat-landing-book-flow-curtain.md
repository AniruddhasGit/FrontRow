# CR-005: Locked-seat landing, one-flow booking, and the stage curtain

| | |
|---|---|
| **Raised** | 2026-11-07, by the owner, in a working session |
| **Status** | **Accepted by the owner** 2026-11-07 (their own request, quoted below). Presentation and routes only. The seat rules, holds, prices, sign-in and booking are unchanged. |
| **Supersedes** | CR-004's landing (its hall switcher and "See every seat") and its `/browse` page (`/browse` now shows the landing). |

## What the owner asked for (their words)

- "when they land on our website we will have the seated view which is locked i do not want them to be able to change the seats only the movies will change as they scroll through the movies and those movies show up on their hall screen"
- "on the left side nav bar we will have the movies list ... another button which says book tickets which when clicked will take us to the login if already not loggedin, and if already logged in then it will take us to the entrance where we will see the movie screen and it will pan to all seats ... they will stay on the screen and then fly across ... that way it feels like one flow. and the nav bar gets smoothly collapsed"
- "i need a theatre curtain ... for transitions between screen ... when i click on show all shows then i want the hall look to be gone and the nav bar expands to the whole page ... the curtain drops on the hall part ... and collapses to the left hand side pulling along the nav bar border ... and then shows list pops up"
- "the curtain element you made looks very cheap and as it moves to left and right it should have like real physics ... make it real with texture and all."
- "the curtain should open from left to right side while pulling on the nav bar and the movies which are already there will also move while new ones will fade into existence, also the curtain should not wave so much make it a bit sturdy ... minimal wavyness and it looks like it is glitching aswell"

## What was built

| Piece | Behaviour |
|---|---|
| **Landing, `/` and `/browse`** | <ul><li>The visitor sits in the default seat (the back row's seat 1) and the seat is locked: no seat clicks, no hover, no dragging.</li><li>A rail on the left lists the films. It scrolls and snaps, and the film centred in it plays on the screen (on phones the rail runs sideways under the hall).</li><li>The hall is the one where that film's next show runs, so you book in the room you are sitting in.</li><li>Under the screen are the day's times and **Book tickets**.</li></ul> |
| **Book tickets, signed out** | Goes to sign-in, which returns to the seat page. The seat page then plays its own arrival (seated facing the film, then the turn onto the seats). |
| **Book tickets, signed in** | One flow: <ol><li>The rail folds away (`grid-template-columns`, 700 ms).</li><li>The camera turns from the seat, across the room past the far wall, onto the all-seats view (4.2 s).</li><li>The seat page takes over on that same picture. The landing sets `fr.flown`, so the seat page skips its own arrival. The router (`navigate(to, hold)`) keeps the old frame on screen through a View Transition until the seat page's hall has drawn (`hallReady.ts`, 3 s cap).</li></ol> |
| **All films** | <ol><li>The curtain drops over the hall.</li><li>It opens from left to right, gathering to the right edge, and pulls the rail's edge across with it. The rail's ground and border follow the cloth's own reported progress (`--fr-curtain-open`) until the rail fills the page.</li><li>The films already in the rail glide to their places in the `/films` grid: a View Transition matched by `view-transition-name: film-<id>`, 650 ms. Everything else fades in.</li></ol> |
| **The curtain** (`features/curtain/`) | Reusable, with three states: `up`, `down`, `drawn`. Real cloth simulated on the GPU page (details below). Without WebGL it falls back to a flat CSS drape. With reduced motion every move is instant. |
| **`/films`** | The SCR-BRW-01 listing restyled as a poster wall: tall posters, the title and details under each. |

## The curtain

- **Physics:** Verlet integration: 121 × 44 particles, gravity 10 units/s², damping 0.965 (heavy and sturdy, at the owner's request), 120 Hz steps, 12 solver passes.
  - **Pleats:** they are geometry. The top row is pinned along a rail in a smooth sine of depth 0.55 × the pleat width, one pleat every five particles, each pleat varied by a fixed scatter. Vertical links neither stretch nor buckle, so the velvet hangs straight. While the curtain hangs, the links across each pair of pleat faces hold both ways, so no two folds cross (crossed folds rendered as dark slits). Only while it is being drawn do they let the pleats bunch.
  - **Weighted drape:** each step, every particle eases 2 % toward the x of its own pin, so the sheet follows the rail as one piece instead of billowing.
  - **Drop:** the rail falls freely at gravity, then brakes at 0.7 g to the floor. The sheet is carried down by 90 % of the rail's own movement (positions moved, no speed added), so braking never piles cloth up under the valance. The remaining 10 % lags and settles over 450 ms.
  - **Gather:** the pins run to the RIGHT edge (to 3.5 % of the width) over 900 ms, with an ease-in-out, and the pleats deepen only ×2.2.
  - **Clock:** everything runs on the simulation's own clock (a slow device plays the same motion more slowly, never torn), and the cloth reports its own progress and its end to the page.
  - **Pre-warm:** the cloth is mounted, parked above the box and drawn once, while the landing is open, so the first drop starts on the click.
- **Look:** `MeshPhysicalMaterial` with `sheen` (three.js's velvet model), using the `--fr-velvet-*` design tokens and a woven normal map: ambientCG **Fabric084**, CC0, 512 px, at `public/art/velvet_normal.jpg`. The key light is warm and rakes in from high left so every fold reads; there is a cool fill and a footlight. The valance is a stiff boxed pelmet with scalloped swags and a gold cord. It rides the rail and lifts away on the gather.

## Unchanged, and still tested

- The 2D map, holds and booking are untouched.
- The demonstration line is still in the single footer on every route.
- The landing reads only the public read path, once per choice, and nothing polls.
- S-PAY-12 still holds: no `Math.random` in `frontend/src`. The pleat and dust scatter use a fixed hash.
- The design-system contrast check passes: the curtain's reds are decor tokens with reasons, in both themes, and in COMPONENTS.md §11b.

## Not done

- **Demo films:** still the owner's to choose.
- **Self-collision:** the cloth has none. Deep bunching can let two folds pass through each other for a frame. Nobody has seen it at this pace.
