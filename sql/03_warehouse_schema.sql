CREATE TABLE dw.dim_election (
    election_key bigserial PRIMARY KEY,
    election_id bigint NOT NULL UNIQUE,
    election_code text NOT NULL,
    election_name text NOT NULL,
    election_date date
);

CREATE TABLE dw.dim_organ (
    organ_key bigserial PRIMARY KEY,
    organ_code text NOT NULL UNIQUE,
    organ_name text NOT NULL,
    territory_level text NOT NULL
);

CREATE TABLE dw.dim_territory (
    territory_key bigserial PRIMARY KEY,
    territory_code text NOT NULL UNIQUE,
    territory_name text NOT NULL,
    territory_level text NOT NULL,
    parent_code text,
    district_code text,
    municipality_code text
);

CREATE TABLE dw.dim_candidacy (
    candidacy_key bigserial PRIMARY KEY,
    candidacy_id bigint NOT NULL UNIQUE,
    election_code text NOT NULL,
    organ_code text NOT NULL,
    territory_code text NOT NULL,
    source_candidate_ref text NOT NULL,
    candidate_type text NOT NULL,
    sigla text NOT NULL,
    name text
);

CREATE TABLE dw.fact_election_results (
    election_key bigint NOT NULL REFERENCES dw.dim_election (election_key),
    organ_key bigint NOT NULL REFERENCES dw.dim_organ (organ_key),
    territory_key bigint NOT NULL REFERENCES dw.dim_territory (territory_key),
    candidacy_key bigint NOT NULL REFERENCES dw.dim_candidacy (candidacy_key),
    votes integer NOT NULL,
    vote_percent numeric(8, 2),
    mandates integer NOT NULL DEFAULT 0,
    registered_voters integer NOT NULL,
    voters integer NOT NULL,
    blank_votes integer NOT NULL,
    null_votes integer NOT NULL,
    PRIMARY KEY (election_key, organ_key, territory_key, candidacy_key)
);

CREATE INDEX fact_election_results_territory_idx
    ON dw.fact_election_results (territory_key, organ_key);

CREATE INDEX fact_election_results_votes_idx
    ON dw.fact_election_results (election_key, organ_key, territory_key, votes DESC);
