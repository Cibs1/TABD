"""Flask election analytics application — thin layer over PostgreSQL/PostGIS."""
from __future__ import annotations

import json
import os
import sys
import unicodedata
from itertools import groupby
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import psycopg2
import psycopg2.extras
import plotly.graph_objects as go
from flask import Flask, Response, abort, g, render_template, request

import db as _db

app = Flask(__name__)
app.config["DATABASE_URL"] = os.environ.get("DATABASE_URL") or "dbname=tabd"

# ---------------------------------------------------------------------------
# Per-request DB connection via Flask g
# ---------------------------------------------------------------------------

def get_db():
    if "conn" not in g:
        g.conn = psycopg2.connect(
            app.config["DATABASE_URL"],
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return g.conn


@app.teardown_appcontext
def close_db(exc):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    conn = get_db()
    elections = _db.get_elections(conn)
    election_code = request.args.get(
        "election_code",
        elections[0]["election_code"] if elections else "AL2021",
    )
    organ_code = request.args.get("organ_code", "CM")

    try:
        national = _db.get_national_totals(conn, election_code, organ_code)
        national_chart_html = _national_chart(national) if national else ""
    except Exception:
        national_chart_html = ""

    return render_template(
        "index.html",
        elections=elections,
        election_code=election_code,
        organ_code=organ_code,
        national_chart_html=national_chart_html,
    )


@app.route("/results")
def results():
    election_code = request.args.get("election_code", "AL2021")
    territory_code = request.args.get("territory_code")
    organ_code = request.args.get("organ_code", "CM")

    if not territory_code:
        abort(400, "territory_code is required")

    conn = get_db()
    elections = _db.get_elections(conn)
    territory = _db.get_territory_info(conn, territory_code)
    if not territory:
        abort(404, f"Territory {territory_code!r} not found")

    parish_af_summary = []
    if organ_code == "AF" and territory["territory_level"] == "municipality":
        parish_af_summary = _db.get_parish_af_summary(conn, territory_code, election_code)
        turnout = None
        rows = []
        elected_raw = []
    else:
        turnout = _db.get_turnout(conn, territory_code, organ_code, election_code)
        rows = _db.get_results(conn, territory_code, organ_code, election_code)
        elected_raw = _db.get_elected_members(conn, territory_code, organ_code, election_code)

    elected_by_party = {
        sigla: list(members)
        for sigla, members in groupby(elected_raw, key=lambda x: x["sigla"])
    }

    vote_chart_html = _vote_share_chart(rows) if rows else ""
    seat_chart_html = _seats_chart(rows) if rows else ""

    return render_template(
        "results.html",
        elections=elections,
        election_code=election_code,
        territory=territory,
        organ_code=organ_code,
        turnout=turnout,
        rows=rows,
        parish_af_summary=parish_af_summary,
        elected_by_party=elected_by_party,
        vote_chart_html=vote_chart_html,
        seat_chart_html=seat_chart_html,
    )

def normalize_name(name):
    return unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8').lower()

@app.route("/municipality/<name>")
def municipality(name):
    election_code = request.args.get("election_code", "AL2021")
    organ_code = request.args.get("organ_code", "CM")

    conn = get_db()
    municipalities = _db.get_territories_by_level(conn, "municipality")
    
    target_norm = normalize_name(name)
    territory = next((m for m in municipalities if normalize_name(m["territory_name"]) == target_norm), None)
    
    if not territory:
        abort(404, f"Municipality {name!r} not found")

    territory_code = territory["territory_code"]
    elections = _db.get_elections(conn)

    parish_af_summary = []
    if organ_code == "AF" and territory["territory_level"] == "municipality":
        parish_af_summary = _db.get_parish_af_summary(conn, territory_code, election_code)
        turnout = None
        rows = []
        elected_raw = []
    else:
        turnout = _db.get_turnout(conn, territory_code, organ_code, election_code)
        rows = _db.get_results(conn, territory_code, organ_code, election_code)
        elected_raw = _db.get_elected_members(conn, territory_code, organ_code, election_code)

    elected_by_party = {
        sigla: list(members)
        for sigla, members in groupby(elected_raw, key=lambda x: x["sigla"])
    }

    vote_chart_html = _vote_share_chart(rows) if rows else ""
    seat_chart_html = _seats_chart(rows) if rows else ""

    return render_template(
        "results.html",
        elections=elections,
        election_code=election_code,
        territory=territory,
        organ_code=organ_code,
        turnout=turnout,
        rows=rows,
        parish_af_summary=parish_af_summary,
        elected_by_party=elected_by_party,
        vote_chart_html=vote_chart_html,
        seat_chart_html=seat_chart_html,
    )

@app.route("/compare")
def compare():
    conn = get_db()
    elections = _db.get_elections(conn)
    election_codes = [e["election_code"] for e in elections]

    default_to = election_codes[0] if election_codes else "AL2025"
    default_from = election_codes[-1] if len(election_codes) > 1 else default_to
    from_election = request.args.get("from_election", default_from)
    to_election = request.args.get("to_election", default_to)
    organ_code = request.args.get("organ_code", "CM")

    if from_election not in election_codes and election_codes:
        from_election = default_from
    if to_election not in election_codes and election_codes:
        to_election = default_to
    if organ_code not in {"CM", "AM"}:
        organ_code = "CM"

    election_dates = {e["election_code"]: e["election_date"] for e in elections}
    from_date = election_dates.get(from_election)
    to_date = election_dates.get(to_election)
    if from_date and to_date:
        start_date, end_date = sorted((from_date, to_date))
        interval_election_codes = {
            code
            for code, election_date in election_dates.items()
            if election_date and start_date <= election_date <= end_date
        }
    else:
        interval_election_codes = {from_election, to_election}

    family_share_all = _db.get_historical_family_vote_share(conn, organ_code)
    family_share = [
        row for row in family_share_all
        if row["election_code"] in interval_election_codes
    ]
    seat_changes = _db.get_historical_seat_changes(conn, from_election, to_election, organ_code)
    turnout_changes = _db.get_historical_turnout_changes(conn, from_election, to_election, organ_code)
    winner_changes = _db.get_historical_winner_changes(conn, from_election, to_election, organ_code)

    return render_template(
        "compare.html",
        elections=elections,
        from_election=from_election,
        to_election=to_election,
        organ_code=organ_code,
        family_share=family_share,
        seat_changes=seat_changes,
        turnout_changes=turnout_changes,
        winner_changes=winner_changes,
        family_chart_html=_family_trend_chart(family_share, from_election, to_election),
        seat_change_chart_html=_seat_change_chart(seat_changes, from_election, to_election),
        turnout_change_chart_html=_turnout_change_chart(turnout_changes, from_election, to_election),
    )


@app.route("/api/map.geojson")
def map_geojson():
    election_code = request.args.get("election_code", "AL2021")
    organ_code = request.args.get("organ_code", "CM")
    conn = get_db()
    try:
        data = _db.get_municipalities_geojson(conn, election_code, organ_code)
    except Exception:
        data = {"type": "FeatureCollection", "features": []}
    return Response(json.dumps(data), mimetype="application/json")


# ---------------------------------------------------------------------------
# Chart generators (Plotly Python → embedded HTML)
# ---------------------------------------------------------------------------

def _national_chart(rows):
    top = rows[:12]
    fig = go.Figure(go.Bar(
        x=[float(r["national_vote_share"] or 0) for r in top],
        y=[r["sigla"] for r in top],
        orientation="h",
        marker_color="#4f8ef7",
        text=[f"{r['national_vote_share']}%" for r in top],
        textposition="outside",
    ))
    fig.update_layout(
        title="National Vote Share",
        xaxis_title="%",
        height=380,
        margin=dict(l=120, r=50, t=40, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=11),
        yaxis=dict(autorange="reversed"),
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _vote_share_chart(rows):
    top = [r for r in rows if (r["votes"] or 0) > 0][:15]
    fig = go.Figure(go.Bar(
        x=[float(r["vote_share"] or 0) for r in top],
        y=[r["sigla"] for r in top],
        orientation="h",
        marker_color="#4f8ef7",
        text=[f"{r['vote_share']}%" for r in top],
        textposition="outside",
    ))
    fig.update_layout(
        title="Vote Share (%)",
        xaxis_title="%",
        height=max(300, 30 * len(top) + 80),
        margin=dict(l=120, r=70, t=40, b=30),
        paper_bgcolor="white",
        plot_bgcolor="white",
        yaxis=dict(autorange="reversed"),
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _seats_chart(rows):
    seat_rows = [r for r in rows if (r["mandates"] or 0) > 0]
    if not seat_rows:
        return ""
    fig = go.Figure(go.Pie(
        labels=[r["sigla"] for r in seat_rows],
        values=[r["mandates"] for r in seat_rows],
        hole=0.4,
        textinfo="label+value",
    ))
    fig.update_layout(
        title="Seat Distribution",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor="white",
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _family_trend_chart(rows, from_election, to_election):
    if not rows:
        return ""

    priority = ["PS", "PPD/PSD and coalitions", "CDU", "BE", "CH", "IL", "PAN", "Other"]
    rows_by_family = {family: [] for family in priority}
    for row in rows:
        rows_by_family.setdefault(row["political_family"], []).append(row)

    palette = {
        "PS": "#d62728",
        "PPD/PSD and coalitions": "#f59e0b",
        "CDU": "#166534",
        "BE": "#7f1d1d",
        "CH": "#1e1b4b",
        "IL": "#06b6d4",
        "PAN": "#16a34a",
        "Other": "#6b7280",
    }

    fig = go.Figure()
    for family in priority:
        family_rows = sorted(rows_by_family.get(family, []), key=lambda r: r["election_code"])
        if not family_rows:
            continue
        fig.add_trace(go.Scatter(
            x=[r["election_code"] for r in family_rows],
            y=[float(r["vote_share"] or 0) for r in family_rows],
            mode="lines+markers",
            name=family,
            line=dict(width=3, color=palette.get(family)),
            marker=dict(size=7),
        ))

    fig.update_layout(
        title=f"Vote Share by Political Family: {from_election} to {to_election}",
        yaxis_title="%",
        height=390,
        margin=dict(l=45, r=20, t=45, b=40),
        paper_bgcolor="white",
        plot_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="left", x=0),
        hovermode="x unified",
    )
    fig.update_yaxes(rangemode="tozero")
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _seat_change_chart(rows, from_election, to_election):
    if not rows:
        return ""

    top = [r for r in rows if r["seat_change"] is not None][:10]
    fig = go.Figure(go.Bar(
        x=[int(r["seat_change"] or 0) for r in top],
        y=[r["political_family"] for r in top],
        orientation="h",
        marker_color=[
            "#198754" if (r["seat_change"] or 0) >= 0 else "#dc3545"
            for r in top
        ],
        text=[f"{int(r['seat_change'] or 0):+d}" for r in top],
        textposition="outside",
    ))
    fig.update_layout(
        title=f"Seat Change: {from_election} to {to_election}",
        xaxis_title="Seats",
        height=340,
        margin=dict(l=150, r=70, t=45, b=35),
        paper_bgcolor="white",
        plot_bgcolor="white",
        yaxis=dict(autorange="reversed"),
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _turnout_change_chart(rows, from_election, to_election):
    if not rows:
        return ""

    top = rows[:15]
    fig = go.Figure(go.Bar(
        x=[float(r["turnout_change"] or 0) for r in top],
        y=[r["territory_name"] for r in top],
        orientation="h",
        marker_color=[
            "#198754" if (r["turnout_change"] or 0) >= 0 else "#dc3545"
            for r in top
        ],
        text=[f"{float(r['turnout_change'] or 0):+.2f}%" for r in top],
        textposition="outside",
    ))
    fig.update_layout(
        title=f"Largest Voter Turnout Changes: {from_election} to {to_election}",
        xaxis_title="Change in voter turnout (%)",
        height=430,
        margin=dict(l=150, r=85, t=45, b=35),
        paper_bgcolor="white",
        plot_bgcolor="white",
        yaxis=dict(autorange="reversed"),
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
