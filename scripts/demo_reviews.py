"""Demo ratings and reviews (owner, 2026-11-23): hundreds of star ratings per film, a share of them with a written
review, and Helpful votes, put on a running database in one go.

  DATABASE_URL=<owner url> python scripts/demo_reviews.py

What it does, in ONE transaction:
  1. the demo crowd: customer-51@ .. customer-750@ at the seed's domain (the seed's email pattern, the seed's own
     password hash copied from customer-01, so no password is read, hashed or printed here; a made-up handle as the
     display name, or none). customer-01..50 are the seed's logins and are never used as raters;
  2. for every published film already released (not Coming soon) that has no crowd rating yet: 120-450 ratings dated
     between its release (at most 60 days back) and now, plus 25-45% more dated over the NEXT 120 days. Every rating
     read shows a row only from its created_at on (app/domain/browse/catalogue.py rating_shown), so new ratings and
     reviews appear day by day and the averages drift, with no job and no timer;
  3. each film gets its own quality (an average of about 5.5-8.8 out of 10) and a real-looking spread, low scores
     included; 25-40% of ratings carry text whose tone follows the score (1-4 negative, 5-6 mixed, 7-10 positive);
  4. Helpful votes from other crowd accounts, most reviews none, a few many, each dated after its review.

Idempotent: a film that already has a crowd rating is skipped whole, so a re-run adds only films released since.
Deterministic: every choice comes from random.Random seeded with the film's title, so a re-run on a fresh copy of the
same catalogue writes the same scores and texts.

THE TEXT IS GENERIC ON PURPOSE. No title, plot, character, actor, place or genre word: only pacing, the ending, the
acting in general, the hall, the seats, value, rewatching, who they went with. A sentence a reader could check against
one film would give the simulation away. A review is one to three sentences from its tone's pool, so the same exact
text rarely repeats on a page.

VERIFIED VIEWERS: NOT made, on purpose. The app's own write gate wants a paid booking for a show of the film that has
started. The crowd's ~10,000 ratings would need ~10,000 bookings on PAST shows, but the demo films only have past
shows since CR-006 rotated them in (a few days of history), and the future-dated ratings would need bookings on shows
that have not happened yet. Faking them would put ~10,000 extra sales into the manager and admin figures. So these rows
are written directly, as the seed writes its bookings; the gate stays the rule for every real customer.

No audit row: there is no actor, as with the seed. No card data, no real person: the handles are made up from words.
"""

from __future__ import annotations

import os
import random
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

# The crowd's numbers. app/domain/demo_fill.py books seats for the same accounts (tests/demo keeps the two equal);
# this script needs only psycopg, like demo_films.py, so it does not import the app.
CROWD_FIRST, CROWD_SIZE = 51, 700
PAST_DAYS, FUTURE_DAYS = 60, 120
NOW_COUNT = (120, 450)  # ratings visible on the day of the run
LATER_SHARE = (0.25, 0.45)  # and this many more again, dated over the next FUTURE_DAYS
QUALITY = (5.5, 8.8)
TEXT_SHARE = (0.25, 0.40)

