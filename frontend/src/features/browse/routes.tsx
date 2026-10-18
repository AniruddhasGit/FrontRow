// Browse screens - owned by the browse lane (Phase 3). src/router.tsx collects feature route tables; this one
// still has to be added there (and `/` handed to ListingScreen in App.tsx) by the owner of those two files.
import type { AppRoute } from "../../router";
import { SeatMapScreen } from "../seatmap/SeatMapScreen";
import { ListingScreen } from "./ListingScreen";
import { MovieScreen } from "./MovieScreen";

export const browseRoutes: AppRoute[] = [
  { path: "/", render: () => <ListingScreen /> },
  { path: "/movies/:movieId", render: (p) => <MovieScreen key={p.movieId} movieId={p.movieId} /> },
  { path: "/showtimes/:showtimeId", render: (p) => <SeatMapScreen key={p.showtimeId} showtimeId={p.showtimeId} /> },
];
