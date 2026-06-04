-- Historical comparison queries for Autarquicas 2013, 2017, 2021, and 2025.
-- Run after loading AL2013, AL2017, AL2021, and AL2025.

-- 1. Confirm loaded elections and fact sizes.
SELECT
    e.election_code,
    e.election_date,
    COUNT(vr.*) AS vote_result_rows
FROM election.elections e
LEFT JOIN election.vote_results vr
  ON vr.election_id = e.election_id
GROUP BY e.election_code, e.election_date
ORDER BY e.election_date;

-- 2. Municipality turnout trend for the municipal council election.
SELECT
    t.territory_code,
    t.territory_name,
    MAX(trn.turnout_rate) FILTER (WHERE e.election_code = 'AL2013') AS turnout_2013,
    MAX(trn.turnout_rate) FILTER (WHERE e.election_code = 'AL2017') AS turnout_2017,
    MAX(trn.turnout_rate) FILTER (WHERE e.election_code = 'AL2021') AS turnout_2021,
    MAX(trn.turnout_rate) FILTER (WHERE e.election_code = 'AL2025') AS turnout_2025,
    MAX(trn.turnout_rate) FILTER (WHERE e.election_code = 'AL2025')
      - MAX(trn.turnout_rate) FILTER (WHERE e.election_code = 'AL2013') AS turnout_change_2013_2025
FROM election.turnout_results tr
JOIN election.elections e
  ON e.election_id = tr.election_id
JOIN election.territories t
  ON t.territory_code = tr.territory_code
CROSS JOIN LATERAL (
    SELECT
        CASE
            WHEN tr.voters = 0 THEN NULL
            ELSE election.turnout_rate(tr.voters, tr.registered_voters)
        END AS turnout_rate
) trn
WHERE tr.organ_code = 'CM'
  AND t.territory_level = 'municipality'
  AND e.election_code IN ('AL2013', 'AL2017', 'AL2021', 'AL2025')
GROUP BY t.territory_code, t.territory_name
ORDER BY ABS(
    MAX(trn.turnout_rate) FILTER (WHERE e.election_code = 'AL2025')
      - MAX(trn.turnout_rate) FILTER (WHERE e.election_code = 'AL2013')
) DESC NULLS LAST
LIMIT 30;

-- 3. National municipal-council vote-share trend by political family.
WITH family_results AS (
    SELECT
        election_code,
        CASE
            WHEN sigla = 'PS' OR sigla LIKE 'PS.%' THEN 'PS'
            WHEN sigla LIKE 'PPD/PSD%' THEN 'PPD/PSD and coalitions'
            WHEN sigla IN ('PCP-PEV', 'CDU') THEN 'CDU'
            WHEN sigla IN ('B.E.', 'BE') THEN 'BE'
            WHEN sigla = 'CH' THEN 'CH'
            WHEN sigla = 'IL' THEN 'IL'
            WHEN sigla = 'PAN' THEN 'PAN'
            ELSE 'Other'
        END AS political_family,
        SUM(votes) AS votes
    FROM election.mv_result_summary
    WHERE organ_code = 'CM'
      AND territory_level = 'municipality'
      AND election_code IN ('AL2013', 'AL2017', 'AL2021', 'AL2025')
    GROUP BY election_code, political_family
)
SELECT
    election_code,
    political_family,
    votes,
    ROUND(votes::numeric / SUM(votes) OVER (PARTITION BY election_code) * 100, 2) AS vote_share
FROM family_results
ORDER BY election_code, vote_share DESC;

-- 4. Municipalities where the winning list changed between elections.
WITH winners AS (
    SELECT
        election_code,
        territory_code,
        territory_name,
        sigla AS winner,
        vote_share
    FROM election.mv_territory_winners
    WHERE organ_code = 'CM'
      AND territory_level = 'municipality'
      AND election_code IN ('AL2013', 'AL2017', 'AL2021', 'AL2025')
)
SELECT
    COALESCE(w13.territory_code, w17.territory_code, w21.territory_code, w25.territory_code) AS territory_code,
    COALESCE(w13.territory_name, w17.territory_name, w21.territory_name, w25.territory_name) AS territory_name,
    w13.winner AS winner_2013,
    w17.winner AS winner_2017,
    w21.winner AS winner_2021,
    w25.winner AS winner_2025,
    w13.vote_share AS share_2013,
    w17.vote_share AS share_2017,
    w21.vote_share AS share_2021,
    w25.vote_share AS share_2025
FROM winners w13
FULL JOIN winners w17
  ON w17.territory_code = w13.territory_code
 AND w17.election_code = 'AL2017'
FULL JOIN winners w21
  ON w21.territory_code = COALESCE(w13.territory_code, w17.territory_code)
 AND w21.election_code = 'AL2021'
FULL JOIN winners w25
  ON w25.territory_code = COALESCE(w13.territory_code, w17.territory_code, w21.territory_code)
 AND w25.election_code = 'AL2025'
WHERE w13.election_code = 'AL2013'
  AND (
      w13.winner IS DISTINCT FROM w17.winner
      OR w17.winner IS DISTINCT FROM w21.winner
      OR w21.winner IS DISTINCT FROM w25.winner
  )
ORDER BY territory_name;

-- 5. Seat changes for the largest national families.
WITH family_seats AS (
    SELECT
        election_code,
        CASE
            WHEN sigla = 'PS' OR sigla LIKE 'PS.%' THEN 'PS'
            WHEN sigla LIKE 'PPD/PSD%' THEN 'PPD/PSD and coalitions'
            WHEN sigla IN ('PCP-PEV', 'CDU') THEN 'CDU'
            WHEN sigla IN ('B.E.', 'BE') THEN 'BE'
            WHEN sigla = 'CH' THEN 'CH'
            WHEN sigla = 'IL' THEN 'IL'
            WHEN sigla = 'PAN' THEN 'PAN'
            ELSE 'Other'
        END AS political_family,
        SUM(mandates) AS seats
    FROM election.mv_result_summary
    WHERE organ_code = 'CM'
      AND territory_level = 'municipality'
      AND election_code IN ('AL2013', 'AL2017', 'AL2021', 'AL2025')
    GROUP BY election_code, political_family
)
SELECT
    political_family,
    MAX(seats) FILTER (WHERE election_code = 'AL2013') AS seats_2013,
    MAX(seats) FILTER (WHERE election_code = 'AL2017') AS seats_2017,
    MAX(seats) FILTER (WHERE election_code = 'AL2021') AS seats_2021,
    MAX(seats) FILTER (WHERE election_code = 'AL2025') AS seats_2025,
    MAX(seats) FILTER (WHERE election_code = 'AL2025')
      - MAX(seats) FILTER (WHERE election_code = 'AL2013') AS seat_change_2013_2025
FROM family_seats
GROUP BY political_family
ORDER BY seats_2025 DESC NULLS LAST;
