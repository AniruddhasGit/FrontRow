# FR-ADR-074 — A 3D hall is a presentation layer over the seat map, and adds three.js and two web fonts

| | |
|---|---|
| Status | **APPROVED** — client ruling, 2026-11-06 (Aniruddha Jathar, in session; recorded in `docs/15 ChangeRequest/CR-001`) |
| Type | CLIENT_RULING (scope change + new dependencies, both reserved under `SRC-002 §13.1` / `CLAUDE.md` "Reserved") |
| Sources | CR-001 Part B; FR-ADR-044 (CSS Modules); FR-ADR-072 (tokens); SRC-003 OPEN-SEAT-01 (categories, ASSUMED) |

## Decision

1. The seat page (`/showtimes/{id}`) gets a live 3D model of the hall the showtime plays in. It is built from the
   seat-map response (`gr`/`gc`, categories, states) and offers three cameras: overview, view from my seat, and from
   the screen. Selection is shared with the 2D map.
2. **The 3D layer only presents.** Holds, the Redis lock, the database guard, payment, idempotency and every invariant
   are unchanged. The 3D layer calls the same API the 2D map calls, and holds nothing of its own.
3. **The 2D map stays complete and always available.** It is what phones, keyboards, screen readers and browsers
   without WebGL use. 3D failing or being absent loses nothing.
4. **New dependencies, approved:** `three`, `@react-three/fiber`, `@react-three/drei`, `@react-three/postprocessing`;
   and the web fonts Inter Tight + JetBrains Mono, self-hosted (no runtime call to a font CDN).
5. The 3D bundle is code-split and loads only on the seat page. The seat models are static `.glb` files, one per
   category. Third-party models are credited (CC BY) in `CREDITS.md`.

## Why

This is the client's own choice of product presentation, made after reviewing the wireframes. The 3D layer adds no
server, no query and no state, so it changes neither the memory budget nor the free-tier hosting.

## Reversal cost

Delete the 3D feature folder and the four packages; the 2D map is untouched by construction.
