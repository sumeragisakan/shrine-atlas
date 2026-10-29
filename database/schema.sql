PRAGMA foreign_keys = ON;

CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;

CREATE TABLE prefectures (
    code INTEGER PRIMARY KEY CHECK (code BETWEEN 1 AND 47),
    name_ja TEXT NOT NULL
) STRICT;

CREATE TABLE shrines (
    id TEXT PRIMARY KEY,
    prefecture_code INTEGER NOT NULL REFERENCES prefectures(code),
    display_order INTEGER NOT NULL,
    name_ja TEXT NOT NULL,
    kana TEXT NOT NULL,
    area TEXT NOT NULL,
    municipality TEXT NOT NULL,
    headline TEXT NOT NULL,
    introduction TEXT NOT NULL,
    research_note TEXT NOT NULL,
    checked_at TEXT NOT NULL
) STRICT;

CREATE TABLE aliases (
    shrine_id TEXT NOT NULL REFERENCES shrines(id),
    ordinal INTEGER NOT NULL,
    alias TEXT NOT NULL,
    PRIMARY KEY (shrine_id, ordinal)
) STRICT;

CREATE TABLE tags (
    shrine_id TEXT NOT NULL REFERENCES shrines(id),
    ordinal INTEGER NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (shrine_id, ordinal)
) STRICT;

CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL UNIQUE CHECK (url LIKE 'https://%'),
    label TEXT NOT NULL,
    kind TEXT NOT NULL,
    covers TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    published_at TEXT
) STRICT;

-- Ordinals preserve the [1], [2], ... citation numbering within each shrine.
CREATE TABLE shrine_sources (
    shrine_id TEXT NOT NULL REFERENCES shrines(id),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    source_id TEXT NOT NULL REFERENCES sources(id),
    PRIMARY KEY (shrine_id, ordinal),
    UNIQUE (shrine_id, source_id)
) STRICT;

CREATE TABLE locations (
    id TEXT PRIMARY KEY,
    shrine_id TEXT NOT NULL REFERENCES shrines(id),
    ordinal INTEGER NOT NULL,
    name TEXT NOT NULL,
    label TEXT NOT NULL,
    address_ja TEXT NOT NULL,
    latitude REAL CHECK (latitude BETWEEN -90 AND 90),
    longitude REAL CHECK (longitude BETWEEN -180 AND 180),
    precision_note TEXT NOT NULL,
    map_status TEXT NOT NULL CHECK (map_status IN ('mapped','not_published','outside_prefecture_needs_review')),
    CHECK ((latitude IS NULL) = (longitude IS NULL)),
    CHECK (map_status != 'mapped' OR latitude IS NOT NULL),
    UNIQUE (shrine_id, ordinal),
    UNIQUE (id, shrine_id)
) STRICT;

CREATE TABLE directory_entries (
    shrine_id TEXT PRIMARY KEY REFERENCES shrines(id),
    directory_number INTEGER NOT NULL UNIQUE,
    index_name TEXT NOT NULL,
    index_url TEXT NOT NULL,
    listed_address TEXT NOT NULL,
    original_detail_url TEXT,
    detail_url TEXT,
    detail_status TEXT NOT NULL,
    source_sha256 TEXT,
    checked_at TEXT NOT NULL
) STRICT;

CREATE TABLE record_quality (
    shrine_id TEXT PRIMARY KEY REFERENCES shrines(id),
    record_status TEXT NOT NULL,
    kami_availability TEXT NOT NULL,
    history_availability TEXT NOT NULL,
    kami_verbatim TEXT NOT NULL,
    former_rank TEXT NOT NULL
) STRICT;

CREATE TABLE entity_registry (
    shrine_id TEXT PRIMARY KEY REFERENCES shrines(id),
    corporate_number TEXT NOT NULL,
    state TEXT NOT NULL,
    closed_date TEXT,
    registered_address TEXT,
    source_id TEXT NOT NULL REFERENCES sources(id)
) STRICT;

CREATE TABLE location_sources (
    location_id TEXT NOT NULL REFERENCES locations(id),
    source_id TEXT NOT NULL REFERENCES sources(id),
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (location_id, source_id)
) STRICT;

-- A group is a source's textual list, NOT a harmonized list of deity identities.
-- Conflicting lists are separate rows, e.g. the two Akaiiwa Shrine lists.
CREATE TABLE deity_groups (
    id TEXT PRIMARY KEY,
    shrine_id TEXT NOT NULL REFERENCES shrines(id),
    ordinal INTEGER NOT NULL,
    role_text TEXT NOT NULL,
    UNIQUE (shrine_id, ordinal)
) STRICT;

CREATE TABLE deity_mentions (
    group_id TEXT NOT NULL REFERENCES deity_groups(id),
    ordinal INTEGER NOT NULL,
    name_verbatim TEXT NOT NULL,
    PRIMARY KEY (group_id, ordinal)
) STRICT;

CREATE TABLE deity_group_sources (
    group_id TEXT NOT NULL REFERENCES deity_groups(id),
    source_id TEXT NOT NULL REFERENCES sources(id),
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (group_id, source_id)
) STRICT;

CREATE TABLE historical_notes (
    id TEXT PRIMARY KEY,
    shrine_id TEXT NOT NULL REFERENCES shrines(id),
    ordinal INTEGER NOT NULL,
    label TEXT NOT NULL,
    text TEXT NOT NULL,
    nature TEXT NOT NULL,
    UNIQUE (shrine_id, ordinal)
) STRICT;

CREATE TABLE historical_note_sources (
    note_id TEXT NOT NULL REFERENCES historical_notes(id),
    source_id TEXT NOT NULL REFERENCES sources(id),
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (note_id, source_id)
) STRICT;

CREATE TABLE research_note_sources (
    shrine_id TEXT NOT NULL REFERENCES shrines(id),
    source_id TEXT NOT NULL REFERENCES sources(id),
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (shrine_id, source_id)
) STRICT;

-- Media bytes remain in media/ or a future object store; the DB stores metadata.
CREATE TABLE media_assets (
    id TEXT PRIMARY KEY,
    shrine_id TEXT NOT NULL REFERENCES shrines(id),
    location_id TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('image', 'model')),
    path TEXT NOT NULL,
    caption TEXT NOT NULL,
    source_url TEXT NOT NULL,
    creator TEXT NOT NULL,
    license TEXT NOT NULL,
    license_url TEXT,
    sha256 TEXT,
    checked_at TEXT NOT NULL,
    FOREIGN KEY (location_id, shrine_id) REFERENCES locations(id, shrine_id)
) STRICT;

CREATE INDEX shrines_by_prefecture ON shrines(prefecture_code, display_order);
CREATE INDEX locations_by_shrine ON locations(shrine_id);
CREATE INDEX deity_mentions_by_name ON deity_mentions(name_verbatim);
CREATE INDEX media_by_shrine ON media_assets(shrine_id);

CREATE VIEW deity_occurrences AS
SELECT s.id AS shrine_id, s.name_ja AS shrine_name,
       s.prefecture_code, g.id AS group_id, g.role_text,
       m.ordinal, m.name_verbatim
FROM shrines s
JOIN deity_groups g ON g.shrine_id = s.id
JOIN deity_mentions m ON m.group_id = g.id;
