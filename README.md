# Election Analytics Platform for Portugal

Database-centred project for the Advanced Topics in Databases practical assignment.

The current implementation uses the official CNE Autarquicas 2021 spreadsheet package and builds:

- a staging schema for raw Excel-derived data;
- a normalized operational schema;
- a data warehouse schema;
- PL/pgSQL procedures, functions, triggers, views, and materialized views;
- analytical SQL examples required by the assignment;
- a CAOP/PostGIS geometry loader;
- a thin Flask frontend using explicit SQL through `psycopg2`.

## Source Data

The CNE files must be in:

```text
2021al_mapa_oficial/
```

The ETL currently uses:

- `mapa_1_resultados.xlsx`: registered voters, voters, blank/null votes, and votes per candidacy.
- `mapa_anexo.xlsx`: resolution of local `[A]..[G]` coalition and citizen-group labels.
- `mapa_2_perc_mandatos.xlsx`: official percentages and mandates.
- `mapa_3_eleitos.xlsx`: elected members per territory, organ, and list.

For maps, use the DGT CAOP GeoPackages currently placed in:

```text
CAOP_Continente_2025-gpkg/
CAOP_RAM_2025-gpkg/
CAOP_RAA_2025-gpkg/
```

The assignment recommends CAOP 2021 to match the election year. This project uses CAOP 2025 as a newer compatible DGT administrative-boundary dataset; mention this choice in the report.

## Python Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## PostgreSQL Setup

Create a PostgreSQL database with PostGIS available. Example:

```bash
createdb tabd
psql -d tabd -c "CREATE EXTENSION IF NOT EXISTS postgis;"
export DATABASE_URL="postgresql://USER:PASSWORD@localhost:5432/tabd"
```

Adjust the connection string to your local user/password.

On Ubuntu with PostgreSQL 18, install PostGIS first if `CREATE EXTENSION postgis` fails:

```bash
sudo apt-get install -y postgresql-18-postgis-3 postgresql-18-postgis-3-scripts
sudo systemctl restart postgresql
```

## Load CNE Election Data

Dry-run the parser first:

```bash
python3 etl/load_cne_2021.py --dry-run
```

Expected counts:

```text
result rows:       3719
candidate aliases: 2755
candidate votes:   12277
percent/mandates:  12277
elected members:   35491
```

Export processed CSV files for inspection:

```bash
python3 etl/load_cne_2021.py --dry-run --export-processed data/processed
```

Create schemas and load the database:

```bash
python3 etl/load_cne_2021.py --setup
```

## Load CAOP Geometries

Inspect detected GeoPackage layers and columns:

```bash
.venv/bin/python etl/load_caop.py --caop-dir . --dry-run
```

Load geometries into `election.territories.geom`:

```bash
.venv/bin/python etl/load_caop.py --caop-dir . --dsn "dbname=tabd"
```

Expected loaded geometry coverage:

```text
district        20 / 20
municipality   308 / 308
parish        2949 / 3083
```

## Run the Flask App

After the database is loaded:

```bash
.venv/bin/flask --app app/app.py run
```

Open:

```text
http://127.0.0.1:5000
```

The map will show data only after CAOP geometries are loaded. Before that, the app can still query election results directly by URL, for example:

```text
http://127.0.0.1:5000/results?election_code=AL2021&territory_code=010100&organ_code=CM
```

## SQL Files

- `sql/00_extensions_and_schemas.sql`: PostGIS extension and schema reset.
- `sql/01_staging_schema.sql`: raw CNE staging tables.
- `sql/02_operational_schema.sql`: normalized operational model.
- `sql/03_warehouse_schema.sql`: star-schema warehouse.
- `sql/04_functions_views_triggers.sql`: SQL functions, PL/pgSQL routines, triggers, views, D'Hondt, and warehouse refresh.
- `sql/05_analytical_queries.sql`: required analytical query examples.
- `sql/06_materialized_views.sql`: cached frontend/analytics views.
- `sql/07_validation_queries.sql`: post-load validation queries.

## Validation Queries

After loading PostgreSQL, run:

```sql
SELECT count(*) FROM staging.cne_result_rows;
SELECT count(*) FROM staging.cne_candidate_votes;
SELECT count(*) FROM staging.cne_percent_mandates;
SELECT count(*) FROM staging.cne_elected_members;

SELECT count(*) FROM election.turnout_results;
SELECT count(*) FROM election.vote_results;
SELECT count(*) FROM election.seat_results;
SELECT count(*) FROM election.elected_members;

SELECT count(*) FROM dw.fact_election_results;
```

Or run the validation file:

```bash
psql -d tabd -f sql/07_validation_queries.sql
```

Check a known municipality:

```sql
SELECT sigla, votes, vote_share, mandates
FROM election.mv_result_summary
WHERE territory_code = '010100'
  AND organ_code = 'CM'
ORDER BY votes DESC;
```

Validate D'Hondt for Agueda CM:

```sql
SELECT *
FROM election.dhondt_allocate('010100', 'CM', 7);
```

Compare with official mandates:

```sql
SELECT sigla, mandates
FROM election.mv_result_summary
WHERE territory_code = '010100'
  AND organ_code = 'CM'
ORDER BY mandates DESC, votes DESC;
```

## Current Limitations

- The project uses official DGT CAOP 2025 GeoPackages instead of CAOP 2021. This is documented in the report as a newer compatible boundary dataset.
- Parish geometry coverage is partial: 2949 / 3083 parish territories have geometry after the CAOP 2025 load. The assignment minimum is still satisfied because district/region and municipality geometries are fully loaded.
- `staging.cne_elected_members` has 35491 parsed rows, while `election.elected_members` has 35142 loaded rows. The difference comes from parish-level elected-member labels/codes that do not match normalized candidacies exactly. Vote, turnout, mandate, D'Hondt, warehouse, and municipality-level analyses are unaffected.
- Before submission, add screenshots of the frontend/map to `docs/` if your teacher expects screenshot files separately from the report.

## Deliverables Status

- `sql/`: DDL, warehouse, functions, views, triggers, analytical queries, validation queries.
- `etl/`: CNE and CAOP loaders.
- `app/`: Flask frontend using `psycopg2`.
- `docs/report.tex` and `docs/report.pdf`: two-column 5-page report with TikZ diagrams.
- `slides/presentation.tex`: oral presentation source.
