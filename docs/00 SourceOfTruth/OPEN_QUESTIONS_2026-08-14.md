# Open questions — the answer sheet

```
Status ........ NOT FROZEN. This is a working file. Once you have answered it, your answers
                are filed verbatim as SRC-003, hashed, and this file stops being authoritative.
Rows .......... 40. Thirty are your own questions from SRC-001 §10. Ten were raised while
                drafting CONSTITUTION.md.
Blocks ........ everything. GOAL_02 onward cannot start until these are ruled.
```

---

## How to use this file

Write your answer on the `Your answer:` line under each question. You do not have to be formal —
"3 cinemas, 5 screens each, biggest is 220 seats" is a perfect answer.

**Four things you can say, and what each means:**

| You say | What happens |
|---|---|
| a real answer | recorded as `RULED`. It binds, and everything downstream cites it. |
| **"you pick"** | I choose, and it is recorded as `ASSUMED` — not `RULED`. It never hardens into a rule, and I will flag it every time it matters. Available on most rows. |
| **"don't know yet"** | recorded as `DECLINED`, with the working default written down as `ASSUMED`. Same effect as "you pick" but honest about why. |
| **"not in v1"** | recorded as a scope decision. Cleanest answer for anything you do not need yet. |

**"You pick" is not available on rows marked `RESERVED`.** Those are money, legal, and one-way
doors — decisions that cost real money, create a legal obligation, or cannot be undone once
bookings exist. On those I will keep asking rather than guess. There are 11 of them and they are
labelled.

**You can answer in any order and stop whenever you want.** Part 1 unblocks the most. If you only
have twenty minutes, do Part 1 and Part 4.

---

# Part 1 — The eight that block everything

These stop the next goal from starting at all. Six of them exist because your two documents
contradict each other, and I am not allowed to pick a winner.

---

### `OPEN-NAME-01` — who signs off on this project? · **RESERVED (governance)**

**Question.** What is your full name, for the ratification block at the bottom of
`CONSTITUTION.md`? And is there a backup person who can make decisions if you are unavailable?
"No backup — accepted" is a perfectly valid written answer.

**Why it matters.** Until a named human signs, the Constitution is UNADOPTED. Every decision record
filed before that point carries a caveat saying it was recorded while nothing governed the project.
That caveat does not go away retroactively.

**Blocks if unanswered.** Nothing technically. But every ADR filed from now on inherits the caveat,
and the longer it goes the more records carry it.

**My recommendation.** None offered — I cannot name you.

**Your answer:**
>Aniruddha Jathar is my name and i will always be the one building 


---

### `OPEN-LOCALE-01` — which country, city, and currency? · **RESERVED (money)**

**Question.** Where does this launch, and what currency do customers pay in?

**Why it matters.** This is the single most expensive question in the file, and it is not a display
setting. Money is stored as a whole number of the smallest unit — 100 for one rupee, 100 for one
dollar, but **1** for one yen, because yen has no subunit. Pick the wrong ratio and every historical
booking silently means something different. Since `SRC-001 §7.6` says booking records are permanent
and auditable, there is no fixing it later.

It also answers `OPEN-TMDB-01`, because TMDB's "now playing" list is region-specific, and it sets the
timezone that decides when a showtime actually is.

**Blocks if unanswered.** The data model (`GOAL_08`). I cannot write a money column without it.

**My recommendation.** None offered — this is your market, and it is money.

**Your answer:**
>India launched currency is rupees

---

### `OPEN-ROLE-01` — how many kinds of user are there? · source conflict

