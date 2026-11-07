# CR-004: Seated landing, Browse rail, and full-screen hall pages

| | |
|---|---|
| **Raised** | 2026-11-07, by the owner, in a working session |
| **Status** | **Accepted by the owner** 2026-11-07 (their own request, quoted below). It changes presentation and routes only. The seat rules, holds, prices and booking are unchanged. |
| **Supersedes** | `FR-ADR-074` 5 ("3D only on the seat page"): the landing and Browse now load the 3D hall too. CR-003 item 3's `/halls/hallN_intro.mp4` (retired 2026-11-07, live camera instead). SCR-BRW-01's route `/` (the listing moves to `/films`). |

## What the owner asked for (their words)

- "a landing page ... to be like I'm already seated in a seat ... the landing page will have the options to view all the halls, and ... a button which says browse the shows"
- "when we browse the shows then we will automatically be taken to that hall view of that respective show ... a left hand side nav bar which allows me to go through different movies while the hall changes as the show and timings change"
- "when people go to book the seat they will be taken into the hall view while facing the screen with their show on the screen and then pan to the seats ... select their seat in 3D view or in 2D view, hover over seat will tell their price and availability"
- "I hate this boxy view i want to have a full screen filled view of the theatre with the nav bar can be on the right side of the screen. no empty space ... realign and respace all the pages"

## What was built

| Route | Screen |
|---|---|
| `/` | **Landing.** The visitor is already sitting in the middle of Hall 1, facing the screen with the first listed film on it. It has a "Browse the shows" button and a "See every hall" switcher for Halls 1 to 6. Dragging turns the view; clicking a seat sits there. |
| `/browse` | **Browse.** A left rail lists every film. The chosen film's showtimes for the day are shown, with "Next: <day>" when there are none. The rest of the window is the chosen show's hall, seen from a seat, with that film on the screen. Changing the film or the time changes the hall. When the show's seat map is loaded, hovering over a seat gives its price and its state. "Choose your seats" opens the seat page. |
| `/films` | The SCR-BRW-01 card listing with its filters, unchanged apart from its address. The rail links to it. |
| `/showtimes/:id` | **Seat page.** The hall fills the window on the left, and a panel on the right holds the heading, the 2D map, the legend and the summary. The visitor arrives seated in the front level's middle seat, facing their film. After about 1.4 s the camera rises and turns by the side wall onto the all-seats view (`hall.ts` `screenFirst`). The "2D map" button gives the 2D map the full width, and "Show the hall in 3D" brings the hall back. Hovering in 3D shows the price and state, as before. |

Every other page (sign-in, bookings, checkout, admin, dashboard) now uses the full width, with a gutter that grows with the window, instead of a centred box.

## Unchanged, and still tested

- The 2D map stays in the page whenever the 3D hall is shown. It is the accessible way to choose seats; the 3D canvas is `aria-hidden`.
- The demonstration line is in the single footer landmark on every route (S-SCP-12). On the hall pages it sits on the bottom edge of the window.
- No hold or booking can start from the landing or from Browse. A seat click there only moves the camera.
- The reads are the public ones the listing already made: `/api/movies`, `/api/showtimes`, and `/api/showtimes/:id/seatmap`, once per choice. Nothing polls.

## Not done

- **Demo films.** The owner will choose a few real films (title, poster, and a screen still at `/art/screen_<film id>.jpg`). Until then the screen shows the title card.
- **The landing's hall** is Hall 1 by default, not the hall of the next show. Change `Landing.tsx` if the owner wants that.
