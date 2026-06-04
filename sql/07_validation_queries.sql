-- Row-count validation after running:
--   python3 etl/load_cne_2021.py --setup

SELECT 'staging.cne_result_rows' AS table_name, count(*) AS row_count
FROM staging.cne_result_rows
UNION ALL
SELECT 'staging.cne_candidate_aliases', count(*)
FROM staging.cne_candidate_aliases
UNION ALL
SELECT 'staging.cne_candidate_votes', count(*)
FROM staging.cne_candidate_votes
UNION ALL
SELECT 'staging.cne_percent_mandates', count(*)
FROM staging.cne_percent_mandates
UNION ALL
SELECT 'staging.cne_elected_members', count(*)
FROM staging.cne_elected_members
UNION ALL
SELECT 'election.turnout_results', count(*)
FROM election.turnout_results
UNION ALL
SELECT 'election.vote_results', count(*)
FROM election.vote_results
UNION ALL
SELECT 'election.seat_results', count(*)
FROM election.seat_results
UNION ALL
SELECT 'election.elected_members', count(*)
FROM election.elected_members
UNION ALL
SELECT 'dw.fact_election_results', count(*)
FROM dw.fact_election_results;

-- Known municipality check: Agueda, Camara Municipal.
SELECT sigla, votes, vote_share, mandates
FROM election.mv_result_summary
WHERE territory_code = '010100'
  AND organ_code = 'CM'
  AND election_code = 'AL2021'
ORDER BY votes DESC;

-- D'Hondt allocation for Agueda CM. The total seats are 7.
SELECT *
FROM election.dhondt_allocate('010100', 'CM', 7);

-- Compare calculated D'Hondt seats against official mandates.
WITH calculated AS (
    SELECT sigla, count(*) AS calculated_mandates
    FROM election.dhondt_allocate('010100', 'CM', 7)
    GROUP BY sigla
),
official AS (
    SELECT sigla, mandates AS official_mandates
    FROM election.mv_result_summary
    WHERE territory_code = '010100'
      AND organ_code = 'CM'
      AND election_code = 'AL2021'
)
SELECT
    COALESCE(official.sigla, calculated.sigla) AS sigla,
    COALESCE(official.official_mandates, 0) AS official_mandates,
    COALESCE(calculated.calculated_mandates, 0) AS calculated_mandates,
    COALESCE(official.official_mandates, 0) = COALESCE(calculated.calculated_mandates, 0) AS matches
FROM official
FULL OUTER JOIN calculated USING (sigla)
ORDER BY official_mandates DESC, calculated_mandates DESC, sigla;

-- Materialized-view sanity checks.
SELECT count(*) AS result_summary_rows
FROM election.mv_result_summary;

SELECT count(*) AS municipality_winners
FROM election.mv_territory_winners
WHERE organ_code = 'CM'
  AND territory_level = 'municipality';

SELECT sigla, total_votes, national_vote_share
FROM election.mv_national_totals
WHERE election_code = 'AL2021'
  AND organ_code = 'CM'
ORDER BY total_votes DESC
LIMIT 15;
