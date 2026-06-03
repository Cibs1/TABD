"""Flask election analytics application — thin layer over PostgreSQL/PostGIS."""
from __future__ import annotations

import json
import os
import sys
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
        elected_by_party=elected_by_party,
        vote_chart_html=vote_chart_html,
        seat_chart_html=seat_chart_html,
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


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
