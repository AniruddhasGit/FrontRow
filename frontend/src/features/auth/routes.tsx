// Account, checkout, booking and confirmation screens. src/router.tsx collects this table, so nobody edits the router to
// add a screen. [JUDGMENT CALL] The checkout, booking and ticket routes ride on this table because the router collects
// only this one and the admin one today; a later edit of src/router.tsx can give each feature its own table.
import type { AppRoute } from "../../router";
import { NotificationsScreen, ProfileScreen, RewardsScreen, WishlistScreen } from "../account/AccountScreens";
import { HelpScreen } from "../account/HelpScreen";
import { MyBookingsScreen } from "../account/MyBookingsScreen";
import { ResetConfirmScreen, ResetRequestScreen, tokenFrom } from "../account/ResetScreens";
import { CheckoutScreen } from "../booking/CheckoutScreen";
import { ConfirmationScreen } from "../ticket/ConfirmationScreen";
import { SignInScreen } from "./SignInScreen";

export const authRoutes: AppRoute[] = [
  { path: "/sign-in", render: () => <SignInScreen initial="sign-in" /> },
  { path: "/register", render: () => <SignInScreen initial="register" /> },
  { path: "/account/reset", render: () => <ResetRequestScreen /> },
  // The token is read from location.hash (the fragment), never sent to any server by the browser.
  { path: "/account/reset/confirm", render: () => <ResetConfirmScreen token={tokenFrom(window.location.hash)} /> },
  { path: "/showtimes/:showtimeId/checkout", render: (p) => <CheckoutScreen key={p.showtimeId} showtimeId={p.showtimeId} /> },
  { path: "/bookings", render: () => <MyBookingsScreen /> },
  // CR-008 T3-T8: the account sidebar's pages, and Help (open to everyone)
  { path: "/account/rewards", render: () => <RewardsScreen /> },
  { path: "/account/wishlist", render: () => <WishlistScreen /> },
  { path: "/account/notifications", render: () => <NotificationsScreen /> },
  { path: "/account/profile", render: () => <ProfileScreen /> },
  { path: "/help", render: () => <HelpScreen /> },
  { path: "/bookings/:reference", render: (p) => <ConfirmationScreen key={p.reference} reference={p.reference} /> },
];