**Question.** Your two documents disagree. `CLIENT_ASK.md §4` lists **five**: guest visitor,
registered customer, cinema staff (scans tickets at the door), cinema manager (creates showtimes,
sets prices, sees their own cinema's numbers), and system administrator. `CLAUDE_CODE_BRIEF.md §3`
mentions only **"admins"**. Which is right for v1?

**Why it matters.** Roles are cheap to add to the database now and expensive later. If I build two
roles and you later want five, that is a rewrite of every permission check. If I build five and you
only ever use two, the cost is a few unused rows.

The bigger question underneath: **is staff ticket-scanning at the door in v1, or not?** That is a
whole surface — a scanner screen, a validation endpoint, a used-ticket state.

**Blocks if unanswered.** The BRD, the PRD, and the data model.

**My recommendation.** Model all five in the database from day one, but only build the screens for
the roles a phase actually needs. Expanding a role set later is a rewrite; collapsing one is a
migration. Say "yes, all five in the schema" and I will build interfaces only as phases require.

**Your answer:**
>no make it simple i am learning devops no scanner and stuff at the entrance we will make a receipt after purchase which will have a unique ID to make the person enter the cenima hall.  the guest is someone who has no account can browse but will need to amkee a account if want to purchase a ticket. and a admin who has the whole access. do not make more personas. thats it. the admin can add movie names and pictures and other stuff which the people can view on the website. and also have a dealine of how long this will stay and other things that need to be done so that customer can see the movies on front end. only 1 admin persona. admin can do all the stuff the managers can do.

---

### `OPEN-SCOPE-01` — four things you asked for have no phase to be built in

**Question.** `CLIENT_ASK.md` requires four things that `CLAUDE_CODE_BRIEF.md §12`'s seven phases
never build:

1. **Staff validating tickets at the door** (`§5.5.3`)
2. **A manager seeing only their own cinema's numbers** (`§4.4`)
3. **A customer cancelling a booking** (`§5.4.3`)
4. **Management reporting** — occupancy and revenue per show, per day, per movie (`§5.5.2`)

You already said "build the seven phases, then extend". This asks you to make that concrete: do
those four become **Phase 8 and Phase 9**, specified now and built after Phase 7? Or is any of them
actually not needed?

**Why it matters.** An intention that is not written down is not a plan. If cancellation is coming,
the booking table needs a status column and a cancellation timestamp from the start — adding those
after real bookings exist is a migration on live data.

**Blocks if unanswered.** The Bible (`GOAL_07`) cannot place stories in phases.

**My recommendation.** Phase 8 = staff check-in and manager scoping. Phase 9 = cancellation and
reporting. Specified now, built after Phase 7. Cancellation and refunds are entangled with
`OPEN-CANCEL-01`, so it belongs last.

**Your answer:**
>different managers for different cinema hall. can see earnings movies for the day, month, week and cannot add the new movies,the theatre has 6 cinema halls. and there are 2 managers per cinema hall. and other analytics things add more stuff that managers can do.

---

### `OPEN-QUEUE-01` — SQS or Redis for background jobs? · source conflict

**Question.** `CLAUDE_CODE_BRIEF.md §4.5` says the worker consumes **AWS SQS**. `§5.4.1` says
"prefer RQ or Dramatiq over Celery" — but RQ and Dramatiq are **Redis** job queues, not SQS
consumers. These are two different designs.

Second half of the question: if it is SQS, **what runs locally?** SQS is an AWS service; there is no
SQS in your `docker-compose.yml`. The options are a fake in-memory queue, or a container called
ElasticMQ that speaks the SQS protocol. ElasticMQ is a new dependency and `§13.1` says I must ask
before adding one.

**Why it matters.** SQS teaches you more — dead letter queues, visibility timeouts, message
retention, IAM permissions. That is the point of the project. Redis via RQ is simpler and uses a
service you already have.

**Blocks if unanswered.** Phase 5, and the architecture document before it.

**My recommendation.** SQS, because `§8.5.2` explicitly asks for dead letter queue handling and
that concept only exists in a real queue service. For local development, add ElasticMQ to
`docker-compose.yml` — it is about 100 MB and only runs on your laptop, never in AWS. **That is the
dependency I am asking permission for.**

**Your answer:**
>
yes allowed to have ELASTICmq.
---

### `OPEN-EMAIL-01` — how does the confirmation email actually get sent?

**Question.** Both documents require a confirmation email (`CLIENT_ASK.md §5.3.4`,
`CLAUDE_CODE_BRIEF.md §8.5.1`). **Nothing in your approved service list can send mail**, and `§4.12`
says I must not add a service that is not on the list. So as written, this requirement cannot be
built.

Three ways out:

- **AWS SES.** The obvious one. Free tier covers 3,000 message-charges a month. It starts in a
  "sandbox" where you can only email addresses you have verified, and getting out of the sandbox is
  a support request that takes a day or two. It is one more AWS service for you to configure, which
  fits the learning goal.
- **A third-party mail API** — Resend, Postmark, SendGrid. Simpler, free tiers exist, but it is an
  external vendor.
- **Not in v1.** The worker still runs and still generates the ticket QR code; the customer sees
  their booking reference on screen and in their account instead of in an inbox.

**Why it matters.** Phase 5 is the worker phase and email is half of what the worker does.

**Blocks if unanswered.** Phase 5.

**My recommendation.** SES. It is the only option that also teaches you something, and the sandbox
restriction is fine because you will be testing with your own address anyway. **Request it early** —
the sandbox exit is not instant.

**Your answer:**
>
yes will use this. 
---

### `OPEN-PROC-01` — four containers will not fit in 1 GB

**Question.** `§12` implies four processes running all the time: the API, the background worker,
a scheduler for the daily movie sync, and something serving the frontend. Your `t3.micro` has 1 GB
total, and before any of your containers start, roughly 300–400 MB is already gone to the operating
system, the Docker daemon, and the ECS agent. That leaves about 600–700 MB for four Python-ish
processes.

`§13.6` tells me to say this rather than quietly work around it. I am saying it.

**Why it matters.** If it does not fit, containers get killed by the kernel at the worst possible
moment, which on this product means during checkout.

**Blocks if unanswered.** The architecture document, and the Phase 1 container layout.

**My recommendation.** Drop from four processes to three:

- **Delete the scheduler container.** `§10.6.1` already requires an HTTP endpoint that triggers the
  sync, protected by an admin token. Point an EventBridge rule at it on a daily schedule. You get
  the same result, you learn EventBridge, and it costs zero memory.
- **Serve the frontend from a small nginx container** (about 15 MB) rather than a Node process.

That leaves the API (~200 MB), the worker (~150 MB), nginx (~15 MB), with real headroom. *(This is
reasoned from typical figures, not measured on your instance — I have never seen this run in AWS.)*

**Your answer:**
> sure.                          

---

### `OPEN-PAY-02` — simulated payment for v1? · **RESERVED (money)**

**Question.** You already said yes on 2026-08-14. This row exists so the answer is on the record in
a file rather than in a conversation. Confirm: **v1 uses a simulated payment step** — a fake
provider with real states (pending → authorized → captured, or failed) and a realistic delay,
built behind an interface so a real provider drops in later without changing the database.

**Why it matters.** It means you can build and test the entire booking flow without a payment
account, and the swap to a real provider later is one adapter, not a rewrite.

**One safety rule I am adding:** the simulated provider must be impossible to reach in a deployed
environment without a deliberate, visible flag. A fake payment that looks real to a customer is the
worst thing this could turn into.

**Your answer:**
>
yes this is fine.
---

# Part 2 — Scale

### `OPEN-SCALE-01` — how many cinemas and screens at launch?

**Question.** How many cinemas, and roughly how many screens in each?

**Why it matters.** It decides whether the seed data is 3 cinemas or 30, and whether a manager
picking "their cinema" is a dropdown or a search box.

**My recommendation.** If you are not sure, "you pick" is fine here and I will use 3 cinemas with
4–6 screens each, which is enough to make the manager-scoping test meaningful.

**Your answer:**
>
i answered this above.
---

### `OPEN-SCALE-02` — how many seats in the biggest screen?

**Question.** What is the largest screen, in number of seats?

**Why it matters.** Not cosmetic. Every customer looking at a seat map downloads the state of every
seat, every 3 seconds. A 120-seat screen and a 500-seat screen are different engineering problems —
different payload size, different cache entry size, and a different answer to whether the seat map
renders acceptably on a phone.

**My recommendation.** "You pick" is fine; I will design for 300 and test the layout at 500 so the
design does not fall over at the top end.

**Your answer:**
>
pick random.
---

### `OPEN-SCALE-03` — realistic peak, in customers booking at the same minute?

**Question.** On your busiest Friday evening, roughly how many people are trying to book in the same
minute?

**Why it matters.** It sets what the load test has to prove, and whether one `t3.micro` is honestly
enough. It does **not** change the correctness guarantee — 50 simultaneous requests for one seat
still produce exactly one winner regardless.

**My recommendation.** "You pick" is fine; I will size the load test at 50 concurrent bookers and
report where it starts to hurt.

**Your answer:**
>
you pick
---

# Part 3 — Seats and screens

### `OPEN-SEAT-01` — are there different seat categories?

**Question.** Do your screens have different classes of seat — recliner, premium, standard? If yes,
what are they called?

**Why it matters.** `CLIENT_ASK.md §5.2.3` says seats are priced differently, so the answer is
almost certainly yes. I need the actual names because they appear on screen, in the price breakdown,
and on the ticket. Making them up is inventing your product's content, which I am not allowed to do.

**My recommendation.** None on the names — those are yours. On the structure: make it a table rather
than a fixed list, so you can add a category later without a migration.

**Your answer:**
>you pick

---

### `OPEN-SEAT-02` — wheelchair accessible seats? · **RESERVED (legal)**

**Question.** Are there wheelchair spaces or accessible seats that must be marked as such, and are
there rules about who may book them?

**Why it matters.** In many countries this is a legal requirement, not a feature. It also changes
the seat map design — an accessible seat needs to be identifiable without relying on colour, and it
may need to be held back from general sale.

**My recommendation.** None offered — this may carry a legal obligation in your country and that is
not mine to assume.

**Your answer:**
>no forget that this is demo project.

---

### `OPEN-SEAT-03` — are any seats sold only in pairs?

**Question.** Do you have couple seats, or any seat that cannot be sold on its own?

**Why it matters.** This is a bigger deal than it looks. Right now the lock is per seat. If seats
come in pairs, the lock is per **group**, and "two people clicking at the same millisecond" becomes
a harder problem — you have to acquire two locks atomically or neither.

**My recommendation.** If the answer is no, say no clearly, because it simplifies the hardest part
of the system. If yes, it is worth building properly from the start rather than retrofitting.

**Your answer:**
>
no such thing
---

### `OPEN-SEAT-04` — block single-seat gaps?

**Question.** Some cinemas stop you leaving exactly one empty seat between your booking and the next
one, because a single orphan seat rarely sells. Do you want that rule?

**Why it matters.** If yes, it must be enforced **while the customer is picking**, greying out the
seats that would create a gap — not at the end. A rule that only fires at checkout means the customer
picks seats, enters payment details, and is then told no.

**My recommendation.** Not in v1. It is a real usability improvement but it interacts badly with
concurrent booking — a legal selection can become illegal because someone else booked next to you
while you were choosing.

**Your answer:**
>no such rule.

---

# Part 4 — Booking rules

### `OPEN-HOLD-01` — how long are seats held? *(the one that already went wrong)*

**Question.** How long do we hold seats while a customer pays?

**Why this one is flagged.** In `CLIENT_ASK.md §10.9` you asked this as an open question and wrote
"we assumed 7 minutes". In `CLAUDE_CODE_BRIEF.md §8.1.1` you then wrote 7 minutes as a firm
requirement. **Your assumption became a specification without anyone actually deciding it.** That is
recorded in `GOTCHAS.md` as the one trap already confirmed present on this project. So: is 7 minutes
the real answer, or was it a placeholder?

**Why it matters.** Too short and customers lose seats mid-payment on a slow connection. Too long
and a few abandoned checkouts can make a popular Friday show look sold out when it is not.

**My recommendation.** 7 minutes is reasonable — just confirm it deliberately. Also make it a
configuration value, not a constant, so you can change it without a deploy.

**Your answer:**
>make this 3 minutes.

---

### `OPEN-BOOK-01` — maximum seats in one booking?

**Question.** What is the most seats one customer can book at once?

**Why it matters.** It is the main defence against someone locking out an entire screen. Without a
cap, a script can hold every seat in the house for 7 minutes, repeatedly, and the cinema sells
nothing.

**My recommendation.** 10. Common in the industry, and high enough that real groups are not blocked.

**Your answer:**
>10 maxx

---

### `OPEN-BOOK-02` — can a guest book without an account?

**Question.** Must a customer register before booking, or can they book with just an email address?

**Why it matters.** This is a structural decision, not a preference. If guests can book, a booking
can exist without a user account, which changes the database, and it also raises "how does a guest
see or cancel their booking later" — usually a booking reference plus the email address.

Requiring an account is simpler and gives you the booking history `§5.4.2` asks for. Allowing guests
converts more customers.

**My recommendation.** Require an account in v1. `§5.4.2` and `§5.4.3` both assume the customer has
one, and guest checkout is a clean thing to add later.

**Your answer:**
>no booking without an account as the recipet will be sent via mail.

---

### `OPEN-BOOK-03` — when do ticket sales stop?

**Question.** How long before a show starts do we stop selling tickets? At the start time? 15
minutes before? After it has started?

**Why it matters.** It needs an exact rule because it has to be enforced in three places: the
showtime list, the seat map, and the confirm endpoint. And there is an edge case that needs an
answer — what happens when the cut-off passes **while a customer is on the payment screen** holding
valid seats?

**My recommendation.** Stop 20 minutes after the advertised start (trailers), and let anyone who
already holds seats finish their checkout — refusing at the last step after taking a payment
intent is worse than selling a ticket to someone arriving late.

**Your answer:**
>yes 15 minutes

---

### `OPEN-CANCEL-01` — can customers cancel, and do they get money back? · **RESERVED (money)**

**Question.** `CLIENT_ASK.md §5.4.3` says a customer can cancel "within an allowed window". What is
the window, and is the refund full, partial, or nothing?

**Why it matters.** Refunds are irreversible and they are money. It also decides whether the seat
goes back on sale immediately after a cancellation, which affects the seat map and the occupancy
numbers.

**My recommendation.** None offered — this is a money and policy decision.

**Your answer:**
>no refund policy

---

### `OPEN-CANCEL-02` — what if the cinema cancels a show? · **RESERVED (money, irreversible)**

**Question.** A projector breaks and you cancel a screening with 80 tickets sold. What happens —
automatic refunds, credit, or a manual process?

**Why it matters.** Automatic refunds mean the system can move money without a human, which is a
serious capability to build. Manual means someone needs a screen listing every affected booking.

**My recommendation.** None offered.

**Your answer:**
>
no forget this.
---

# Part 5 — Pricing

### `OPEN-PRICE-01` — what does price depend on? · **RESERVED (money)**

**Question.** Does the ticket price vary by seat category, time of day, day of the week, the movie,
or some combination?

**Why it matters.** This decides whether price is a single column on a showtime or a whole pricing
table with rules. Getting it wrong means rebuilding the pricing engine after showtimes exist.

**Options, without a recommendation:** (a) one price per showtime, set by the manager; (b) price per
seat category per showtime; (c) a rules table — category × day × time band. (b) is where most
cinemas actually sit.

**Your answer:**
>
the admin will set the ticket price and more the premium ticket the more% fix price increase across all halls or any movie show.
---

### `OPEN-PRICE-02` — discounts, student pricing, booking fees? · **RESERVED (money)**

**Question.** Do you need discount codes, student or senior pricing, or a per-booking convenience
fee?

**Why it matters.** A booking fee is easy. Discount codes are a whole subsystem — code generation,
usage limits, expiry, and the abuse cases that come with them.

**My recommendation.** None offered on whether to have them. If you say yes to discount codes, I
would suggest Phase 9 rather than v1.

**Your answer:**
>
no discout for now
---

### `OPEN-PRICE-03` — is tax shown separately? · **RESERVED (money, legal)**

**Question.** Does the ticket and the checkout page need to break out tax as its own line?

**Why it matters.** In many places this is a legal requirement on a receipt. It also has to be
decided **before** any booking is stored, because a stored total with no tax breakdown cannot be
split apart afterwards.

**My recommendation.** None offered.

**Your answer:**
>
no
---

# Part 6 — Payment

### `OPEN-PAY-01` — which real payment provider, eventually? · **RESERVED (money)**

**Question.** v1 is simulated, but which provider is the real one you are heading towards, and do
you already have an account?

**Why it matters.** I do not need it now, but knowing the target shapes the interface. Stripe and
Razorpay have meaningfully different flows — Razorpay is India-first with UPI, Stripe is card-first.
Both use webhooks, which means an inbound route your load balancer has to allow.

**My recommendation.** Naming the target now costs nothing and makes the simulated interface honest
rather than generic. If you genuinely do not know, "don't know yet" is fine.

**Your answer:**
>
we'll have a fake button and flip the flag in DB. i do not want real payment.
---

# Part 7 — Movie data (TMDB)

### `OPEN-TMDB-01` — which region do we pull listings for?

**Question.** TMDB's "now playing" is region-specific. Which country code?

**Why it matters.** Same answer as `OPEN-LOCALE-01`. Listed separately because it is your original
question and I want the answer on the record against this id too.

**My recommendation.** Whatever `OPEN-LOCALE-01` says. If you answer that one, just write "same as
locale" here.

**Your answer:**
>rather make it simple we'll no longer pull the movies. the admin will upload them manually and then they will get sorted based on the customers filter, but by default the latest movie will be on top.

---

### `OPEN-TMDB-02` — should customers see upcoming films before tickets are on sale?

**Question.** `§5.1.2` says show upcoming releases separately. Does that mean customers see films
that have no showtimes yet, with no way to book?

**Why it matters.** It is good for the customer, but it needs a clear state on screen so nobody
thinks the site is broken because there is no "book" button.

**My recommendation.** Yes, show them, with an explicit "tickets not yet on sale" state and no
booking control at all — a disabled button reads as a bug.

**Your answer:**
>no.

---

### `OPEN-TMDB-03` — who approves an imported movie? *(your two clauses disagree)*

**Question.** `§5.5.4` says the **administrator** approves imported movies. `§5.6.2` says
"a staff member". Which role actually has this permission?

**Why it matters.** It is a permission on a specific endpoint, so it needs one answer, not two.

**My recommendation.** Administrator. It is a system-wide action — a published movie appears at
every cinema, so it does not sit naturally with a per-cinema role.

**Your answer:**
> i have defined how the admin will work on the top.

---

### `OPEN-TMDB-04` — can staff override what TMDB sent?

**Question.** If someone edits an imported movie — a better poster, a local title, a corrected
certification — and then the daily sync runs again, what should happen? Does the sync overwrite the
human's edit, or leave it alone?

**Why it matters.** This is the one in this section that can quietly destroy work. Get it wrong and
every night at 3am the sync wipes out corrections someone made during the day, and nobody notices
for a week because nothing errors.

**My recommendation.** Track which fields a human has edited and never overwrite those. Everything
else refreshes. It is a small amount of extra work now and it prevents a failure that is invisible
until it is expensive.

**Your answer:**
> yeah for this the admin will add the new movies posters and other stuff which will be displayed to the customers. that's easier to make.

---

# Part 8 — Tickets and entry

### `OPEN-TICKET-01` — QR code, a reference number, or both?

**Question.** What does the customer actually arrive with?

**Why it matters.** `CLAUDE_CODE_BRIEF.md §8.5.1` already assumes a QR code, so this is mostly a
confirmation. A human-readable reference matters as a fallback when a phone screen is cracked, dead,
or too dim for a scanner.

**My recommendation.** Both. QR for scanning, and a short reference like `FR-8H2K-4N` that staff can
type. The reference costs almost nothing and it is what saves you at the door.

**Your answer:**
>the receipt sent on email which has a unique ID. that will be shown at the entrance.

---

### `OPEN-TICKET-02` — does ticket validation need to work offline?

**Question.** If the internet drops at the door on a Friday night, does staff need a way to still
let people in?

**Why it matters.** This is a much bigger question than it appears. Offline validation means the
scanning device holds a copy of valid tickets, which means it can be stolen and read, and it means
two doors can both accept the same ticket because neither can see the other's state. It is a
different security model, not a fallback screen.

**My recommendation.** Not in v1. Instead: staff can look up a booking by reference and mark it used
manually, and if the internet is down entirely they fall back to the paper process you use today.

**Your answer:**
>we will have manual check up with the unique ID sent out to the customer with the booking recipet and seat number and all that stuff.

---

# Part 9 — Reporting

### `OPEN-REPORT-01` — what do you need to see, and how often?

**Question.** `§5.5.2` asks for occupancy and revenue per show, per day, and per movie. Which of
those do you look at **daily**, and which **weekly**?

**Why it matters.** It decides what gets computed live versus what gets pre-calculated. A daily
number that takes 8 seconds to load is a number nobody looks at.

**My recommendation.** "You pick" is fine here. I will build occupancy-per-show and
revenue-per-day as the live screen, and treat per-movie as a weekly view.

**Your answer:**
>reporting will be done to the mamagers and admins as they will have a dashboard.

---

### `OPEN-REPORT-02` — do you need a spreadsheet export?

**Question.** Does management need to download the numbers as a CSV or Excel file?

**Why it matters.** Mostly easy. The one thing to be careful about: an export of booking data
contains customer names and emails, so it is a data-protection surface, not just a download button.

**My recommendation.** Yes to a CSV of aggregate numbers (occupancy, revenue). No to exporting
customer-level booking data in v1 unless you specifically need it.

**Your answer:**
>No

---

# Part 10 — Operations

### `OPEN-OPS-01` — who gets told when the site goes down?

**Question.** If the site is down at 7pm on a Friday, how does anyone find out?

**Why it matters.** Right now the honest answer is "nobody, until a customer complains". That is a
legitimate choice for a project like this, but it should be written down as an accepted risk rather
than left as a hole you discover later.

**My recommendation.** A CloudWatch alarm on running-task-count below 1, emailing you through SNS.
It is free-tier, it is one more AWS service for you to configure, and it turns "nobody" into "you".

**Your answer:**
>yes follow recommendation. my email id: [REDACTED BY THE BUILD SESSION — this repository is
>PUBLIC. The address was supplied by the client on 2026-08-14 as the CloudWatch/SNS alert
>destination. It lives in the SNS subscription and in local .env, never in git. Nothing downstream
>needs the literal string. Removed before the first commit that would have published it — it has
>never been pushed.]

---

### `OPEN-OPS-02` — how long must booking records be kept? · **RESERVED (legal)**

**Question.** Is there a legal or accounting requirement for how long you keep booking and payment
records?

**Why it matters.** It sets whether anything is ever deleted, and it interacts with data-protection
rules about not keeping personal data longer than needed. Deleting rows is a one-way door.

**My recommendation.** None offered.

**Your answer:**
>for now forever we'll change that later if i ask.

---

### `OPEN-OPS-03` — do you need to see who changed what?

**Question.** Do you need a readable log of staff actions — who changed a price, who cancelled a
show, who published a movie?

**Why it matters.** The system will **write** these records regardless; `§7.6` requires being able
to answer "who booked this seat and when", and every privileged action logs alongside its change.
This question is only about whether you need a **screen to read them**.

**My recommendation.** Write them from day one (already required). Build the screen in Phase 9. The
data being there is what matters; reading it is rarely urgent until it suddenly is.

**Your answer:**
>the admin will only be the one who does changes in movie , cancel a show or other priviledged things..no other persona.

---

# Part 11 — Raised while drafting the Constitution

### `OPEN-TLS-01` — HTTPS on the deployed site?

**Question.** You have a load balancer, so proper HTTPS is available and free — AWS Certificate
Manager issues certificates at no cost for use with an ALB. Do you want TLS terminated there, and do
you have a domain name?

**Why it matters.** Without it, the login cookie travels in clear text, and I am required to keep
calling the deployed environment something other than "production" in every document. With a domain
and ACM it is a fifteen-minute job for you and it removes a whole class of caveat.

**Note:** ACM is not on your forbidden list and costs nothing for ALB use, so this does not breach
the free-tier constraint. You do need a domain name, which is the only real cost.

**My recommendation.** Yes. Get a cheap domain, request an ACM certificate, terminate at the ALB.

**Your answer:**
>I will look if i can get a free domain somewhere. 

---

### `OPEN-SEED-01` — what should the sample cinemas be called?

**Question.** `§6.1.6` asks for seed data with sample cinemas, screens and showtimes. What should
they be called? Real names you plan to use, or obviously fictional ones?

**Why it matters.** Inventing plausible cinema names is inventing your product's content, and I am
not allowed to do that — partly because fake names have a way of surviving into production and
appearing on a real customer's ticket.

**My recommendation.** Obviously fictional and clearly fake: "Demo Cinema — Northgate", "Demo Cinema
— Riverside". Nothing that could be mistaken for real. Or give me the real ones.

**Your answer:**
>nope do not generate anything just generate a few fake records which we will ingest to showcase the bookings. I will bring poster and movie titles and we'll fill them with dummy data for demo. dummy data for about a month would be nice.

---

### `OPEN-AWSREAD-01` — which AWS account, and what am I allowed to look at?

**Question.** You gave me read-only credentials to check your work. Which account and region are
they for, and is it a development environment only — or will I at some point be looking at something
holding real customer and payment data?

**Why it matters.** Reading a production database's configuration is a different thing from reading
a sandbox's. I want the boundary written down before I use the keys, not after.

**My recommendation.** Development only until you say otherwise. I will not run anything beyond
`describe`, `list` and `get`, and I will not create, change or delete anything at any point without
you saying so in writing.

**Your answer:**
>yes follow recommendation.

---

### `OPEN-MODEL-01` — AI and data handling · **RESERVED (legal)**

**Question.** Once this holds real customer names, emails and payment records: what code and data is
allowed to be sent to an AI model, and are you comfortable with the vendors that implies becoming
processors of that data?

**Why it matters.** It does not matter today — there is no real data. It will matter the day before
you launch, and it is much easier to answer now.

**My recommendation.** None offered — this is a legal and data-protection question.

**Your answer:**
>nothing like AI for now.

---

## When you are done

You do not need to finish all 40. Answer what you can, leave the rest blank, and I will file the
blanks as `DECLINED` with a working default marked `ASSUMED` — never as a settled decision.

Once you hand this back, `GOAL_01` files your answers verbatim as `SRC-003`, hashes it, appends an
erratum to `SRC-001` or `SRC-002` wherever your answer corrects something they say, and flips the
Article X rows to `RULED` or `DECLINED`. Then `GOAL_02` can start.
