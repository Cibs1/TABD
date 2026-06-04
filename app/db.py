"""Database query functions — all SQL is explicit, psycopg2 only, no ORM."""
from __future__ import annotations

import json
import os

import psycopg2
import psycopg2.extras

DSN = os.environ.get("DATABASE_URL") or "dbname=tabd"


def get_conn():
    return psycopg2.connect(DSN, cursor_factory=psycopg2.extras.RealDictCursor)


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

def get_elections(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT election_code, election_name, election_date
            FROM election.elections
            ORDER BY election_date DESC NULLS LAST
        """)
        return cur.fetchall()


def get_territory_info(conn, territory_code: str):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT t.territory_code, t.territory_name, t.territory_level,
                   p.territory_name AS parent_name,
                   p.territory_code AS parent_code
            FROM election.territories t
            LEFT JOIN election.territories p ON p.territory_code = t.parent_code
            WHERE t.territory_code = %s
        """, (territory_code,))
        return cur.fetchone()


def get_territories_by_level(conn, level: str):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT t.territory_code, t.territory_name, t.territory_level,
                   p.territory_name AS parent_name,
                   p.territory_code AS parent_code
            FROM election.territories t
            LEFT JOIN election.territories p ON p.territory_code = t.parent_code
            WHERE t.territory_level = %s
        """, (level,))
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Turnout and results
# ---------------------------------------------------------------------------

def get_turnout(conn, territory_code: str, organ_code: str, election_code: str):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT tr.registered_voters,
                   tr.voters,
                   tr.blank_votes,
                   tr.null_votes,
                   election.turnout_rate(tr.voters, tr.registered_voters) AS turnout_rate,
                   tr.voters - tr.blank_votes - tr.null_votes AS valid_votes
            FROM election.turnout_results tr
            JOIN election.elections e USING (election_id)
            WHERE tr.territory_code = %s
              AND tr.organ_code = %s
              AND e.election_code = %s
        """, (territory_code, organ_code, election_code))
        return cur.fetchone()


def get_results(conn, territory_code: str, organ_code: str, election_code: str):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT sigla, name, candidate_type,
                   votes, vote_share, mandates, official_vote_percent
            FROM election.mv_result_summary
            WHERE territory_code = %s
              AND organ_code = %s
              AND election_code = %s
            ORDER BY votes DESC
        """, (territory_code, organ_code, election_code))
        return cur.fetchall()


def get_elected_members(conn, territory_code: str, organ_code: str, election_code: str):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT em.list_position, em.member_name, c.sigla
            FROM election.elected_members em
            JOIN election.candidacies c USING (candidacy_id)
            JOIN election.elections e ON e.election_id = em.election_id
            WHERE em.territory_code = %s
              AND em.organ_code = %s
              AND e.election_code = %s
            ORDER BY c.sigla, em.list_position
        """, (territory_code, organ_code, election_code))
        return cur.fetchall()


