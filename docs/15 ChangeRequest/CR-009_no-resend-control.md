# CR-009: No "Send the receipt again" button; tickets live under My bookings

| | |
|---|---|
| **Raised** | 2026-11-22, by the owner, in a working session |
| **Status** | **Asked for by the owner** 2026-11-22. Built and checked locally (frontend 174/174, tsc clean). |
| **Amends** | SCR-TKT-01: the resend control and its polite status line are withdrawn from the booking page; focus order is heading → reference → copy control → facts. `FR-ADR-048`'s resend control is withdrawn from the UI by the owner. |

## What the owner asked for (their words)

- "Don't need send the receipt button remove it the people should be able to login and then be able to see their previous history and current tickets."

## What was built

| Piece | Change |
|---|---|
| Booking page (`ticket/page.ts`, `ConfirmationScreen.tsx`) | The button, its note and its request are removed. **Copy reference** is the page's only button (a unit test checks it). |
| My bookings (`account/MyBookingsScreen.tsx`, `/bookings`) | Already lists **Upcoming** (current tickets) and **Past** (history), each row opening the ticket. An empty Past now says "No past bookings yet." instead of showing nothing. |
| Styles (`styles/buttons.css`) | The resend button's rule is removed. |
| e2e (`checks/pay_ticket_account.test.mjs`) | Checks the button is absent instead of pressing it. |

## Not changed (kept on purpose)

- **The API endpoint** `POST /api/bookings/by-reference/{reference}/resend-receipt` (EP-TKT-02) and its backend tests stay: nothing in the UI calls it now, and removing it is a separate decision for the owner. The first receipt email is still sent after payment.
- **OPEN-EMAILFAIL-01** is unchanged: the reference is on screen and under My bookings whether or not the email arrives.
