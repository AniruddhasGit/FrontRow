# CR-010: Ray-traced lighting for the halls (seats, reflections, a sharper bake)

| | |
|---|---|
| **Raised** | 2026-11-22, by the owner, in a working session |
| **Status** | **Asked for by the owner** 2026-11-22. Not started: ships after the CR-007/CR-008 deploy. Prototype on Screen 5 first, for the owner's before/after. |
| **Amends** | CR-003 (the baked hall). |

## What the owner asked for (their words)

- "the shading in the entire theatre looks very fake, can you run ray tracing in blender to get real lights? that'll be great."

## Why it looks fake (found 2026-11-22)

- The room shell is already ray traced (Cycles, baked), but at 2048 px and 96 samples, and diffuse only: no gloss.
- The seats are most of the picture and are NOT ray traced: they are live instanced models (their colour shows sold/held/yours), lit in `HallScene.tsx` by two point lights, an ambient and a hemisphere light. No shadows, no bounce, no occlusion between rows.

## The list, and what marks each task done

| # | Task | Done when |
|---|---|---|
| L1 | **Cycles light probes for the seats.** Blender renders small 360° irradiance captures on a grid over the seating area of each hall (seats in place), reduced to spherical harmonics and stored in `hallN.json`; the browser lights each seat instance from its nearest probes (per-instance SH in the seat shader) instead of the point lights. | Before/after browser screenshots at the same cameras for all six halls show real falloff and row-to-row occlusion; ≥ 30 fps at a 390×844 viewport on the dev machine's integrated-GPU profile. |
| L2 | **Reflections.** One Cycles equirect HDR per hall from mid-hall, used as the seats' and brass's environment (PMREM). | A close-up shows brass and leather reflecting the hall's lights. |
| L3 | **Sharper bake.** Floor and walls at 4096 px, 256 samples. | Side-by-side crops of a wall and the floor show a sharper, cleaner surface; each hall GLB grows by ≤ 3 MB. |
| L4 | **Records.** | Graphics library (`claude_leash/Graphics/FrontRow/Logic/LOGIC.md`, scripts, before/after in References) updated; `check_sightlines.py` and `check_halls.py` still pass; seat positions unchanged. |

## L1-L4: what was built (2026-11-23)

Built for all six halls; the Screen 5 approval step was waived by the owner (asleep, wants it by morning). Values and
maths: `claude_leash/Graphics/FrontRow/Logic/LOGIC.md`, section "ray-traced light for the seats" (CR-010).

| # | Built | Check |
|---|---|---|
| L1 | `hall_probes.py`: per seat, two Cycles 64 × 32 equirect probes (40 % and 100 % of the seat's height, the seat itself hidden, every other seat in place), 1024 spp, reduced to L2 spherical harmonics (cosine-convolved, ÷ π) in `hallN.json` `seats[i].sh`. Browser (`seatLight.ts`, `HallScene.tsx`): a per-instance float texture read by `gl_InstanceID`; the seat and frame shaders take their diffuse light from the seat's own probes (blended by height), then the bake's AgX +0.4 × 2.2 curve, then the screen glow at half strength. No point / ambient / hemisphere lights in a probed hall; older files and the procedural hall keep the old lights. The seat back shell is leather (as in the Blender halls), so seat backs no longer read black. | Before/after for all six halls: `claude_leash/Graphics/FrontRow/References/screenshots_2026-11-22/lighting/cmp_hall1.png` … `cmp_hall6.png` (all-seats on top, seat view below, before left). Falloff from the screen, darker rows behind raised backs, door-sign spill, lit seat backs. Frame rate at 390 × 844: about 93 fps, p95 11.4 ms (GTX 1650 via ANGLE; no integrated-GPU machine available). |
| L2 | One 512 × 256 Cycles panorama per hall from mid-hall, `public/halls/hallN_env.hdr` (RGBE, 512 KB), PMREM'd with three's `HDRLoader`, as the seats' and frames' `envMap` (intensity 0.7); leather gets a thin clear coat. | `lighting/after/hall5_seat_lookdown.png`: the coat on the recliner backs catches the downlights. Subtle by design. |
| L3 | Floor and wall atlases 4096 px at 256 spp (room and speaker atlases 1024). Bake 763-1126 s per hall. | GLB growth +1.04 to +1.27 MB per hall (limit 3 MB). |
| L4 | Graphics library: LOGIC.md section, CHECKLIST additions, README log, scripts (`hall_probes.py`, `render_truth.py`, `run_lit_halls.sh`, `lighting_shots.js`), code snapshots, before/after images, the new GLB / json / hdr in `Elements/baked_halls/`. | `check_sightlines.py` 0 blocked in all six; `check_halls.py` PASS in all six; every seat id and position unchanged (≤ 1 mm). Frontend: `npx tsc -b` clean, 201/201 node tests (4 new in `seatLight.test.mjs`). |

Deploy note: the site must serve `/halls/hallN_env.hdr` as a static file (any content type works; a missing file only
drops the reflections).
