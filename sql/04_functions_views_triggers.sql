CREATE OR REPLACE FUNCTION election.vote_share(votes integer, valid_votes integer)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
RETURNS NULL ON NULL INPUT
AS $$
    SELECT CASE
        WHEN valid_votes = 0 THEN NULL
        ELSE round((votes::numeric / valid_votes::numeric) * 100, 2)
    END
$$;

CREATE OR REPLACE FUNCTION election.turnout_rate(voters integer, registered_voters integer)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
RETURNS NULL ON NULL INPUT
AS $$
    SELECT CASE
        WHEN registered_voters = 0 THEN NULL
        ELSE round((voters::numeric / registered_voters::numeric) * 100, 2)
    END
$$;

CREATE OR REPLACE FUNCTION election.assert_turnout_consistency()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.registered_voters < 0
        OR NEW.voters < 0
        OR NEW.blank_votes < 0
        OR NEW.null_votes < 0 THEN
        RAISE EXCEPTION 'Turnout values cannot be negative';
    END IF;

    IF NEW.blank_votes + NEW.null_votes > NEW.voters THEN
        RAISE EXCEPTION 'Blank plus null votes cannot exceed voters';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS turnout_consistency_trg ON election.turnout_results;
CREATE TRIGGER turnout_consistency_trg
BEFORE INSERT OR UPDATE ON election.turnout_results
FOR EACH ROW
EXECUTE FUNCTION election.assert_turnout_consistency();

CREATE OR REPLACE FUNCTION election.assert_vote_result_consistency()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    candidate_scope record;
BEGIN
    IF NEW.votes < 0 THEN
        RAISE EXCEPTION 'Votes cannot be negative';
    END IF;

    SELECT election_id, territory_code, organ_code
    INTO candidate_scope
    FROM election.candidacies
    WHERE candidacy_id = NEW.candidacy_id;

    IF candidate_scope.election_id IS NULL THEN
        RAISE EXCEPTION 'Unknown candidacy id %', NEW.candidacy_id;
    END IF;

    IF candidate_scope.election_id <> NEW.election_id
        OR candidate_scope.territory_code <> NEW.territory_code
        OR candidate_scope.organ_code <> NEW.organ_code THEN
        RAISE EXCEPTION 'Vote result scope does not match candidacy scope';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS vote_result_consistency_trg ON election.vote_results;
CREATE TRIGGER vote_result_consistency_trg
BEFORE INSERT OR UPDATE ON election.vote_results
FOR EACH ROW
EXECUTE FUNCTION election.assert_vote_result_consistency();

CREATE OR REPLACE FUNCTION election.assert_seat_result_consistency()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    candidate_scope record;
BEGIN
    IF NEW.mandates < 0 THEN
        RAISE EXCEPTION 'Mandates cannot be negative';
    END IF;

    SELECT election_id, territory_code, organ_code
    INTO candidate_scope
    FROM election.candidacies
    WHERE candidacy_id = NEW.candidacy_id;

    IF candidate_scope.election_id <> NEW.election_id
        OR candidate_scope.territory_code <> NEW.territory_code
        OR candidate_scope.organ_code <> NEW.organ_code THEN
        RAISE EXCEPTION 'Seat result scope does not match candidacy scope';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS seat_result_consistency_trg ON election.seat_results;
CREATE TRIGGER seat_result_consistency_trg
BEFORE INSERT OR UPDATE ON election.seat_results
FOR EACH ROW
EXECUTE FUNCTION election.assert_seat_result_consistency();

CREATE OR REPLACE PROCEDURE election.load_from_staging(
    p_election_code text DEFAULT 'AL2021',
    p_election_name text DEFAULT 'Eleições Autárquicas 2021',
    p_election_date date DEFAULT DATE '2021-09-26',
    p_source_name text DEFAULT 'CNE mapa oficial Autárquicas 2021'
)
LANGUAGE plpgsql
AS $$
DECLARE
    target_election_id bigint;
