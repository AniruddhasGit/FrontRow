"""The admin domain (E6, Phase 2): venue, halls, seats, seat categories, showtimes, managers.

Every rule lives here, not in the handlers under app/api/admin/, because the admin API is not the only
caller (FR-ADR-022): a handler parses the body, calls one function in this package and returns what it
returns. Each write function opens ONE transaction on the request's connection and writes the change and
its audit row(s) inside it (P-ADM-19).
"""