POSITIVE = [
    "Absolutely worth the ticket.", "Loved every minute of it.", "One of the best nights out I've had in a while.",
    "The pacing was spot on, never felt long.", "Great performances across the board.",
    "The sound in the hall was incredible.", "Seats were comfy and the screen looked amazing.",
    "I'd happily watch it again.", "Went in with low expectations and came out grinning.",
    "The ending really stayed with me.", "Really well made, you can tell people cared about it.",
    "Solid from start to finish.", "Brought my parents and they enjoyed it as much as I did.",
    "Went with a group of friends, we talked about it all the way home.", "Everyone in our row was hooked.",
    "The last half hour is brilliant.", "Beautifully shot, the big screen does it justice.",
    "Worth seeing in a proper cinema rather than at home.", "So good. Already planning a second visit.",
    "The cast clearly had great chemistry.", "Didn't check my phone once, which says a lot.",
    "It earns every minute of its runtime.", "The music fit perfectly.", "loved it",
    "honestly one of the better ones this year.", "great night out, no complaints.", "Surprisingly moving in places.",
    "The opening grabbed me straight away.", "Lovely to see a full hall reacting together.",
    "The audience clapped at the end, which you don't see often.",
    "Crisp picture, booming sound, comfy recliners. Perfect.", "Smart writing and it never talks down to you.",
    "Strong lead performance that holds the whole thing together.", "The supporting cast is just as good.",
    "It looks gorgeous on a big screen.", "Kept me guessing right up to the end.",
    "Exactly what I wanted from a night at the cinema.", "Not a wasted scene.", "I went twice in one week, no regrets.",
    "Good pace, good performances, good ending. What more do you want.",
    "Took my partner for date night and we both loved it.",
    "Really impressive, I wasn't expecting it to be this good.", "The atmosphere in the hall made it even better.",
    "Fantastic. Go see it on the biggest screen you can.", "Gripping from the first scene.", "Has real heart.",
    "Felt shorter than it was, in a good way.", "I'm still thinking about it days later.",
    "The ending landed perfectly for me.", "The best thing I've seen here in months.", "Every performance felt real.",
    "Brilliant use of sound, the whole room felt it.", "worth every cent.",
    "Great booking experience too, seats exactly where I wanted.", "Very satisfying ending.",
    "Clever, confident and a joy to watch.", "Strong from start to end, a couple of moments gave me chills.",
    "My friends dragged me along and I'm glad they did.",
    "Good enough that I'm recommending it to everyone at work.", "A really well told story.",
    "Excellent. The time flew by.", "Visually stunning and well acted.",
    "The hall was packed and the energy was great.", "So much better than I expected.",
    "Touching without being cheesy.", "Nicely paced, no dull stretches.", "Proper big screen experience.",
    "I teared up a bit near the end, not gonna lie.", "One I'll be buying when it comes out at home.",
    "It just works on every level.", "Absolutely brilliant, go.", "Gorgeous to look at and great to listen to.",
    "A confident, well crafted film.", "Fully deserves the good word of mouth.", "The pacing in the middle is perfect.",
    "Best seats I've had, and the film matched them.", "Came out buzzing.", "Very rewatchable.",
    "A treat from beginning to end.", "Really good, the second half especially.",
    "Brilliant performances, especially from the lead.", "My dad doesn't like anything and even he enjoyed it.",
    "Wonderful. I didn't want it to end.", "Had high hopes and it delivered.", "great acting, great sound, great seats.",
    "Fantastic film, fantastic cinema.", "The sound mix was perfect.", "really enjoyed this one!!", "Totally gripped.",
    "Thoughtful and well acted.", "It's the kind of film you want to talk about afterwards.",
    "Impressive work from everyone involved.", "A really polished piece of work.", "Great story, told well.",
    "I'd give it an 11 if I could.", "Everything clicked.", "This is why I still go to the cinema.",
    "Glad I saw it on the big screen.", "The final scene is perfect.",
    "Kept the whole room quiet, everyone was hooked.", "Would definitely recommend.", "the ending got me.",
    "Not perfect but I loved it anyway.", "Easily the best film I've seen this month.",
    "Strong performances and a great finish.", "Very well directed.", "A memorable night out with friends.",
    "Second time watching and it holds up.", "It's even better the second time.", "Really immersive.",
    "Had me hooked the whole way through.", "So well done. Go see it.", "Superb.",
    "Great experience overall, film and cinema both.", "Watched it with my sister, we both want to go again.",
    "Classy, well paced and properly entertaining.", "Rarely see an audience this into a film.",
    "A great reminder of why the big screen matters.", "Big recommend.", "excellent, just excellent.",
    "Wasn't sure about it from the trailer but it won me over.", "Brilliantly acted.", "realy good, worth it",
    "Defintely worth a watch.", "Amazing film. The seats were super comfortable too.",
]
MIXED = [
    "It was fine. Not great, not bad.", "Good first half, the second half dragged a bit.", "Decent, but a bit too long.",
    "Some strong moments, some flat ones.", "The acting was good but the pacing was all over the place.",
    "Enjoyable enough for a night out.", "Worth a watch, probably not twice.", "The ending didn't fully work for me.",
    "Started slow but picked up.", "Good performances let down by a rushed ending.", "Fine for a matinee price.",
    "I'd wait for it to come out at home.", "It's okay. I expected a bit more.", "Liked it more than my friends did.",
    "My friends loved it, I thought it was just alright.", "Not bad at all, just a bit forgettable.",
    "A few too many slow stretches.", "Good to look at, but it didn't grab me.", "The middle section lost me a little.",
    "Solid but safe.", "Mixed feelings. Some parts were brilliant, others dragged.", "Decent watch, nothing special.",
    "A bit uneven but has its moments.", "Sound was great, the film itself was average.",
    "The cinema was lovely, the film was so-so.", "Could have lost twenty minutes.", "Middle of the road for me.",
    "it was ok", "meh, it was alright.", "Good enough, but I won't remember much of it next week.",
    "The first hour is strong, then it runs out of steam.", "I wanted to like it more than I did.",
    "Not my favourite, but I can see why people like it.", "Some good ideas, not all of them land.",
    "Performances were good, the writing less so.", "Pleasant enough way to spend an evening.",
    "Bit predictable but well made.", "The ending felt rushed.", "I liked it, my partner didn't.", "Good, not great.",
    "Watchable, but I'm not sure it needed to be this long.", "Fine. The seats were the highlight honestly.",
    "Kind of slow, but the last act makes up for some of it.", "Average. Glad I went on a discount day.",
    "It had potential.", "A few great scenes in an otherwise ordinary film.", "I was entertained, just not blown away.",
    "Decent but overhyped.", "Somewhere between a 5 and a 6 for me.", "Looked great, felt a little hollow.",
    "The pacing is off in the middle.", "Not as good as the reviews made out.",
    "Good lead performance, weak supporting characters.", "Okay for a one time watch.",
    "It's fine if you go in with low expectations.", "Honestly a bit mixed on this one.",
    "Some moments really work, others feel like filler.", "Started great, ending was a letdown.",
    "Not bad, but not one I'd rush back for.", "I think it would work better at home.",
    "It was alright, the audience was more fun than the film.", "Kept my attention, mostly.",
    "Fairly average, the sound in the hall helped.", "A decent effort but nothing new.", "It's ok. a bit long.",
    "Entertaining in parts.", "Wouldn't say no to seeing it again, wouldn't push for it either.",
    "Liked the start, lost interest near the end.", "Good in places but it drags.",
    "Not sure how I feel about the ending.", "Some solid acting, but the story wanders.", "Fine, just fine.",
    "abit slow for me but the ending was decent.", "Its alright, nothing to write home about.",
    "Could have been great with a tighter edit.",
]
NEGATIVE = [
    "Really disappointing.", "Way too long and nothing much happens.", "I nearly walked out.",
    "Not worth the ticket price.", "The pacing was painfully slow.", "Flat performances all round.",
    "The ending made no sense to me.", "Couldn't wait for it to finish.", "Expected so much more.",
    "Dull from start to finish.", "I checked my watch more than once.", "Badly paced and far too long.",
    "Save your money.", "Not for me at all.", "My friends and I all agreed it was a miss.", "The acting felt wooden.",
    "Boring. Sorry, but it was.", "Fell asleep halfway through.",
    "The first ten minutes were fine, then it fell apart.", "Great cinema, shame about the film.",
    "The seats were comfy, which helped me get through it.", "Overlong and underwhelming.",
    "Messy, confusing, and too loud.", "Way too loud in places, and the story didn't hold up.",
    "Felt like it would never end.", "Nothing about it worked for me.", "One of the weakest films I've seen this year.",
    "I wanted to like it, I really did.", "The ending ruined whatever good there was.", "Two hours I won't get back.",
    "waste of time", "nope.", "Not good. Not even bad in a fun way.", "Lifeless performances and a weak ending.",
    "Pretty forgettable, I already can't remember most of it.", "Would not recommend.",
    "Went with high hopes and left annoyed.", "The trailer was better than the film.",
    "Couldn't connect with any of the characters.", "Very slow, very long, very little payoff.",
    "Half the hall left looking confused.", "It tries hard but nothing lands.",
    "Disappointing, especially after all the buzz.", "Poorly paced, the middle is a slog.",
    "I don't get the hype at all.", "Bland.", "The writing let everyone down.", "Not worth a second look.",
    "I'd skip this one.", "The only good thing was the sound system.", "Too long by at least half an hour.",
    "It just never got going.", "Really let down by the ending.", "Even the good actors couldn't save it.",
    "honestly pretty bad.", "Dragged on and on.", "I came out more tired than entertained.",
    "Wish I'd picked something else.", "Big disappointment for me.", "Confusing and dull.",
    "Didn't work for me on any level.", "Nothing memorable about it.", "Hard to sit through.",
    "Weak story, weak ending.", "Not my thing, and I tried.", "Uninspired.", "dont bother.", "realy boring, sorry.",
    "My partner liked it a bit, I really didn't.", "Felt like three films stitched together, none of them good.",
    "The cinema itself was great, the film was a chore.", "I kept waiting for it to get better.",
    "Average at best, and that's being kind.", "Not worth leaving the house for.", "Left before the end.",
    "Very forgettable.",
]
# Handles for the crowd's display names: two everyday words, sometimes with a number. Nobody's name.
HANDLE_A = ["quiet", "late", "aisle", "back", "front", "popcorn", "rainy", "sunday", "midnight", "matinee", "row",
            "slow", "night", "weekend", "reel", "silver", "velvet", "big", "lucky", "early", "corner", "balcony"]