BEGIN
    DELETE FROM election.elections
    WHERE election_code = p_election_code;

    INSERT INTO election.elections (election_code, election_name, election_date, source_name)
    VALUES (p_election_code, p_election_name, p_election_date, p_source_name)
    RETURNING election_id INTO target_election_id;

    INSERT INTO election.organs (organ_code, organ_name, territory_level)
    VALUES
        ('CM', 'Câmara Municipal', 'municipality'),
        ('AM', 'Assembleia Municipal', 'municipality'),
        ('AF', 'Assembleia de Freguesia', 'parish')
    ON CONFLICT (organ_code) DO UPDATE
    SET organ_name = EXCLUDED.organ_name,
        territory_level = EXCLUDED.territory_level;

    INSERT INTO election.territories (
        territory_code,
        territory_name,
        territory_level,
        parent_code,
        district_code,
        municipality_code
    )
    WITH district_rows AS (
        SELECT
            CASE
                WHEN substring(territory_code from 1 for 2) IN ('31', '32') THEN '300000'
                WHEN substring(territory_code from 1 for 2) BETWEEN '41' AND '49' THEN '400000'
                ELSE substring(territory_code from 1 for 2) || '0000'
            END AS district_code,
            MIN(initcap(municipality_name)) AS district_name
        FROM staging.cne_result_rows
        WHERE organ_code IS NULL
          AND election_code = p_election_code
          AND municipality_name IS NOT NULL
        GROUP BY 1
    )
    SELECT
        district_code,
        district_name,
        'district',
        NULL,
        district_code,
        NULL
    FROM district_rows
    ON CONFLICT (territory_code) DO UPDATE
    SET territory_name = EXCLUDED.territory_name,
        territory_level = EXCLUDED.territory_level,
        parent_code = EXCLUDED.parent_code,
        district_code = EXCLUDED.district_code,
        municipality_code = EXCLUDED.municipality_code;

    INSERT INTO election.territories (
        territory_code,
        territory_name,
        territory_level,
        parent_code,
        district_code,
        municipality_code
    )
    SELECT DISTINCT
        territory_code,
        initcap(municipality_name),
        'municipality',
        CASE
            WHEN substring(territory_code from 1 for 2) IN ('31', '32') THEN '300000'
            WHEN substring(territory_code from 1 for 2) BETWEEN '41' AND '49' THEN '400000'
            ELSE substring(territory_code from 1 for 2) || '0000'
        END,
        CASE
            WHEN substring(territory_code from 1 for 2) IN ('31', '32') THEN '300000'
            WHEN substring(territory_code from 1 for 2) BETWEEN '41' AND '49' THEN '400000'
            ELSE substring(territory_code from 1 for 2) || '0000'
        END,
        territory_code
    FROM staging.cne_result_rows
    WHERE organ_code IN ('CM', 'AM')
      AND election_code = p_election_code
      AND municipality_name IS NOT NULL
    ON CONFLICT (territory_code) DO UPDATE
    SET territory_name = EXCLUDED.territory_name,
        territory_level = EXCLUDED.territory_level,
        parent_code = EXCLUDED.parent_code,
        district_code = EXCLUDED.district_code,
        municipality_code = EXCLUDED.municipality_code;

    INSERT INTO election.territories (
        territory_code,
        territory_name,
        territory_level,
        parent_code,
        district_code,
        municipality_code
    )
    SELECT DISTINCT
        territory_code,
        initcap(parish_name),
        'parish',
        substring(territory_code from 1 for 4) || '00',
        CASE
            WHEN substring(territory_code from 1 for 2) IN ('31', '32') THEN '300000'
            WHEN substring(territory_code from 1 for 2) BETWEEN '41' AND '49' THEN '400000'
            ELSE substring(territory_code from 1 for 2) || '0000'
        END,
        substring(territory_code from 1 for 4) || '00'
    FROM staging.cne_result_rows
    WHERE organ_code = 'AF'
      AND election_code = p_election_code
      AND parish_name IS NOT NULL
    ON CONFLICT (territory_code) DO UPDATE
    SET territory_name = EXCLUDED.territory_name,
        territory_level = EXCLUDED.territory_level,
        parent_code = EXCLUDED.parent_code,
        district_code = EXCLUDED.district_code,
        municipality_code = EXCLUDED.municipality_code;

    INSERT INTO election.turnout_results (
        election_id,
        territory_code,
        organ_code,
        registered_voters,
        voters,
        blank_votes,
        null_votes
    )
    SELECT
        target_election_id,
        territory_code,
        organ_code,
        COALESCE(registered_voters, 0),
        COALESCE(voters, 0),
        COALESCE(blank_votes, 0),
        COALESCE(null_votes, 0)
    FROM staging.cne_result_rows
    WHERE organ_code IN ('CM', 'AM', 'AF')
      AND election_code = p_election_code
    ON CONFLICT (election_id, territory_code, organ_code) DO UPDATE
    SET registered_voters = EXCLUDED.registered_voters,
        voters = EXCLUDED.voters,
        blank_votes = EXCLUDED.blank_votes,
        null_votes = EXCLUDED.null_votes;

    INSERT INTO election.candidacies (
        election_id,
        organ_code,
        territory_code,
        source_candidate_ref,
        candidate_type,
        sigla,
        name
    )
    SELECT DISTINCT
        target_election_id,
        organ_code,
        territory_code,
        candidate_ref,
        candidate_group,
        COALESCE(NULLIF(resolved_sigla, ''), candidate_ref),
        resolved_name
    FROM staging.cne_candidate_votes
    WHERE votes IS NOT NULL
      AND election_code = p_election_code
    ON CONFLICT (election_id, organ_code, territory_code, source_candidate_ref) DO UPDATE
    SET candidate_type = EXCLUDED.candidate_type,
        sigla = EXCLUDED.sigla,
        name = EXCLUDED.name;

    INSERT INTO election.vote_results (
        election_id,
        territory_code,
        organ_code,
        candidacy_id,
        votes
    )
    SELECT
        target_election_id,
        votes.territory_code,
        votes.organ_code,
        candidacies.candidacy_id,
        votes.votes
    FROM staging.cne_candidate_votes votes
    JOIN election.candidacies candidacies
      ON candidacies.election_id = target_election_id
     AND candidacies.organ_code = votes.organ_code
     AND candidacies.territory_code = votes.territory_code
     AND candidacies.source_candidate_ref = votes.candidate_ref
    WHERE votes.election_code = p_election_code
    ON CONFLICT (election_id, territory_code, organ_code, candidacy_id) DO UPDATE
    SET votes = EXCLUDED.votes;

    INSERT INTO election.seat_results (
        election_id,
        territory_code,
        organ_code,
        candidacy_id,
        vote_percent,
        mandates
    )
    SELECT
        target_election_id,
        mandates.territory_code,
        mandates.organ_code,
        candidacies.candidacy_id,
        mandates.vote_percent,
        COALESCE(mandates.mandates, 0)
    FROM staging.cne_percent_mandates mandates
    JOIN election.candidacies candidacies
      ON candidacies.election_id = target_election_id
     AND candidacies.organ_code = mandates.organ_code
     AND candidacies.territory_code = mandates.territory_code
     AND candidacies.source_candidate_ref = mandates.candidate_ref
    WHERE mandates.election_code = p_election_code
    ON CONFLICT (election_id, territory_code, organ_code, candidacy_id) DO UPDATE
    SET vote_percent = EXCLUDED.vote_percent,
        mandates = EXCLUDED.mandates;

    INSERT INTO election.elected_members (
        election_id,
        territory_code,
        organ_code,
        candidacy_id,
        list_position,
        member_name
    )
    SELECT
        target_election_id,
        em.territory_code,
        em.organ_code,
        c.candidacy_id,
        em.list_position,
        em.member_name
    FROM staging.cne_elected_members em
    JOIN election.candidacies c
      ON c.election_id = target_election_id
     AND c.territory_code = em.territory_code
     AND c.organ_code = em.organ_code
     AND c.sigla = em.candidate_sigla
    WHERE em.election_code = p_election_code
    ON CONFLICT (election_id, territory_code, organ_code, candidacy_id, list_position, member_name) DO UPDATE
    SET member_name = EXCLUDED.member_name;
