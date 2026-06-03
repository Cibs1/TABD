# Assignment Status

Status checked against `advanced_topics_databases_practical_assignment.pdf`.

## Implemented

### 5.1 Operational data model

Implemented in `sql/02_operational_schema.sql`.

Current operational entities:

- elections
- organs
- territories
- candidacies
- turnout results
- vote results
- seat results
- elected members

The model includes primary keys, foreign keys, uniqueness constraints, and indexes. It supports municipality and parish-level election rows. Districts are represented as parent territories.

### 5.2 Staging area, ETL, and data warehouse

Implemented in:

- `sql/01_staging_schema.sql`
- `sql/03_warehouse_schema.sql`
- `etl/load_cne_2021.py`
- `etl/xlsx_reader.py`

The ETL is rerunnable and loads the official CNE Excel files into staging, then into the operational schema and warehouse.

The PostgreSQL/PostGIS load has been tested successfully on the local `tabd` database with:

```bash
.venv/bin/python etl/load_cne_2021.py --setup --dsn "dbname=tabd"
```

Current parsed CNE counts:

```text
result rows:       3719
candidate aliases: 2755
candidate votes:   12277
percent/mandates:  12277
elected members:   35491
```

The warehouse has dimensions for election, organ, territory, and candidacy, plus a result fact table.

### 5.3 SQL functions, PL/pgSQL, and triggers

Implemented in `sql/04_functions_views_triggers.sql`.

Current functions/views/procedures/triggers include:

- `election.vote_share(...)`
- `election.turnout_rate(...)`
- `election.dhondt_allocate(...)`
- `election.v_result_summary`
- `election.v_territory_winners`
- `election.load_from_staging()`
- `dw.refresh_from_operational()`
- turnout consistency trigger
- vote result consistency trigger
- seat result consistency trigger

### 5.4 Analytical SQL requirements

Implemented in `sql/05_analytical_queries.sql`.

Coverage:

- D'Hondt method
- 3 window-function queries
- 1 `GROUP BY ROLLUP`
- 1 `GROUP BY CUBE`
- advanced aggregates using `FILTER` and `jsonb_agg`

### 5.5 Spatial data and visualization

Minimum requirement implemented and loaded.

Implemented:

- `election.territories.geom` as `geometry(MultiPolygon, 3763)`
- spatial index on `territories.geom`
- `etl/load_caop.py` to load CAOP GeoPackage or shapefile boundaries
- Flask GeoJSON endpoint for municipality map data
- Leaflet map in the frontend
- CAOP 2025 GeoPackages loaded as a newer compatible DGT boundary dataset

Loaded geometry counts:

```text
district        20 / 20
municipality   308 / 308
parish        2949 / 3083
```

The Flask GeoJSON map endpoint has been tested against the loaded database and returns 308 municipality features.

### 5.6 Web frontend

Implemented in `app/`.

Implemented:

- Flask app
- explicit SQL through `psycopg2`
- election selector
- organ selector
- municipality map endpoint
- results table
- turnout summary
- vote-share chart
- seat-distribution chart
- elected-members display

Validated endpoint checks:

```text
GET /                                                              200
GET /api/map.geojson?election_code=AL2021&organ_code=CM           200, 308 features
GET /results?election_code=AL2021&territory_code=010100&organ_code=CM  200
```

## Missing Deliverables

### Required project files

Complete or mostly complete:

- `/docs/report.tex` and `/docs/report.pdf`: 5-page two-column report.
- ER diagram: included in the report as a TikZ figure.
- warehouse/star-schema diagram: included in the report as a TikZ figure.
- `/slides/`: presentation source/PDF should be included before final submission.

Still recommended before final submission:

- frontend/map screenshots in `/docs/`, ideally one homepage map screenshot and one municipality results screenshot.

### Reproducibility

Mostly complete.

Validated:

- CNE ETL setup/load into PostgreSQL/PostGIS.
- CAOP GeoPackage load into PostGIS.
- validation queries against local `tabd`.
- Flask endpoint checks against the populated database.

Still recommended:

- have both group members run the README commands once before submission.

### Data validation

Partially complete.

Validated:

- row counts after PostgreSQL load
- Agueda CM result summary
- Agueda CM D'Hondt mandates against official mandates

Known limitation:

- `staging.cne_elected_members` has 35491 parsed rows, while `election.elected_members` has 35142 loaded rows. The mismatch comes from elected-member records that do not match a normalized candidacy/territory exactly, mostly in parish-level rows with inconsistent codes or list labels. This does not affect vote, turnout, mandate, D'Hondt, or warehouse facts.

## Recommended Next Order

1. Add/take frontend screenshots for the documentation folder.
2. Review the report and slides together so both group members can explain the design.
3. Submit the repository/archive and prepare the oral demo.
