"""What the server is, rather than what it stores.

The shape of the database (`schema`, driven by Alembic), the build it is running
(`build_info`, including the wire version every client checks), where things
live on disk (`paths`), and turning audio into the form it is kept in
(`transcode`).

Nothing here reads or writes a row. That is what makes it safe to import from
anywhere, including from the stores themselves.
"""