HANDLE_B = ["viewer", "seat", "watcher", "goer", "owl", "fan", "regular", "critic", "buff", "sitter", "ticket", "screen"]


def tone(score: int) -> list[str]:
    return NEGATIVE if score <= 4 else MIXED if score <= 6 else POSITIVE


def compose(rng: random.Random, pool: list[str]) -> str:
    """One to three distinct sentences from one tone's pool. A line without end punctuation only ever stands alone."""
    first = rng.choice(pool)
    n = rng.choices((1, 2, 3), (58, 32, 10))[0]
    if n == 1 or first[-1] not in ".!?":
        return first
    joined = [first]
    for line in rng.sample(pool, min(len(pool), 6)):
        if len(joined) == n:
            break
        if line not in joined and line[-1] in ".!?":
            joined.append(line)
    return " ".join(joined)


def score(rng: random.Random, quality: float) -> int:
    """Real ratings: a bump just above the film's average, a pile of 10s, and a tail of 1-4s that grows as the film
    gets worse. Tuned so the mean lands near `quality`."""
    low = 0.05 + (QUALITY[1] - quality) * 0.04
    if rng.random() < low:
        return rng.choices((1, 2, 3, 4), (35, 20, 22, 23))[0]
    if rng.random() < 0.06 + (quality - QUALITY[0]) * 0.03:
        return 10
    return max(1, min(10, round(rng.gauss(quality + 0.35, 1.45))))


