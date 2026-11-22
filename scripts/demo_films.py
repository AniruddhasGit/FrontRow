"""CR-006 addendum (owner, 2026-11-22): put the owner's demo films on a running database, in one go.

  DATABASE_URL=<owner url> python scripts/demo_films.py

Idempotent: a film is found by title and updated, never duplicated. What it does:
  1. adds the films' vocabulary (certifications, a language, genres) if missing;
  2. upserts the films, published, with posters that ship with the website (/art/films/<slug>.webp; the poster
     route redirects there, and the 3D screen loads <slug>-still.webp beside it);
  3. renames the two formats (2D, IMAX), withdraws the DEMO vocabulary, unpublishes the four DEMO MOVIE placeholders (kept, so every past booking still names its film);
  4. re-assigns every FUTURE showtime that nobody has booked across the films in turn (each plays daily), with
     ends_at = starts_at + the new runtime + 15 minutes; from then on the schedule top-up keeps rotating them.
No audit row: there is no actor, as with the seed. The owner's AI-generated art; names and faces are invented.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import psycopg

# title, slug, runtime, certification, genres, synopsis
FILMS = [
    ("Outpost 77", "outpost-77", 118, "PG-13", ["Sci-Fi", "Thriller"],
     "A research team at a remote ice station drills into something that has been frozen in the glacier for ten "
     "thousand years, and it is still sending a signal."),
    ("The Iron Garden", "the-iron-garden", 124, "PG", ["Fantasy", "Adventure"],
     "In a smog-choked steampunk city, a young engineer and a disgraced inventor find a living garden growing "
     "through the gears beneath the streets."),
    ("Echoes of the Desolate", "echoes-of-the-desolate", 131, "PG-13", ["Action", "Sci-Fi"],
     "Years after the collapse, a scavenger and her salvaged war-machine companion cross the wasteland to bring "
     "hope back to the last settlement."),
    ("Deep Sea Reckoning", "deep-sea-reckoning", 112, "PG-13", ["Action", "Thriller"],
     "Four thousand metres down, a salvage crew boards an abandoned Cold War base and wakes a war that never ended."),
    ("The First Chronicle", "the-first-chronicle", 141, "PG", ["Fantasy", "Adventure"],
     "Before the maps, the world was endless. A young cartographer and a weathered guide set out to chart the edge "
     "of everything."),
    ("Neon Reverie", "neon-reverie", 116, "R", ["Sci-Fi", "Thriller"],
     "In a rain-soaked megacity where memories can be bought and rewritten, a detective finds his own past was "
     "edited."),
    ("The Last Stage", "the-last-stage", 127, "PG-13", ["Western", "Drama"],
     "A frontier guide and his daughter lead the last stagecoach of the season through a mountain pass as the "
     "winter closes in."),
    ("Apartment 4B", "apartment-4b", 98, "R", ["Horror", "Thriller"],
     "A young woman moves into a cheap apartment in an old building and learns why nobody stays past the first "
     "month."),
    ("Voidbound", "voidbound", 121, "PG-13", ["Sci-Fi", "Action"],
     "When the deep-space freighter Ares-IV breaks apart, two survivors have hours to repair it before the silence "
     "takes them."),
    ("Aria and the Star Whales", "aria-and-the-star-whales", 96, "PG", ["Animation", "Family"],
     "A young musician sails a sky-ship above the clouds to follow the song of the star whales and find her way "
     "home."),
    ("Echoes of the Steppe", "echoes-of-the-steppe", 133, "PG-13", ["Drama", "Adventure"],
     "On the endless grasslands, a young eagle hunter and her grandfather ride to save their herd and the old ways "
     "of their people."),
    ("The Dragon's Oath", "the-dragons-oath", 138, "PG-13", ["Fantasy", "Action"],
     "In a ruined mountain kingdom, a young squire and a hardened ranger make a bond with the last dragon, and an "
     "army comes to break it."),
    ("The Astral Grimoire", "the-astral-grimoire", 122, "PG", ["Fantasy", "Adventure"],
     "In a library city floating above the clouds, an apprentice opens a book of star magic that her master swore "
     "would stay closed."),
    ("The Redwood Covenant", "the-redwood-covenant", 104, "R", ["Horror", "Thriller"],
     "A couple renting a cabin deep in the redwoods find the masked people of the forest keep an old promise to the "
     "trees."),
    ("The Marigold Reunion", "the-marigold-reunion", 109, "PG-13", ["Comedy", "Family"],
     "Three generations, one villa, one wedding cake and a week of summer in which every family secret comes out at "
     "dinner."),
    ("The Edge of the Map", "the-edge-of-the-map", 129, "PG-13", ["Adventure", "Action"],
     "An explorer follows a dead man's journal into the jungle, to a temple no map has ever marked."),
    ("Paws & Claws: The Great Alley Caper", "paws-and-claws", 92, "PG", ["Animation", "Family"],
     "A streetwise cat and a scruffy terrier team up with every stray on the block to pull off the heist of the "
     "summer."),
    ("Caldera", "caldera", 117, "PG-13", ["Action", "Sci-Fi"],
     "A rescue team drops into a hidden volcanic valley where something has survived for sixty-six million years."),
    ("Iron Horizon", "iron-horizon", 135, "R", ["War", "Action"],
     "Cut off on the front line with the storm closing in, a squad leader has one night to hold the ridge."),
    ("Silent Sky", "silent-sky", 114, "PG-13", ["Sci-Fi", "Thriller"],
     "When every light on Earth goes out, a paramedic crosses the occupied city to find her brother before the "
     "machines find her."),
]
LANGUAGE = "English"
CHANGEOVER = timedelta(minutes=15)


def lookup(cur, table: str, name: str) -> int:
    row = cur.execute(f"SELECT id FROM {table} WHERE name = %s", (name,)).fetchone()
    if row:
        return row[0]
    return cur.execute(f"INSERT INTO {table} (name, is_active) VALUES (%s, true) RETURNING id", (name,)).fetchone()[0]


def main() -> None:
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    now = datetime.now(timezone.utc)
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        last = cur.execute("SELECT max(starts_at) FROM showtime").fetchone()[0] or now
        language = lookup(cur, "language", LANGUAGE)
        ids, runtime = [], {}
        for title, slug, minutes, cert, genres, synopsis in FILMS:
            cert_id = lookup(cur, "certification", cert)
            row = cur.execute("SELECT id FROM movie WHERE title = %s", (title,)).fetchone()
            values = (synopsis, minutes, cert_id, language, f"/art/films/{slug}.webp", now - timedelta(days=1),
                      last + timedelta(days=1))
            if row:
                mid = row[0]
                cur.execute("UPDATE movie SET synopsis = %s, runtime_minutes = %s, certification_id = %s, language_id = %s, "
                            "poster_object_key = %s, published_at = coalesce(published_at, now()), display_from = %s, "
                            "display_until = greatest(display_until, %s), version = version + 1 WHERE id = %s", (*values, mid))
            else:
                mid = cur.execute(
                    "INSERT INTO movie (title, synopsis, runtime_minutes, certification_id, language_id, poster_object_key, "
                    "published_at, display_from, display_until, version) VALUES (%s, %s, %s, %s, %s, %s, now(), %s, %s, 1) "
                    "RETURNING id", (title, *values)).fetchone()[0]
            for g in genres:
                cur.execute("INSERT INTO movie_genre (movie_id, genre_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (mid, lookup(cur, "genre", g)))
            ids.append(mid)
            runtime[mid] = minutes
        # the seed's placeholder vocabulary: real format names, and the unused DEMO labels withdrawn from the filters
        cur.execute("UPDATE format SET name = '2D' WHERE name = 'DEMO FORMAT 1'")
        cur.execute("UPDATE format SET name = 'IMAX' WHERE name = 'DEMO FORMAT 2'")
        for table in ("language", "certification", "genre"):
            cur.execute(f"UPDATE {table} SET is_active = false WHERE name ~ '^DEMO '")
        cur.execute("UPDATE movie SET published_at = NULL, version = version + 1 WHERE title ~ '^DEMO MOVIE [0-9]{2}$' "
                    "AND published_at IS NOT NULL")
        future = cur.execute(
            "SELECT s.id, s.screen_id, s.starts_at FROM showtime s WHERE s.starts_at > %s "
            "AND NOT EXISTS (SELECT 1 FROM booking b WHERE b.showtime_id = s.id) ORDER BY s.starts_at, s.screen_id",
            (now,)).fetchall()
        # every day's shows (24: 4 slots x 6 halls) are dealt across all the films in turn (20 films: most play daily)
        for k, (sid, screen, starts) in enumerate(future):
            film = ids[k % len(ids)]
            cur.execute("UPDATE showtime SET movie_id = %s, ends_at = %s, version = version + 1 WHERE id = %s",
                        (film, starts + timedelta(minutes=runtime[film]) + CHANGEOVER, sid))
        print(f"demo films: {len(ids)} published, {len(future)} future showtimes rotated across them")


if __name__ == "__main__":
    main()