def get_parish_af_summary(conn, municipality_code: str, election_code: str):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                freg.territory_code,
                freg.territory_name,
                w.sigla AS winner_sigla,
                w.votes,
                w.vote_share,
                w.mandates,
                election.turnout_rate(tr.voters, tr.registered_voters) AS turnout_rate
            FROM election.mv_territory_winners w
            JOIN election.territories freg
              ON freg.territory_code = w.territory_code
            JOIN election.elections e
              ON e.election_code = w.election_code
            LEFT JOIN election.turnout_results tr
              ON tr.election_id = e.election_id
             AND tr.territory_code = freg.territory_code
             AND tr.organ_code = 'AF'
            WHERE w.election_code = %s
              AND w.organ_code = 'AF'
              AND w.territory_level = 'parish'
              AND freg.municipality_code = %s
            ORDER BY freg.territory_name
        """, (election_code, municipality_code))
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Analytical / warehouse queries
# ---------------------------------------------------------------------------

def get_national_totals(conn, election_code: str, organ_code: str = "CM"):
    """Top parties by national vote share — uses mv_national_totals."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT sigla, candidate_type,
                   total_votes, total_mandates, national_vote_share
            FROM election.mv_national_totals
            WHERE election_code = %s AND organ_code = %s
            ORDER BY total_votes DESC
            LIMIT 15
        """, (election_code, organ_code))
        return cur.fetchall()


def get_district_summary(conn, election_code: str, organ_code: str = "CM"):
    """Votes by district with ROLLUP — used for analytical display."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                district.territory_name AS district_name,
                rs.sigla,
                SUM(rs.votes) AS votes
            FROM election.mv_result_summary rs
            JOIN election.territories mun
                ON mun.territory_code = rs.territory_code
            JOIN election.territories district
                ON district.territory_code = mun.district_code
            WHERE rs.organ_code = %s
              AND rs.territory_level = 'municipality'
              AND rs.election_code = %s
            GROUP BY ROLLUP (district.territory_name, rs.sigla)
            ORDER BY district_name NULLS LAST, votes DESC NULLS LAST
        """, (organ_code, election_code))
        return cur.fetchall()


def get_historical_family_vote_share(conn, organ_code: str = "CM"):
    with conn.cursor() as cur:
        cur.execute("""
            WITH family_results AS (
                SELECT
                    election_code,
                    CASE
                        WHEN sigla = 'PS' OR sigla LIKE 'PS.%%' THEN 'PS'
                        WHEN sigla LIKE 'PPD/PSD%%' THEN 'PPD/PSD and coalitions'
                        WHEN sigla IN ('PCP-PEV', 'CDU') THEN 'CDU'
                        WHEN sigla IN ('B.E.', 'BE') THEN 'BE'
                        WHEN sigla = 'CH' THEN 'CH'
                        WHEN sigla = 'IL' THEN 'IL'
                        WHEN sigla = 'PAN' THEN 'PAN'
                        ELSE 'Other'
                    END AS political_family,
                    SUM(votes) AS votes
                FROM election.mv_result_summary
                WHERE organ_code = %s
                  AND territory_level = 'municipality'
                GROUP BY election_code, political_family
            )
            SELECT
                election_code,
                political_family,
                votes,
                ROUND(
                    votes::numeric
                    / NULLIF(SUM(votes) OVER (PARTITION BY election_code), 0)
                    * 100,
                    2
                ) AS vote_share
            FROM family_results
            ORDER BY election_code, vote_share DESC
        """, (organ_code,))
        return cur.fetchall()


def get_historical_seat_changes(conn, from_election: str, to_election: str, organ_code: str = "CM"):
    with conn.cursor() as cur:
        cur.execute("""
            WITH family_seats AS (
                SELECT
                    election_code,
                    CASE
                        WHEN sigla = 'PS' OR sigla LIKE 'PS.%%' THEN 'PS'
                        WHEN sigla LIKE 'PPD/PSD%%' THEN 'PPD/PSD and coalitions'
                        WHEN sigla IN ('PCP-PEV', 'CDU') THEN 'CDU'
                        WHEN sigla IN ('B.E.', 'BE') THEN 'BE'
                        WHEN sigla = 'CH' THEN 'CH'
                        WHEN sigla = 'IL' THEN 'IL'
                        WHEN sigla = 'PAN' THEN 'PAN'
                        ELSE 'Other'
                    END AS political_family,
                    SUM(mandates) AS seats
                FROM election.mv_result_summary
                WHERE organ_code = %s
                  AND territory_level = 'municipality'
                  AND election_code IN (%s, %s)
                GROUP BY election_code, political_family
            )
            SELECT
                political_family,
                COALESCE(MAX(seats) FILTER (WHERE election_code = %s), 0) AS seats_from,
                COALESCE(MAX(seats) FILTER (WHERE election_code = %s), 0) AS seats_to,
                COALESCE(MAX(seats) FILTER (WHERE election_code = %s), 0)
                  - COALESCE(MAX(seats) FILTER (WHERE election_code = %s), 0) AS seat_change
            FROM family_seats
            GROUP BY political_family
            ORDER BY ABS(
                COALESCE(MAX(seats) FILTER (WHERE election_code = %s), 0)
                  - COALESCE(MAX(seats) FILTER (WHERE election_code = %s), 0)
            ) DESC, political_family
        """, (
            organ_code,
            from_election,
            to_election,
            from_election,
            to_election,
            to_election,
            from_election,
            to_election,
            from_election,
        ))
        return cur.fetchall()


def get_historical_turnout_changes(conn, from_election: str, to_election: str, organ_code: str = "CM", limit: int = 25):
    with conn.cursor() as cur:
        cur.execute("""
            WITH turnout AS (
                SELECT
                    e.election_code,
                    t.territory_code,
                    t.territory_name,
                    CASE
                        WHEN tr.voters = 0 THEN NULL
                        ELSE election.turnout_rate(tr.voters, tr.registered_voters)
                    END AS turnout_rate
                FROM election.turnout_results tr
                JOIN election.elections e
                  ON e.election_id = tr.election_id
                JOIN election.territories t
                  ON t.territory_code = tr.territory_code
                WHERE tr.organ_code = %s
                  AND t.territory_level = 'municipality'
                  AND e.election_code IN (%s, %s)
            )
            SELECT
                territory_code,
                territory_name,
                MAX(turnout_rate) FILTER (WHERE election_code = %s) AS turnout_from,
                MAX(turnout_rate) FILTER (WHERE election_code = %s) AS turnout_to,
                MAX(turnout_rate) FILTER (WHERE election_code = %s)
                  - MAX(turnout_rate) FILTER (WHERE election_code = %s) AS turnout_change
            FROM turnout
            GROUP BY territory_code, territory_name
            HAVING MAX(turnout_rate) FILTER (WHERE election_code = %s) IS NOT NULL
               AND MAX(turnout_rate) FILTER (WHERE election_code = %s) IS NOT NULL
            ORDER BY ABS(
                MAX(turnout_rate) FILTER (WHERE election_code = %s)
                  - MAX(turnout_rate) FILTER (WHERE election_code = %s)
            ) DESC
            LIMIT %s
        """, (
            organ_code,
            from_election,
            to_election,
            from_election,
            to_election,
            to_election,
            from_election,
            from_election,
            to_election,
            to_election,
            from_election,
            limit,
        ))
        return cur.fetchall()


def get_historical_winner_changes(conn, from_election: str, to_election: str, organ_code: str = "CM", limit: int = 100):
    with conn.cursor() as cur:
        cur.execute("""
            WITH winners AS (
                SELECT
                    election_code,
                    territory_code,
                    territory_name,
                    sigla AS winner,
                    vote_share
                FROM election.mv_territory_winners
                WHERE organ_code = %s
                  AND territory_level = 'municipality'
                  AND election_code IN (%s, %s)
            )
            SELECT
                from_w.territory_code,
                from_w.territory_name,
                from_w.winner AS winner_from,
                to_w.winner AS winner_to,
                from_w.vote_share AS share_from,
                to_w.vote_share AS share_to
            FROM winners from_w
            JOIN winners to_w
              ON to_w.territory_code = from_w.territory_code
             AND to_w.election_code = %s
            WHERE from_w.election_code = %s
              AND from_w.winner IS DISTINCT FROM to_w.winner
            ORDER BY from_w.territory_name
            LIMIT %s
        """, (organ_code, from_election, to_election, to_election, from_election, limit))
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Spatial / GeoJSON
# ---------------------------------------------------------------------------

def get_municipalities_geojson(conn, election_code: str, organ_code: str = "CM") -> dict:
    """
    Municipality boundaries with winner info for the Leaflet choropleth.
    Returns GeoJSON FeatureCollection; empty if geometry not yet loaded.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                t.territory_code,
                t.territory_name,
                d.territory_name AS district_name,
                w.sigla        AS winner_sigla,
                w.votes,
                w.vote_share,
                w.mandates,
                election.turnout_rate(tr.voters, tr.registered_voters) AS turnout_rate,
                ST_AsGeoJSON(
                    ST_Transform(
                        ST_SimplifyPreserveTopology(t.geom, 100),
                        4326
                    )
                ) AS geojson
            FROM election.territories t
            LEFT JOIN election.elections e
                ON e.election_code = %s
            LEFT JOIN election.territories d
                ON d.territory_code = t.district_code
            LEFT JOIN election.mv_territory_winners w
                ON w.territory_code = t.territory_code
               AND w.election_code = %s
               AND w.organ_code = %s
            LEFT JOIN election.turnout_results tr
                ON tr.territory_code = t.territory_code
               AND tr.organ_code = %s
               AND tr.election_id = e.election_id
            WHERE t.territory_level = 'municipality'
              AND t.geom IS NOT NULL
        """, (election_code, election_code, organ_code, organ_code))
        rows = cur.fetchall()

    features = []
    for row in rows:
        if not row["geojson"]:
            continue
        features.append({
            "type": "Feature",
            "geometry": json.loads(row["geojson"]),
            "properties": {
                "territory_code": row["territory_code"],
                "territory_name": row["territory_name"],
                "district_name": row["district_name"],
                "winner_sigla": row["winner_sigla"],
                "votes": row["votes"],
                "vote_share": float(row["vote_share"]) if row["vote_share"] else None,
                "mandates": row["mandates"],
                "turnout_rate": float(row["turnout_rate"]) if row["turnout_rate"] else None,
            },
        })
    return {"type": "FeatureCollection", "features": features}