def handle(rng: random.Random) -> str | None:
    if rng.random() < 0.12:
        return None
    a, b = rng.choice(HANDLE_A), rng.choice(HANDLE_B)
    shape = rng.random()
    return (f"{a}{b}" if shape < 0.35 else f"{a}_{b}" if shape < 0.55 else f"{a}{b}{rng.randint(1, 99)}"
            if shape < 0.85 else f"{a.capitalize()}{b.capitalize()}")


def crowd(cur, out) -> list[int]:
    """customer-51.. customer-750 at the seed's domain, created where missing. Returns their ids, by number."""
    seed = cur.execute("SELECT email, password_hash FROM users WHERE role = 'customer' "
                       "AND email ~ '^customer-01@[^@]+[.]invalid$' ORDER BY id LIMIT 1").fetchone()
    if seed is None:
        raise SystemExit("demo_reviews: no seed customer (customer-01@...invalid): run scripts/seed.py first. "
                         "Nothing was written.")
    domain, password_hash = seed[0].split("@", 1)[1], seed[1]
    rng = random.Random("frontrow-crowd")
    emails = [f"customer-{c:02d}@{domain}" for c in range(CROWD_FIRST, CROWD_FIRST + CROWD_SIZE)]
    names = [handle(rng) for _ in emails]
    existing = {e for (e,) in cur.execute("SELECT lower(email) FROM users WHERE lower(email) = ANY(%s)",
                                          (emails,)).fetchall()}
    missing = [(e, password_hash, n) for e, n in zip(emails, names) if e not in existing]
    if missing:
        cur.executemany("INSERT INTO users (email, password_hash, role, password_version, display_name) "
                        "VALUES (%s, %s, 'customer', 1, %s) ON CONFLICT DO NOTHING", missing)
        out(f"crowd accounts created: {len(missing)}")
    ids = dict(cur.execute("SELECT lower(email), id FROM users WHERE lower(email) = ANY(%s)", (emails,)).fetchall())
    return [ids[e] for e in emails]