END;
$$;

CREATE OR REPLACE FUNCTION election.dhondt_allocate(
    p_territory_code text,
    p_organ_code text,
    p_seats integer,
    p_election_code text DEFAULT 'AL2021'
)
RETURNS TABLE (
    seat_number integer,
    candidacy_id bigint,
    sigla text,
    votes integer,
    divisor integer,
    quotient numeric
)
LANGUAGE sql
STABLE
AS $$
    WITH candidate_votes AS (
        SELECT
            candidacies.candidacy_id,
            candidacies.sigla,
            vote_results.votes
        FROM election.vote_results
        JOIN election.candidacies USING (candidacy_id)
        JOIN election.elections ON elections.election_id = vote_results.election_id
        WHERE elections.election_code = p_election_code
          AND vote_results.territory_code = p_territory_code
          AND vote_results.organ_code = p_organ_code
          AND vote_results.votes > 0
    ),
    quotients AS (
        SELECT
            candidate_votes.candidacy_id,
            candidate_votes.sigla,
            candidate_votes.votes,
            divisor,
            candidate_votes.votes::numeric / divisor::numeric AS quotient
        FROM candidate_votes
        CROSS JOIN generate_series(1, p_seats) AS divisor
    ),
    ranked AS (
        SELECT
            row_number() OVER (
                ORDER BY quotient DESC, votes DESC, sigla ASC, divisor ASC
            )::integer AS seat_number,
            candidacy_id,
            sigla,
            votes,
            divisor,
            quotient
        FROM quotients
    )
    SELECT seat_number, candidacy_id, sigla, votes, divisor, quotient
    FROM ranked
    WHERE seat_number <= p_seats
    ORDER BY seat_number
