"""baseline — the floor, and the last place ad-hoc schema code lives

Generated from a freshly-built database rather than written by hand, so it is
exactly what the store constructors produced before Alembic took over.

It does two things, and the second is the awkward one. It creates every table,
and it adds any column an older database is missing. That column-adding is the
`_add_column` logic that used to be spread over nine store constructors, brought
here so it exists *once* and only below this line — every revision after this is
an ordinary migration against a known floor.

The tolerance is what lets a database from any earlier era be adopted without
archaeology: bring it to the floor, then migrate forward normally. It cannot fix
a column that exists with the wrong *shape* — SQLite has no ALTER for that — but
nothing needs it to, because `schema.drift()` catches exactly that case and
`batch_alter_table` fixes it in a revision of its own.

Revision ID: 0001_baseline
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

# Verbatim DDL, one string per statement. Data rather than a heredoc because
# several carry comments containing semicolons, and splitting a joined script on
# ";" cuts those in half.
TABLES = [
    ('analysis_jobs', "CREATE TABLE analysis_jobs (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    capture_id INTEGER NOT NULL REFERENCES captures(id) ON DELETE CASCADE,\n                    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,\n                    state TEXT NOT NULL DEFAULT 'queued',\n                    claimed_at TEXT,\n                    finished_at TEXT,\n                    error TEXT,\n                    created_at TEXT NOT NULL\n                )"),
    ('analysis_results', 'CREATE TABLE analysis_results (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    job_id INTEGER NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,\n                    capture_id INTEGER NOT NULL,\n                    duration REAL,\n                    waveform_json TEXT,\n                    reliability_json TEXT,\n                    model_version TEXT,\n                    created_at TEXT NOT NULL\n                )'),
    ('captures', "CREATE TABLE captures (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,\n                    client_uuid TEXT,\n                    latitude REAL,\n                    longitude REAL,\n                    location_name TEXT,\n                    recorded_at TEXT,\n                    duration_sec REAL,\n                    notes TEXT,\n                    family_id INTEGER,\n                    status TEXT NOT NULL DEFAULT 'recording',\n                    created_at TEXT NOT NULL\n                , name TEXT, keep INTEGER NOT NULL DEFAULT 0, app_version INTEGER, app_commit TEXT, observer_role TEXT, silent_confirmed_at TEXT, behavior_guess TEXT, crop_start_sec REAL, crop_end_sec REAL, contributor_id INTEGER REFERENCES contributors(id))"),
    ('config_versions', 'CREATE TABLE config_versions (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    version INTEGER NOT NULL UNIQUE,\n                    published_at TEXT NOT NULL,\n                    notes TEXT\n                )'),
    ('context_defs', 'CREATE TABLE context_defs (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    key TEXT NOT NULL UNIQUE,\n                    category TEXT NOT NULL,\n                    sort_order INTEGER NOT NULL DEFAULT 0,\n                    active INTEGER NOT NULL DEFAULT 1,\n                    version_introduced INTEGER NOT NULL DEFAULT 1\n                )'),
    ('context_events', "CREATE TABLE context_events (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    capture_id INTEGER NOT NULL REFERENCES captures(id) ON DELETE CASCADE,\n                    -- Which call this was the situation for. Retracting the\n                    -- label takes its context with it: a situation attached to\n                    -- a call nobody stands behind any more is not evidence.\n                    label_id INTEGER REFERENCES labels(id) ON DELETE CASCADE,\n                    device_id INTEGER REFERENCES devices(id),\n                    client_uuid TEXT,\n                    -- A key from the served context vocabulary.\n                    key TEXT NOT NULL,\n                    -- Redundant with the label's span, kept so a context event\n                    -- still says when it happened if the vocabulary or the\n                    -- labelling is ever reworked around it.\n                    start_sec REAL,\n                    end_sec REAL,\n                    notes TEXT,\n                    created_at TEXT NOT NULL\n                , contributor_id INTEGER REFERENCES contributors(id))"),
    ('contributors', "CREATE TABLE contributors (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    -- What the outside world is allowed to see. Sequential\n                    -- integer ids leak how many people have signed up and let\n                    -- anyone enumerate them; a public dataset should quote this.\n                    public_uuid TEXT NOT NULL UNIQUE,\n                    display_name TEXT NOT NULL,\n                    role TEXT NOT NULL DEFAULT 'contributor',\n                    -- 'suspended' costs nothing now and is the column you\n                    -- otherwise add in a hurry, the first time someone uploads\n                    -- something they shouldn't have.\n                    status TEXT NOT NULL DEFAULT 'active',\n                    -- Hashed like a device token: it is the secret that joins a\n                    -- second phone to this person. Lost ones are rotated, not\n                    -- recovered.\n                    claim_code_hash TEXT,\n                    created_at TEXT NOT NULL\n                )"),
    ('detected_calls', 'CREATE TABLE detected_calls (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    analysis_id INTEGER NOT NULL REFERENCES analysis_results(id) ON DELETE CASCADE,\n                    start_sec REAL, end_sec REAL,\n                    species TEXT, scientific_name TEXT,\n                    call_type TEXT, confidence REAL, crow_conf REAL\n                )'),
    ('devices', "CREATE TABLE devices (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    device_uuid TEXT NOT NULL UNIQUE,\n                    token_hash TEXT NOT NULL UNIQUE,\n                    locale TEXT NOT NULL DEFAULT 'en',\n                    platform TEXT,\n                    created_at TEXT NOT NULL,\n                    last_seen_at TEXT\n                , contributor_id INTEGER REFERENCES contributors(id), label TEXT, revoked_at TEXT, app_version INTEGER, app_commit TEXT)"),
    ('families', 'CREATE TABLE families (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,\n                    client_uuid TEXT,\n                    name TEXT NOT NULL,\n                    -- Chosen on the phone and stored, so a family keeps the same\n                    -- glow on the map across devices and reinstalls.\n                    color TEXT,\n                    notes TEXT,\n                    created_at TEXT NOT NULL\n                , contributor_id INTEGER REFERENCES contributors(id))'),
    ('instructions', 'CREATE TABLE instructions (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    key TEXT NOT NULL UNIQUE,\n                    sort_order INTEGER NOT NULL DEFAULT 0,\n                    active INTEGER NOT NULL DEFAULT 1,\n                    version_introduced INTEGER NOT NULL DEFAULT 1\n                )'),
    ('label_defs', 'CREATE TABLE label_defs (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    key TEXT NOT NULL UNIQUE,\n                    core_mapping TEXT NOT NULL,\n                    color TEXT,\n                    sort_order INTEGER NOT NULL DEFAULT 0,\n                    active INTEGER NOT NULL DEFAULT 1,\n                    version_introduced INTEGER NOT NULL DEFAULT 1\n                , trains INTEGER NOT NULL DEFAULT 1)'),
    ('labels', "CREATE TABLE labels (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    capture_id INTEGER NOT NULL REFERENCES captures(id) ON DELETE CASCADE,\n                    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,\n                    device_id INTEGER NOT NULL REFERENCES devices(id),\n                    start_sec REAL,\n                    end_sec REAL,\n                    species TEXT NOT NULL,\n                    call_type TEXT NOT NULL,\n                    label_source TEXT NOT NULL DEFAULT 'human',\n                    notes TEXT,\n                    created_at TEXT NOT NULL\n                , contributor_id INTEGER REFERENCES contributors(id), client_uuid TEXT)"),
    ('media', "CREATE TABLE media (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    capture_id INTEGER NOT NULL REFERENCES captures(id) ON DELETE CASCADE,\n                    client_uuid TEXT,\n                    kind TEXT NOT NULL DEFAULT 'audio',\n                    storage TEXT NOT NULL DEFAULT 'local',\n                    storage_ref TEXT NOT NULL,\n                    format TEXT NOT NULL DEFAULT 'wav',\n                    sample_rate INTEGER,\n                    channels INTEGER,\n                    bytes INTEGER NOT NULL DEFAULT 0,\n                    sha256 TEXT,\n                    upload_state TEXT NOT NULL DEFAULT 'pending',\n                    uploaded_at TEXT,\n                    created_at TEXT NOT NULL\n                , input_device TEXT, input_honoured INTEGER, pre_roll_sec REAL)"),
    ('observations', "CREATE TABLE observations (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    capture_id INTEGER NOT NULL REFERENCES captures(id) ON DELETE CASCADE,\n                    device_id INTEGER NOT NULL REFERENCES devices(id),\n                    client_uuid TEXT,\n                    body TEXT NOT NULL,\n                    -- 'voice' means transcribed from a spoken memo rather than typed;\n                    -- worth knowing, since dictated notes read differently.\n                    source TEXT NOT NULL DEFAULT 'typed',\n                    locale TEXT,\n                    created_at TEXT NOT NULL,\n                    updated_at TEXT NOT NULL\n                , contributor_id INTEGER REFERENCES contributors(id))"),
    ('observer_roles', 'CREATE TABLE observer_roles (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    key TEXT NOT NULL UNIQUE,\n                    sort_order INTEGER NOT NULL DEFAULT 0,\n                    active INTEGER NOT NULL DEFAULT 1,\n                    version_introduced INTEGER NOT NULL DEFAULT 1\n                )'),
    ('sightings', 'CREATE TABLE sightings (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    capture_id INTEGER NOT NULL REFERENCES captures(id) ON DELETE CASCADE,\n                    device_id INTEGER REFERENCES devices(id),\n                    client_uuid TEXT,\n                    -- A key from the served context vocabulary — the same one\n                    -- context events use, so the two can be compared.\n                    key TEXT NOT NULL,\n                    -- Seconds relative to the start of the recording. Negative\n                    -- is before it, positive is after. Required: this is the\n                    -- field that makes a sighting a sighting rather than a\n                    -- context event somebody was loose about.\n                    offset_sec REAL NOT NULL,\n                    -- Roughly how far off, in metres. Optional and expected to\n                    -- be a guess — "about a block" is a real answer and a\n                    -- useful one, and demanding precision would only produce\n                    -- invented precision.\n                    distance_m REAL,\n                    notes TEXT,\n                    created_at TEXT NOT NULL\n                , contributor_id INTEGER REFERENCES contributors(id))'),
    ('taxonomy', 'CREATE TABLE taxonomy (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    common_name TEXT NOT NULL UNIQUE,\n                    scientific_name TEXT NOT NULL,\n                    slug TEXT NOT NULL,\n                    has_head INTEGER NOT NULL DEFAULT 0,\n                    active INTEGER NOT NULL DEFAULT 1\n                )'),
    ('translations', 'CREATE TABLE translations (\n                    id INTEGER PRIMARY KEY AUTOINCREMENT,\n                    namespace TEXT NOT NULL,\n                    key TEXT NOT NULL,\n                    locale TEXT NOT NULL,\n                    text TEXT NOT NULL,\n                    UNIQUE(namespace, key, locale)\n                )'),
]

INDEXES = [
    'CREATE UNIQUE INDEX captures_contributor_client_uuid ON captures (contributor_id, client_uuid)',
    'CREATE UNIQUE INDEX context_capture_client_uuid ON context_events (capture_id, client_uuid)',
    'CREATE UNIQUE INDEX families_contributor_client_uuid ON families (contributor_id, client_uuid)',
    'CREATE INDEX idx_captures_contributor ON captures (contributor_id)',
    'CREATE INDEX idx_context_capture ON context_events (capture_id)',
    'CREATE INDEX idx_context_events_contributor ON context_events (contributor_id)',
    'CREATE INDEX idx_context_label ON context_events (label_id)',
    'CREATE INDEX idx_families_contributor ON families (contributor_id)',
    'CREATE INDEX idx_labels_contributor ON labels (contributor_id)',
    'CREATE INDEX idx_observations_capture ON observations (capture_id)',
    'CREATE INDEX idx_observations_contributor ON observations (contributor_id)',
    'CREATE INDEX idx_sightings_capture ON sightings (capture_id)',
    'CREATE INDEX idx_sightings_contributor ON sightings (contributor_id)',
    'CREATE UNIQUE INDEX labels_capture_client_uuid ON labels (capture_id, client_uuid)',
    'CREATE UNIQUE INDEX media_capture_client_uuid ON media (capture_id, client_uuid)',
    'CREATE UNIQUE INDEX observations_capture_client_uuid ON observations (capture_id, client_uuid)',
    'CREATE UNIQUE INDEX sightings_capture_client_uuid ON sightings (capture_id, client_uuid)',
]

# (column, declaration) per table, for bringing an older database up to the
# floor. Declarations are nullable or defaulted throughout — SQLite cannot add a
# NOT NULL column to a populated table, and none of these ever were.
COLUMNS = {
    'analysis_jobs': [
        ('id', 'INTEGER'),
        ('capture_id', 'INTEGER'),
        ('media_id', 'INTEGER'),
        ('state', 'TEXT'),
        ('claimed_at', 'TEXT'),
        ('finished_at', 'TEXT'),
        ('error', 'TEXT'),
        ('created_at', 'TEXT'),
    ],
    'analysis_results': [
        ('id', 'INTEGER'),
        ('job_id', 'INTEGER'),
        ('capture_id', 'INTEGER'),
        ('duration', 'REAL'),
        ('waveform_json', 'TEXT'),
        ('reliability_json', 'TEXT'),
        ('model_version', 'TEXT'),
        ('created_at', 'TEXT'),
    ],
    'captures': [
        ('id', 'INTEGER'),
        ('device_id', 'INTEGER'),
        ('client_uuid', 'TEXT'),
        ('latitude', 'REAL'),
        ('longitude', 'REAL'),
        ('location_name', 'TEXT'),
        ('recorded_at', 'TEXT'),
        ('duration_sec', 'REAL'),
        ('notes', 'TEXT'),
        ('family_id', 'INTEGER'),
        ('status', 'TEXT'),
        ('created_at', 'TEXT'),
        ('name', 'TEXT'),
        ('keep', 'INTEGER'),
        ('app_version', 'INTEGER'),
        ('app_commit', 'TEXT'),
        ('observer_role', 'TEXT'),
        ('silent_confirmed_at', 'TEXT'),
        ('behavior_guess', 'TEXT'),
        ('crop_start_sec', 'REAL'),
        ('crop_end_sec', 'REAL'),
        ('contributor_id', 'INTEGER'),
    ],
    'config_versions': [
        ('id', 'INTEGER'),
        ('version', 'INTEGER'),
        ('published_at', 'TEXT'),
        ('notes', 'TEXT'),
    ],
    'context_defs': [
        ('id', 'INTEGER'),
        ('key', 'TEXT'),
        ('category', 'TEXT'),
        ('sort_order', 'INTEGER'),
        ('active', 'INTEGER'),
        ('version_introduced', 'INTEGER'),
    ],
    'context_events': [
        ('id', 'INTEGER'),
        ('capture_id', 'INTEGER'),
        ('label_id', 'INTEGER'),
        ('device_id', 'INTEGER'),
        ('client_uuid', 'TEXT'),
        ('key', 'TEXT'),
        ('start_sec', 'REAL'),
        ('end_sec', 'REAL'),
        ('notes', 'TEXT'),
        ('created_at', 'TEXT'),
        ('contributor_id', 'INTEGER'),
    ],
    'contributors': [
        ('id', 'INTEGER'),
        ('public_uuid', 'TEXT'),
        ('display_name', 'TEXT'),
        ('role', 'TEXT'),
        ('status', 'TEXT'),
        ('claim_code_hash', 'TEXT'),
        ('created_at', 'TEXT'),
    ],
    'detected_calls': [
        ('id', 'INTEGER'),
        ('analysis_id', 'INTEGER'),
        ('start_sec', 'REAL'),
        ('end_sec', 'REAL'),
        ('species', 'TEXT'),
        ('scientific_name', 'TEXT'),
        ('call_type', 'TEXT'),
        ('confidence', 'REAL'),
        ('crow_conf', 'REAL'),
    ],
    'devices': [
        ('id', 'INTEGER'),
        ('device_uuid', 'TEXT'),
        ('token_hash', 'TEXT'),
        ('locale', 'TEXT'),
        ('platform', 'TEXT'),
        ('created_at', 'TEXT'),
        ('last_seen_at', 'TEXT'),
        ('contributor_id', 'INTEGER'),
        ('label', 'TEXT'),
        ('revoked_at', 'TEXT'),
        ('app_version', 'INTEGER'),
        ('app_commit', 'TEXT'),
    ],
    'families': [
        ('id', 'INTEGER'),
        ('device_id', 'INTEGER'),
        ('client_uuid', 'TEXT'),
        ('name', 'TEXT'),
        ('color', 'TEXT'),
        ('notes', 'TEXT'),
        ('created_at', 'TEXT'),
        ('contributor_id', 'INTEGER'),
    ],
    'instructions': [
        ('id', 'INTEGER'),
        ('key', 'TEXT'),
        ('sort_order', 'INTEGER'),
        ('active', 'INTEGER'),
        ('version_introduced', 'INTEGER'),
    ],
    'label_defs': [
        ('id', 'INTEGER'),
        ('key', 'TEXT'),
        ('core_mapping', 'TEXT'),
        ('color', 'TEXT'),
        ('sort_order', 'INTEGER'),
        ('active', 'INTEGER'),
        ('version_introduced', 'INTEGER'),
        ('trains', 'INTEGER'),
    ],
    'labels': [
        ('id', 'INTEGER'),
        ('capture_id', 'INTEGER'),
        ('media_id', 'INTEGER'),
        ('device_id', 'INTEGER'),
        ('start_sec', 'REAL'),
        ('end_sec', 'REAL'),
        ('species', 'TEXT'),
        ('call_type', 'TEXT'),
        ('label_source', 'TEXT'),
        ('notes', 'TEXT'),
        ('created_at', 'TEXT'),
        ('contributor_id', 'INTEGER'),
        ('client_uuid', 'TEXT'),
    ],
    'media': [
        ('id', 'INTEGER'),
        ('capture_id', 'INTEGER'),
        ('client_uuid', 'TEXT'),
        ('kind', 'TEXT'),
        ('storage', 'TEXT'),
        ('storage_ref', 'TEXT'),
        ('format', 'TEXT'),
        ('sample_rate', 'INTEGER'),
        ('channels', 'INTEGER'),
        ('bytes', 'INTEGER'),
        ('sha256', 'TEXT'),
        ('upload_state', 'TEXT'),
        ('uploaded_at', 'TEXT'),
        ('created_at', 'TEXT'),
        ('input_device', 'TEXT'),
        ('input_honoured', 'INTEGER'),
        ('pre_roll_sec', 'REAL'),
    ],
    'observations': [
        ('id', 'INTEGER'),
        ('capture_id', 'INTEGER'),
        ('device_id', 'INTEGER'),
        ('client_uuid', 'TEXT'),
        ('body', 'TEXT'),
        ('source', 'TEXT'),
        ('locale', 'TEXT'),
        ('created_at', 'TEXT'),
        ('updated_at', 'TEXT'),
        ('contributor_id', 'INTEGER'),
    ],
    'observer_roles': [
        ('id', 'INTEGER'),
        ('key', 'TEXT'),
        ('sort_order', 'INTEGER'),
        ('active', 'INTEGER'),
        ('version_introduced', 'INTEGER'),
    ],
    'sightings': [
        ('id', 'INTEGER'),
        ('capture_id', 'INTEGER'),
        ('device_id', 'INTEGER'),
        ('client_uuid', 'TEXT'),
        ('key', 'TEXT'),
        ('offset_sec', 'REAL'),
        ('distance_m', 'REAL'),
        ('notes', 'TEXT'),
        ('created_at', 'TEXT'),
        ('contributor_id', 'INTEGER'),
    ],
    'taxonomy': [
        ('id', 'INTEGER'),
        ('common_name', 'TEXT'),
        ('scientific_name', 'TEXT'),
        ('slug', 'TEXT'),
        ('has_head', 'INTEGER'),
        ('active', 'INTEGER'),
    ],
    'translations': [
        ('id', 'INTEGER'),
        ('namespace', 'TEXT'),
        ('key', 'TEXT'),
        ('locale', 'TEXT'),
        ('text', 'TEXT'),
    ],
}


def upgrade() -> None:
    bind = op.get_bind()
    before = set(sa.inspect(bind).get_table_names())

    for name, ddl in TABLES:
        if name not in before:
            op.execute(ddl)

    # Only tables that predated this run. One just created from the DDL above
    # already has every column, and asking again earns "duplicate column name".
    inspector = sa.inspect(bind)
    for name, wanted in COLUMNS.items():
        if name not in before:
            continue
        have = {c["name"] for c in inspector.get_columns(name)}
        for column, decl in wanted:
            if column and column not in have:
                op.execute(f"ALTER TABLE {name} ADD COLUMN {column} {decl or 'TEXT'}")

    for ddl in INDEXES:
        op.execute(ddl.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ", 1)
                      .replace("CREATE UNIQUE INDEX ", "CREATE UNIQUE INDEX IF NOT EXISTS ", 1))


def downgrade() -> None:
    raise NotImplementedError("the baseline is the floor")