def run(conn, now: datetime, out=print) -> dict[str, int]:
    """Everything in one transaction on a psycopg connection. Returns {title: ratings written} for the films done."""
    done: dict[str, int] = {}
    with conn.transaction(), conn.cursor() as cur:
        people = crowd(cur, out)
        zone = ZoneInfo(cur.execute("SELECT timezone FROM cinema ORDER BY id LIMIT 1").fetchone()[0])
        today = now.astimezone(zone).date()
        films = cur.execute(
            "SELECT m.id, m.title, m.release_date FROM movie m WHERE m.published_at IS NOT NULL "
            "AND (m.release_date IS NULL OR m.release_date <= %s) "
            "AND NOT EXISTS (SELECT 1 FROM movie_rating r WHERE r.movie_id = m.id AND r.user_id = ANY(%s)) "
            "ORDER BY m.id",
            (today, people)).fetchall()
        ratings, texts = [], {}
        for film_id, title, release in films:
            rng = random.Random(f"frontrow-reviews:{title}")
            quality, share = rng.uniform(*QUALITY), rng.uniform(*TEXT_SHARE)
            now_n = rng.randint(*NOW_COUNT)
            later_n = round(now_n * rng.uniform(*LATER_SHARE))
            opened = datetime.combine(release, time(10), zone) if release else now - timedelta(days=PAST_DAYS)
            start = min(max(opened, now - timedelta(days=PAST_DAYS)), now - timedelta(hours=3))
            span = (now - start).total_seconds()
            # most ratings come soon after release, then they slow down
            moments = [start + timedelta(seconds=span * rng.random() ** 1.7) for _ in range(now_n)]
            moments += [now + timedelta(seconds=FUTURE_DAYS * 86400 * rng.random() ** 1.2 + 1) for _ in range(later_n)]
            for user_id, at in zip(rng.sample(people, now_n + later_n), moments):
                s = score(rng, quality)
                body = compose(rng, tone(s)) if rng.random() < share else None
                at = at.replace(microsecond=0)
                ratings.append((user_id, film_id, s, body, at, at))
                if body:
                    texts[(user_id, film_id)] = (at, len(body))
            done[title] = now_n + later_n
        with cur.copy("COPY movie_rating (user_id, movie_id, score, review_text, created_at, updated_at) "
                      "FROM STDIN") as copy:
            for row in ratings:
                copy.write_row(row)
        # Helpful votes: most reviews none, a few many (longer ones a little more), each after its review.
        rows = cur.execute("SELECT id, user_id, movie_id FROM movie_rating WHERE review_text IS NOT NULL "
                           "AND movie_id = ANY(%s) AND user_id = ANY(%s)", ([f[0] for f in films], people)).fetchall()
        votes = []
        for rating_id, author, film_id in sorted(rows):
            at, length = texts[(author, film_id)]
            rng = random.Random(f"frontrow-votes:{author}:{film_id}")
            k = min(40, int(rng.paretovariate(1.15 if length > 90 else 1.4)) - 1)
            for voter in rng.sample([p for p in people if p != author], max(0, k)):
                votes.append((rating_id, voter, (at + timedelta(hours=rng.uniform(2, 24 * 20))).replace(microsecond=0)))
        with cur.copy("COPY review_vote (rating_id, user_id, created_at) FROM STDIN") as copy:
            for row in votes:
                copy.write_row(row)
    out(f"films rated: {len(done)}, ratings: {len(ratings)}, with text: {len(texts)}, helpful votes: {len(votes)}")
    return done


def main() -> None:
    import psycopg

    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as conn:
        run(conn, datetime.now(timezone.utc))


if __name__ == "__main__":
    main()