$$;

CREATE OR REPLACE VIEW election.v_result_summary AS
SELECT
    elections.election_code,
    territories.territory_code,
    territories.territory_name,
    territories.territory_level,
    organs.organ_code,
    organs.organ_name,
    candidacies.candidacy_id,
    candidacies.sigla,
    candidacies.name,
    candidacies.candidate_type,
    vote_results.votes,
    turnout_results.voters - turnout_results.blank_votes - turnout_results.null_votes AS valid_votes,
    election.vote_share(
        vote_results.votes,
        turnout_results.voters - turnout_results.blank_votes - turnout_results.null_votes
    ) AS vote_share,
    COALESCE(seat_results.vote_percent, 0) AS official_vote_percent,
    COALESCE(seat_results.mandates, 0) AS mandates,
    turnout_results.registered_voters,
    turnout_results.voters,
    turnout_results.blank_votes,
    turnout_results.null_votes,
    election.turnout_rate(turnout_results.voters, turnout_results.registered_voters) AS turnout_rate
FROM election.vote_results
JOIN election.elections
  ON elections.election_id = vote_results.election_id
JOIN election.territories
  ON territories.territory_code = vote_results.territory_code
JOIN election.organs
  ON organs.organ_code = vote_results.organ_code
JOIN election.candidacies
  ON candidacies.candidacy_id = vote_results.candidacy_id
JOIN election.turnout_results
  ON turnout_results.election_id = vote_results.election_id
 AND turnout_results.territory_code = vote_results.territory_code
 AND turnout_results.organ_code = vote_results.organ_code
LEFT JOIN election.seat_results
  ON seat_results.election_id = vote_results.election_id
 AND seat_results.territory_code = vote_results.territory_code
 AND seat_results.organ_code = vote_results.organ_code
 AND seat_results.candidacy_id = vote_results.candidacy_id;

