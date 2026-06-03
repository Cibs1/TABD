CREATE TABLE election.elections (
    election_id bigserial PRIMARY KEY,
    election_code text NOT NULL UNIQUE,
    election_name text NOT NULL,
    election_date date,
    source_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE election.organs (
    organ_code text PRIMARY KEY,
    organ_name text NOT NULL,
    territory_level text NOT NULL CHECK (territory_level IN ('municipality', 'parish'))
);

CREATE TABLE election.territories (
    territory_code text PRIMARY KEY,
    territory_name text NOT NULL,
    territory_level text NOT NULL CHECK (territory_level IN ('district', 'municipality', 'parish')),
    parent_code text REFERENCES election.territories (territory_code),
    district_code text,
    municipality_code text,
    geom geometry(MultiPolygon, 3763),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE election.candidacies (
    candidacy_id bigserial PRIMARY KEY,
    election_id bigint NOT NULL REFERENCES election.elections (election_id) ON DELETE CASCADE,
    organ_code text NOT NULL REFERENCES election.organs (organ_code),
    territory_code text NOT NULL REFERENCES election.territories (territory_code),
    source_candidate_ref text NOT NULL,
    candidate_type text NOT NULL CHECK (candidate_type IN ('party', 'coalition', 'citizen_group')),
    sigla text NOT NULL,
    name text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (election_id, organ_code, territory_code, source_candidate_ref)
);

CREATE TABLE election.turnout_results (
    turnout_id bigserial PRIMARY KEY,
    election_id bigint NOT NULL REFERENCES election.elections (election_id) ON DELETE CASCADE,
    territory_code text NOT NULL REFERENCES election.territories (territory_code),
    organ_code text NOT NULL REFERENCES election.organs (organ_code),
    registered_voters integer NOT NULL,
    voters integer NOT NULL,
    blank_votes integer NOT NULL,
    null_votes integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (election_id, territory_code, organ_code)
);

CREATE TABLE election.vote_results (
    vote_result_id bigserial PRIMARY KEY,
    election_id bigint NOT NULL REFERENCES election.elections (election_id) ON DELETE CASCADE,
    territory_code text NOT NULL REFERENCES election.territories (territory_code),
    organ_code text NOT NULL REFERENCES election.organs (organ_code),
    candidacy_id bigint NOT NULL REFERENCES election.candidacies (candidacy_id) ON DELETE CASCADE,
    votes integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (election_id, territory_code, organ_code, candidacy_id)
);

CREATE TABLE election.seat_results (
    seat_result_id bigserial PRIMARY KEY,
    election_id bigint NOT NULL REFERENCES election.elections (election_id) ON DELETE CASCADE,
    territory_code text NOT NULL REFERENCES election.territories (territory_code),
    organ_code text NOT NULL REFERENCES election.organs (organ_code),
    candidacy_id bigint NOT NULL REFERENCES election.candidacies (candidacy_id) ON DELETE CASCADE,
    vote_percent numeric(8, 2),
    mandates integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (election_id, territory_code, organ_code, candidacy_id)
);

CREATE INDEX territories_parent_idx
    ON election.territories (parent_code);

CREATE INDEX territories_level_idx
    ON election.territories (territory_level);

CREATE INDEX territories_geom_gix
    ON election.territories USING gist (geom);

CREATE INDEX candidacies_lookup_idx
    ON election.candidacies (election_id, organ_code, territory_code, sigla);

CREATE INDEX vote_results_lookup_idx
    ON election.vote_results (election_id, territory_code, organ_code, votes DESC);

CREATE INDEX seat_results_lookup_idx
    ON election.seat_results (election_id, territory_code, organ_code, mandates DESC);

CREATE TABLE election.elected_members (
    elected_member_id bigserial PRIMARY KEY,
    election_id bigint NOT NULL REFERENCES election.elections (election_id) ON DELETE CASCADE,
    territory_code text NOT NULL REFERENCES election.territories (territory_code),
    organ_code text NOT NULL REFERENCES election.organs (organ_code),
    candidacy_id bigint NOT NULL REFERENCES election.candidacies (candidacy_id) ON DELETE CASCADE,
    list_position integer NOT NULL CHECK (list_position > 0),
    member_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (election_id, territory_code, organ_code, candidacy_id, list_position)
);

CREATE INDEX elected_members_lookup_idx
    ON election.elected_members (election_id, territory_code, organ_code, candidacy_id);
