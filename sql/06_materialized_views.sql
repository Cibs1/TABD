-- Materialized view: full result summary cached on disk for fast frontend queries.
-- Refreshed at end of ETL via dw.refresh_from_operational().
CREATE MATERIALIZED VIEW IF NOT EXISTS election.mv_result_summary AS
SELECT *
FROM election.v_result_summary
WITH DATA;

CREATE UNIQUE INDEX mv_result_summary_pk_idx
    ON election.mv_result_summary (election_code, territory_code, organ_code, candidacy_id);

CREATE INDEX mv_result_summary_territory_idx
    ON election.mv_result_summary (territory_code, organ_code, election_code);

CREATE INDEX mv_result_summary_sigla_idx
    ON election.mv_result_summary (sigla, election_code, organ_code);

-- Materialized view: national party totals per organ for CM (used by frontend charts).
CREATE MATERIALIZED VIEW IF NOT EXISTS election.mv_national_totals AS
SELECT
    election_code,
    organ_code,
    sigla,
    candidate_type,
    SUM(votes) AS total_votes,
    SUM(mandates) AS total_mandates,
    round(
        SUM(votes)::numeric / NULLIF(SUM(SUM(votes)) OVER (PARTITION BY election_code, organ_code), 0) * 100,
        2
    ) AS national_vote_share
FROM election.mv_result_summary
WHERE territory_level = 'municipality'
GROUP BY election_code, organ_code, sigla, candidate_type
WITH DATA;

CREATE UNIQUE INDEX mv_national_totals_pk_idx
    ON election.mv_national_totals (election_code, organ_code, sigla);

CREATE INDEX mv_national_totals_votes_idx
    ON election.mv_national_totals (election_code, organ_code, total_votes DESC);

-- Materialized view: territory winners (one row per election/territory/organ).
-- Avoids re-running the ranking window function on every map render.
CREATE MATERIALIZED VIEW IF NOT EXISTS election.mv_territory_winners AS
SELECT *
FROM election.v_territory_winners
WITH DATA;

CREATE UNIQUE INDEX mv_territory_winners_pk_idx
    ON election.mv_territory_winners (election_code, territory_code, organ_code);

CREATE INDEX mv_territory_winners_territory_idx
    ON election.mv_territory_winners (territory_code, organ_code);