CREATE OR REPLACE VIEW election.v_territory_winners AS
SELECT *
FROM (
    SELECT
        v_result_summary.*,
        rank() OVER (
            PARTITION BY election_code, territory_code, organ_code
            ORDER BY votes DESC, sigla ASC
        ) AS result_rank
    FROM election.v_result_summary
) ranked
WHERE result_rank = 1;

CREATE OR REPLACE PROCEDURE dw.refresh_from_operational()
LANGUAGE plpgsql
AS $$
BEGIN
    TRUNCATE
        dw.fact_election_results,
        dw.dim_candidacy,
        dw.dim_territory,
        dw.dim_organ,
        dw.dim_election
    RESTART IDENTITY CASCADE;

    INSERT INTO dw.dim_election (election_id, election_code, election_name, election_date)
    SELECT election_id, election_code, election_name, election_date
    FROM election.elections;

    INSERT INTO dw.dim_organ (organ_code, organ_name, territory_level)
    SELECT organ_code, organ_name, territory_level
    FROM election.organs;

    INSERT INTO dw.dim_territory (
        territory_code,
        territory_name,
        territory_level,
        parent_code,
        district_code,
        municipality_code
    )
    SELECT
        territory_code,
        territory_name,
        territory_level,
        parent_code,
        district_code,
        municipality_code
    FROM election.territories;

    INSERT INTO dw.dim_candidacy (
        candidacy_id,
        election_code,
        organ_code,
        territory_code,
        source_candidate_ref,
        candidate_type,
        sigla,
        name
    )
    SELECT
        candidacies.candidacy_id,
        elections.election_code,
        candidacies.organ_code,
        candidacies.territory_code,
        candidacies.source_candidate_ref,
        candidacies.candidate_type,
        candidacies.sigla,
        candidacies.name
    FROM election.candidacies
    JOIN election.elections USING (election_id);

    INSERT INTO dw.fact_election_results (
        election_key,
        organ_key,
        territory_key,
        candidacy_key,
        votes,
        vote_percent,
        mandates,
        registered_voters,
        voters,
        blank_votes,
        null_votes
    )
    SELECT
        dim_election.election_key,
        dim_organ.organ_key,
        dim_territory.territory_key,
        dim_candidacy.candidacy_key,
        vote_results.votes,
        seat_results.vote_percent,
        COALESCE(seat_results.mandates, 0),
        turnout_results.registered_voters,
        turnout_results.voters,
        turnout_results.blank_votes,
        turnout_results.null_votes
    FROM election.vote_results
    JOIN election.elections
      ON elections.election_id = vote_results.election_id
    JOIN election.turnout_results
      ON turnout_results.election_id = vote_results.election_id
     AND turnout_results.territory_code = vote_results.territory_code
     AND turnout_results.organ_code = vote_results.organ_code
    JOIN election.candidacies
      ON candidacies.candidacy_id = vote_results.candidacy_id
    JOIN dw.dim_election
      ON dim_election.election_id = elections.election_id
    JOIN dw.dim_organ
      ON dim_organ.organ_code = vote_results.organ_code
    JOIN dw.dim_territory
      ON dim_territory.territory_code = vote_results.territory_code
    JOIN dw.dim_candidacy
      ON dim_candidacy.candidacy_id = vote_results.candidacy_id
    LEFT JOIN election.seat_results
      ON seat_results.election_id = vote_results.election_id
     AND seat_results.territory_code = vote_results.territory_code
     AND seat_results.organ_code = vote_results.organ_code
     AND seat_results.candidacy_id = vote_results.candidacy_id;

    REFRESH MATERIALIZED VIEW election.mv_result_summary;
    REFRESH MATERIALIZED VIEW election.mv_territory_winners;
    REFRESH MATERIALIZED VIEW election.mv_national_totals;
END;
$$;
