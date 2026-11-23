# CR-014: The corridor is part of the hall - one live 3D space from the film page to the seats

| | |
|---|---|
| **Raised** | 2026-11-23, by the owner, in a working session |
| **Status** | **Done** 2026-11-23: all six halls baked with their corridors and checked in a real browser (desktop, phone, cold, warm, slow, failed hall file); shipped on the owner's "keep going get it all live". |
| **Amends** | CR-011 F5/F6 and the 2026-11-23 corridor renders (the film page door), CR-004 (the seat page arrival), CR-005 (the landing's hall), the loading gate (`hall3d/readiness.ts`). |

## What the owner asked for (their words)

"it feels like the door and the hall are not connected the transition is very bad, i rather we redesign the hall itself
with a corridor and it loads up in here to make it as smooth as possible". On phones: "Live 3D everywhere".
And for all work: "I do not want to be your eyes, everything you build you will check it yourself" (CLAUDE.md, "You are
the eyes").

## What was wrong (from the owner's video, 2026-11-23)

From the press of the door: the swing played while the corridor was still growing (barely seen); at 1.4 s the page
changed while the fade was half done and the browser held that half-dark frame frozen for about 2.3 s; then an empty
seat page for about 0.7 s; the hall at about 4.6 s; then a 4 s walk-in from a side door that does not follow the
corridor's straight line. About 8.5 s from the press to choosing seats, more than half of it frozen or empty.

## The design

1. **Each hall's 3D model has its own corridor** (Blender, `claude_leash/Graphics/FrontRow/Logic/scripts/hall_build.py`),
   built onto the hall's ENTRY door and baked with the room in Cycles. It has the look of the
   2026-11-23 corridor render (`corridor_render.py`): carpet, fluted panels over a wood dado, sconces, downlights, LED
   coves and skirting light, backlit posters of the site's films, the "SCREEN n" sign (yellow) and ENTER (green) above
   the door. The corridor runs straight into the door, so walking forward goes through it into the hall, and the walk
   turns to the screen inside.
2. **The door leaf is a separate node** in the GLB, named `corr_leaf`, with its origin on the hinge line, so the site
   swings it by rotating that node about the vertical axis. It is baked like the room (its light at rest is close
   enough when it swings).
3. **hallN.json gains** (three.js coordinates, as the rest of the file):
   ```json
   "corridor": {
     "eye": [x, y, z], "look": [x, y, z],          // where the film page's camera stands, looking at the door
     "door": { "node": "corr_leaf", "ajar": 10, "peek": 22, "wide": 92, "sign": 1 }  // degrees; sign: +1/-1 = which way opens it into the hall
   },
   "enter": [ {"eye": [...], "look": [...]}, ... ]   // the camera path: corridor eye -> through the doorway -> into the hall
                                                     // -> the all-seats view (it ends where "intro" ends)
   ```
   `intro` stays as it is.
4. **The site shows one live 3D hall that outlives the page change.** The film page's hero shows the chosen show's hall
   from `corridor.eye`, the door ajar. Hover or focus opens it to `peek`. Pressing the door or Book: the door swings
   to `wide` while the camera follows `enter` in one move; the film page's other parts slide away. When the camera
   lands, the URL becomes the seat page and the seat panel slides in over the SAME scene: the 3D canvas is not
   unmounted, so nothing reloads, fades or freezes. Back from the seat page returns to the film page and the corridor
   view.
5. **Loading.** The chosen show's hall loads as soon as the film page opens (`hall3d/preload.ts`). Until the whole hall
   is ready (`hall3d/readiness.ts`), the corridor render (`/art/corridor/screen<n>.webp`) stands in the hero at the
   same view. When the hall is ready, the live view replaces it with a short crossfade and no jump. Nothing moves
   before everything has loaded. Every wait has an exit: after the cap, the picture stays and the door goes to the
   seat page the old way.
6. **Phones:** the same live 3D (owner's choice), with a cheaper pixel ratio.

## Checks (Claude's own, per CLAUDE.md)

- Video of film page → press → seat page, cold and warm, at 1440 x 900 and 390 x 844, read as frames.
- No frame frozen, blank or half drawn, and no pop-in. Time from the press to the seat view stated.
- The slow path (throttled `/halls/*`) and a failed hall (404) seen working.
- `check_halls.py` and `check_sightlines.py` pass for all six halls; seat ids and positions unchanged.

## Results (2026-11-23, Claude's own runs of `e2e/walk_cr014.mjs`, `HALL=1..6`)

- All six halls: press to seat page 3.70-3.74 s, cold and warm; the same canvas from the film page to the seats and
  back (never remounted); no frame gap over 150 ms after the press. Corridor live 4.2-4.8 s after a cold open, 0.01 s warm.
- Phone (390 x 844, hall 6): the same times, no sideways scroll on either page.
- Slow (`/halls/*` +4 s): the press waits as `queued`, the picture stays still, the walk starts once the hall is ready.
- Failed hall file (404): the picture stays (`fallback`) and the door reaches the seat page in 0.11 s.
- Seat ids and positions unchanged in every hall; every seat has a light probe; `corridor` and 6 `enter` poses present.
- Fixed with it: the hall page's view buttons sat under the phone header (the header wraps to 2-3 rows); `--fr-head`
  now follows the header's real height. The console 404 was `/favicon.ico`; the site now has a brass-lamp favicon.
