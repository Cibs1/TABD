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

The ETL is rerunnable and loads the official CNE Excel files into staging, then into the operational schema and warehouse. It now supports the 2013, 2017, 2021, and 2025 Autarquicas packages through `--source-dir`, `--election-code`, `--election-name`, and `--election-date`.

The PostgreSQL/PostGIS load has been tested successfully on the local `tabd` database with:

```bash
.venv/bin/python etl/load_cne_2021.py --setup --dsn "dbname=tabd"
```

Current loaded vote-result counts:

```text
AL2013: 12152
AL2017: 12069
AL2021: 12295
AL2025: 12839
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

Implemented in `sql/05_analytical_queries.sql` and extended in `sql/08_historical_comparisons.sql`.

Coverage:

- D'Hondt method
- 3 window-function queries
- 1 `GROUP BY ROLLUP`
- 1 `GROUP BY CUBE`
- advanced aggregates using `FILTER` and `jsonb_agg`
- historical comparison queries for turnout changes, political-family vote-share trends, winner changes, and seat changes across 2013/2017/2021/2025

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
district        20 / 21   # national aggregate has no polygon
municipality   308 / 308
parish        3241 / 3394
```

The Flask GeoJSON map endpoint has been tested against the loaded database and returns 308 municipality features.

After loading all four election packages, parish territory coverage is:

```text
district        20 / 21   # national aggregate has no polygon
municipality   308 / 308
parish        3241 / 3394
```

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
- historical comparison page with vote-share trend, seat-change, turnout-change, and winner-change views

Validated endpoint checks:

```text
GET /                                                              200
GET /api/map.geojson?election_code=AL2021&organ_code=CM           200, 308 features
GET /results?election_code=AL2021&territory_code=010100&organ_code=CM  200
GET /compare?from_election=AL2013&to_election=AL2025&organ_code=CM 200
```

## Optional Extension Coverage

Covered from the assignment's suggested extensions:

- historical comparisons: implemented for Autarquicas 2013, 2017, 2021, and 2025.
- additional territory levels: parish-level election rows are loaded, beyond district/municipality.
- materialized views/precomputed aggregates: implemented through `mv_result_summary`, `mv_national_totals`, and `mv_territory_winners`.
- richer frontend interaction: election/organ selectors, clickable Leaflet map, result page with charts and elected members, and a dedicated historical comparison page.

Not implemented:

- more than one election type. The project compares several years of the same election type, not legislative/presidential elections.

## Missing Deliverables

### Required project files

Complete or mostly complete:

- `/docs/report.tex` and `/docs/report.pdf`: two-column report.
- ER diagram: included in the report as a TikZ figure.
- warehouse/star-schema diagram: included in the report as a TikZ figure.
- `/slides/`: presentation source/PDF.
- `/docs/screenshots/`: homepage map and municipality result screenshots.

### Reproducibility

Mostly complete.

Validated:

- CNE ETL setup/load into PostgreSQL/PostGIS.
- CAOP GeoPackage load into PostGIS.
- validation queries and historical comparison queries against local `tabd`.
- Flask endpoint checks against the populated database.

Still recommended:

- have both group members run the README commands once before submission.

### Data validation

Mostly complete.

Validated:

- row counts after PostgreSQL load
- Agueda CM result summary
- Agueda CM D'Hondt mandates against official mandates
- loaded election counts for AL2013, AL2017, AL2021, and AL2025
- historical comparison query execution

Known limitation:

- Some elected-member records do not match a normalized candidacy/territory exactly, mostly in parish-level rows with inconsistent codes or list labels. This does not affect vote, turnout, mandate, D'Hondt, warehouse facts, or municipality-level historical comparisons.
- The official AL2013 package contains one parish-level turnout anomaly: Covelas, Povoa de Lanhoso, AF has 420 registered voters and 422 voters. The loader preserves the official values, so the turnout trigger enforces non-negative values and blank/null consistency but does not reject voters greater than registered voters.

## Recommended Next Order

1. Review the report and slides together so both group members can explain the design.
2. In the oral demo, show `sql/08_historical_comparisons.sql` and the `/compare` page as the optional historical-comparison extension.
3. Submit the repository/archive and prepare the live Flask demo.
