// Browse screens (Phase 3). src/router.tsx collects this table; `/` is the listing.
import type { AppRoute } from "../../router";
import { SeatMapScreen } from "../seatmap/SeatMapScreen";
import { ListingScreen } from "./ListingScreen";
import { MovieScreen } from "./MovieScreen";

export const browseRoutes: AppRoute[] = [
  { path: "/", render: () => <ListingScreen /> },
  { path: "/movies/:movieId", render: (p) => <MovieScreen key={p.movieId} movieId={p.movieId} /> },
  { path: "/showtimes/:showtimeId", render: (p) => <SeatMapScreen key={p.showtimeId} showtimeId={p.showtimeId} /> },
];
