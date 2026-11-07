// Browse screens (Phase 3). src/router.tsx collects this table. CR-004: `/` is the landing (seated in a hall),
// `/browse` the shows rail over the hall, and the card listing with its filters moved to `/films`.
import type { AppRoute } from "../../router";
import { Landing } from "../landing/Landing";
import { SeatMapScreen } from "../seatmap/SeatMapScreen";
import { BrowseScreen } from "./BrowseScreen";
import { ListingScreen } from "./ListingScreen";
import { MovieScreen } from "./MovieScreen";

export const browseRoutes: AppRoute[] = [
  { path: "/", render: () => <Landing /> },
  { path: "/browse", render: () => <BrowseScreen /> },
  { path: "/films", render: () => <ListingScreen /> },
  { path: "/movies/:movieId", render: (p) => <MovieScreen key={p.movieId} movieId={p.movieId} /> },
  { path: "/showtimes/:showtimeId", render: (p) => <SeatMapScreen key={p.showtimeId} showtimeId={p.showtimeId} /> },
];
