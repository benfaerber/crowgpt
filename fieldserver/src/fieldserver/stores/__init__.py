"""One store per table, and the read-only views across them.

Each store owns exactly one table's rows and the rules that go with them: what
an idempotent create means for it, which columns a client may change afterwards,
what has to be true before a row is written. They are plain classes over
sqlite3 — no ORM, because the queries here are the interesting part and hiding
them behind one would cost more than it saved.

`db_base` is the shared connection handling (WAL, busy timeout, foreign keys),
and `dashboard` is the exception to one-store-one-table: it only reads, and it
reads across all of them. `config_store` is the second sanctioned exception —
its nine tables are one served document, versioned as a unit, and nine stores
that could only ever be used together would be the rule without its point.
Its seed vocabulary (and the record of why each entry exists) is
`config_seed`.
"""
