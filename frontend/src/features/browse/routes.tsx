// Browse screens (Phase 3). src/router.tsx collects this table. CR-004: `/` is the landing (seated in a hall),
// `/browse` the same page (CR-005 folded Browse into it), and the card listing with its filters moved to `/films`.
import type { AppRoute } from "../../router";
import { Landing } from "../landing/Landing";
import { SeatMapScreen } from "../seatmap/SeatMapScreen";
import { ListingScreen } from "./ListingScreen";
import { MovieScreen } from "./MovieScreen";

export const browseRoutes: AppRoute[] = [
  { path: "/", render: () => <Landing /> },
  { path: "/browse", render: () => <Landing /> }, // CR-005: Browse folded into the landing; old links still land
  { path: "/films", render: () => <ListingScreen /> },
  { path: "/movies/:movieId", render: (p) => <MovieScreen key={p.movieId} movieId={p.movieId} /> },
  { path: "/showtimes/:showtimeId", render: (p) => <SeatMapScreen key={p.showtimeId} showtimeId={p.showtimeId} /> },
];
