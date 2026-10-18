// Account, checkout, booking and confirmation screens. src/router.tsx collects this table, so nobody edits the router to
// add a screen. [JUDGMENT CALL] The checkout, booking and ticket routes ride on this table because the router collects
// only this one and the admin one today; a later edit of src/router.tsx can give each feature its own table.
import type { AppRoute } from "../../router";
import { MyBookingsScreen } from "../account/MyBookingsScreen";
import { CheckoutScreen } from "../booking/CheckoutScreen";
import { ConfirmationScreen } from "../ticket/ConfirmationScreen";
import { SignInScreen } from "./SignInScreen";

export const authRoutes: AppRoute[] = [
  { path: "/sign-in", render: () => <SignInScreen initial="sign-in" /> },
  { path: "/register", render: () => <SignInScreen initial="register" /> },
  { path: "/showtimes/:showtimeId/checkout", render: (p) => <CheckoutScreen key={p.showtimeId} showtimeId={p.showtimeId} /> },
  { path: "/bookings", render: () => <MyBookingsScreen /> },
  { path: "/bookings/:reference", render: (p) => <ConfirmationScreen key={p.reference} reference={p.reference} /> },
];
