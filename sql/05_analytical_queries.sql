-- D'Hondt validation for one municipality/organ.
-- Example: Agueda CM has 7 mandates.
SELECT *
FROM election.dhondt_allocate('010100', 'CM', 7);

-- Window function 1: ranking of parties/candidacies inside each municipality for CM.
SELECT
    territory_code,
    territory_name,
    sigla,
    votes,
    vote_share,
    rank() OVER (
        PARTITION BY territory_code, organ_code
        ORDER BY votes DESC, sigla
    ) AS local_rank
FROM election.v_result_summary
WHERE organ_code = 'CM'
  AND territory_level = 'municipality'
ORDER BY territory_code, local_rank;

-- Window function 2: national municipality-level vote totals and share by candidacy sigla.
SELECT
    sigla,
    SUM(votes) AS total_votes,
    round(
        SUM(votes)::numeric
        / SUM(SUM(votes)) OVER ()::numeric
        * 100,
        2
    ) AS national_vote_share
FROM election.v_result_summary
WHERE organ_code = 'CM'
  AND territory_level = 'municipality'
GROUP BY sigla
ORDER BY total_votes DESC;

-- Window function 3: turnout ranking by district and municipality.
SELECT
    district.territory_name AS district_name,
    municipality.territory_name AS municipality_name,
    summary.turnout_rate,
    dense_rank() OVER (
        PARTITION BY district.territory_code
        ORDER BY summary.turnout_rate DESC
    ) AS turnout_rank_in_district
FROM election.turnout_results turnout
JOIN election.territories municipality
  ON municipality.territory_code = turnout.territory_code
JOIN election.territories district
  ON district.territory_code = municipality.district_code
JOIN election.elections USING (election_id)
CROSS JOIN LATERAL (
    SELECT election.turnout_rate(turnout.voters, turnout.registered_voters) AS turnout_rate
) summary
WHERE elections.election_code = 'AL2021'
  AND turnout.organ_code = 'CM'
  AND municipality.territory_level = 'municipality'
ORDER BY district_name, turnout_rank_in_district, municipality_name;

-- GROUP BY ROLLUP: votes by district and candidate, plus district and global totals.
SELECT
    district.territory_name AS district_name,
    results.sigla,
    SUM(results.votes) AS votes
FROM election.v_result_summary results
JOIN election.territories municipality
  ON municipality.territory_code = results.territory_code
JOIN election.territories district
  ON district.territory_code = municipality.district_code
WHERE results.organ_code = 'CM'
  AND results.territory_level = 'municipality'
GROUP BY ROLLUP (district.territory_name, results.sigla)
ORDER BY district_name NULLS LAST, votes DESC;

-- GROUP BY CUBE: compare candidate type and district, including all subtotals.
SELECT
    district.territory_name AS district_name,
    results.candidate_type,
    SUM(results.votes) AS votes,
    SUM(results.mandates) AS mandates
FROM election.v_result_summary results
JOIN election.territories municipality
  ON municipality.territory_code = results.territory_code
JOIN election.territories district
  ON district.territory_code = municipality.district_code
WHERE results.organ_code = 'CM'
  AND results.territory_level = 'municipality'
GROUP BY CUBE (district.territory_name, results.candidate_type)
ORDER BY district_name NULLS LAST, candidate_type NULLS LAST;

-- Advanced aggregates: winners per district as JSON plus FILTER counts.
SELECT
    district.territory_name AS district_name,
    COUNT(*) FILTER (WHERE winners.candidate_type = 'party') AS party_wins,
    COUNT(*) FILTER (WHERE winners.candidate_type = 'coalition') AS coalition_wins,
    COUNT(*) FILTER (WHERE winners.candidate_type = 'citizen_group') AS citizen_group_wins,
    jsonb_agg(
        jsonb_build_object(
            'municipality', municipality.territory_name,
            'winner', winners.sigla,
            'votes', winners.votes,
            'share', winners.vote_share
        )
        ORDER BY municipality.territory_name
    ) AS municipality_winners
FROM election.v_territory_winners winners
JOIN election.territories municipality
  ON municipality.territory_code = winners.territory_code
JOIN election.territories district
  ON district.territory_code = municipality.district_code
WHERE winners.organ_code = 'CM'
  AND winners.territory_level = 'municipality'
GROUP BY district.territory_name
ORDER BY district.territory_name;
