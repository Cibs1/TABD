CREATE TABLE staging.cne_result_rows (
    source_file text NOT NULL,
    source_row integer NOT NULL,
    election_code text NOT NULL,
    territory_code text NOT NULL,
    municipality_name text,
    parish_name text,
    organ_code text,
    registered_voters integer,
    voters integer,
    blank_votes integer,
    null_votes integer,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_file, source_row, election_code)
);

CREATE TABLE staging.cne_candidate_aliases (
    source_file text NOT NULL,
    source_row integer NOT NULL,
    election_code text NOT NULL,
    territory_code text NOT NULL,
    municipality_name text,
    parish_name text,
    organ_code text NOT NULL,
    candidate_ref text NOT NULL,
    candidate_group text NOT NULL,
    resolved_sigla text,
    resolved_name text,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_file, source_row, election_code, candidate_ref)
);

CREATE TABLE staging.cne_candidate_votes (
    source_file text NOT NULL,
    source_row integer NOT NULL,
    election_code text NOT NULL,
    territory_code text NOT NULL,
    organ_code text NOT NULL,
    candidate_ref text NOT NULL,
    candidate_group text NOT NULL,
    resolved_sigla text,
    resolved_name text,
    votes integer NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_file, source_row, election_code, candidate_ref)
);

CREATE TABLE staging.cne_percent_mandates (
    source_file text NOT NULL,
    source_row integer NOT NULL,
    election_code text NOT NULL,
    territory_code text NOT NULL,
    organ_code text NOT NULL,
    candidate_ref text NOT NULL,
    candidate_group text NOT NULL,
    resolved_sigla text,
    resolved_name text,
    vote_percent numeric(8, 2),
    mandates integer,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_file, source_row, election_code, candidate_ref)
);

CREATE INDEX cne_result_rows_territory_idx
    ON staging.cne_result_rows (territory_code, organ_code);

CREATE INDEX cne_candidate_votes_lookup_idx
    ON staging.cne_candidate_votes (election_code, territory_code, organ_code, candidate_ref);

CREATE INDEX cne_percent_mandates_lookup_idx
    ON staging.cne_percent_mandates (election_code, territory_code, organ_code, candidate_ref);

CREATE TABLE staging.cne_elected_members (
    source_file text NOT NULL,
    source_row integer NOT NULL,
    election_code text NOT NULL,
    territory_code text NOT NULL,
    municipality_name text,
    parish_name text,
    organ_code text NOT NULL,
    candidate_sigla text NOT NULL,
    list_position integer NOT NULL,
    member_name text NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_file, source_row, election_code, candidate_sigla)
);

CREATE INDEX cne_elected_members_lookup_idx
    ON staging.cne_elected_members (election_code, territory_code, organ_code, candidate_sigla);
