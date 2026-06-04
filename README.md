# Election Analytics Platform for Portugal

Database-centred project for the Advanced Topics in Databases practical assignment.

The current implementation uses official CNE Autarquicas spreadsheet packages for 2013, 2017, 2021, and 2025 and builds:

- a staging schema for raw Excel-derived data;
- a normalized operational schema;
- a data warehouse schema;
- PL/pgSQL procedures, functions, triggers, views, and materialized views;
- analytical SQL examples required by the assignment;
- a CAOP/PostGIS geometry loader;
- a thin Flask frontend using explicit SQL through `psycopg2`, including maps, result drill-down, and historical comparisons.

## Source Data

The CNE files should be in:

```text
data/raw/cne/al2013_mapaoficial_retif/
data/raw/cne/al2017_mapaoficial_retif02_01out2018/
data/raw/cne/2021al_mapa_oficial/
data/raw/cne/2025al-mapa-oficial_retificado/
```

The ETL uses the logical CNE maps present in each package:

- `mapa_1_resultados*.xlsx`, `Parte1_resultados*.xlsx`, or converted legacy equivalent: registered voters, voters, blank/null votes, and votes per candidacy.
- `mapa_anexo*.xlsx` or `Parte4_anexo*.xlsx`: resolution of local `[A]..[G]` coalition and citizen-group labels.
- `mapa_2_perc_mandatos*.xlsx`, `Parte2_perc_mandatos*.xlsx`, or converted legacy equivalent: official percentages and mandates.
- `mapa_3_eleitos*.xlsx`, `Parte3_eleitos*.xlsx`, or converted legacy equivalent: elected members per territory, organ, and list.

For maps, use the DGT CAOP GeoPackages currently placed in:

```text
data/raw/caop/CAOP_Continente_2025-gpkg/
data/raw/caop/CAOP_RAM_2025-gpkg/
data/raw/caop/CAOP_RAA_2025-gpkg/
```

The assignment recommends CAOP 2021 to match the baseline election year. This project uses CAOP 2025 as a newer compatible DGT administrative-boundary dataset for all loaded elections; mention this choice in the report.

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

## Load Baseline CNE Election Data

Dry-run the parser first:

```bash
python3 etl/load_cne_2021.py --dry-run
```

Expected counts:

```text
result rows:       3729
candidate aliases: 2755
candidate votes:   12295
percent/mandates:  12295
elected members:   35491
```

Export processed CSV files for inspection:

```bash
python3 etl/load_cne_2021.py --dry-run --export-processed data/processed
```

Create schemas and load the baseline 2021 database:

```bash
python3 etl/load_cne_2021.py --setup --dsn "dbname=tabd" \
  --source-dir data/raw/cne/2021al_mapa_oficial \
  --election-code AL2021 \
  --election-name "Eleições Autárquicas 2021" \
  --election-date 2021-09-26
```

## Load Historical Election Data

The ETL can also load the 2013, 2017, and 2025 official CNE Autarquicas packages as separate elections.

Detected local folders:

```text
data/raw/cne/al2013_mapaoficial_retif/
data/raw/cne/al2017_mapaoficial_retif02_01out2018/
data/raw/cne/2021al_mapa_oficial/
data/raw/cne/2025al-mapa-oficial_retificado/
```

The 2013 and 2017 packages ship as legacy `.xls`/`.ods` files. Convert the `.xls` files once before loading:

```bash
libreoffice --headless --convert-to xlsx \
  --outdir data/raw/cne/al2013_mapaoficial_retif \
  data/raw/cne/al2013_mapaoficial_retif/*.xls

libreoffice --headless --convert-to xlsx \
  --outdir data/raw/cne/al2017_mapaoficial_retif02_01out2018 \
  data/raw/cne/al2017_mapaoficial_retif02_01out2018/*.xls
```

Then rebuild and load all four elections:

```bash
.venv/bin/python etl/load_cne_2021.py --setup --dsn "dbname=tabd" \
  --source-dir data/raw/cne/2021al_mapa_oficial \
  --election-code AL2021 \
  --election-name "Eleições Autárquicas 2021" \
  --election-date 2021-09-26

.venv/bin/python etl/load_cne_2021.py --dsn "dbname=tabd" \
  --source-dir data/raw/cne/al2013_mapaoficial_retif \
  --election-code AL2013 \
  --election-name "Eleições Autárquicas 2013" \
  --election-date 2013-09-29

.venv/bin/python etl/load_cne_2021.py --dsn "dbname=tabd" \
  --source-dir data/raw/cne/al2017_mapaoficial_retif02_01out2018 \
  --election-code AL2017 \
  --election-name "Eleições Autárquicas 2017" \
  --election-date 2017-10-01

.venv/bin/python etl/load_cne_2021.py --dsn "dbname=tabd" \
  --source-dir data/raw/cne/2025al-mapa-oficial_retificado \
  --election-code AL2025 \
  --election-name "Eleições Autárquicas 2025" \
  --election-date 2025-10-12

.venv/bin/python etl/load_caop.py --caop-dir data/raw/caop --dsn "dbname=tabd"
```

Run historical comparison queries:

```bash
psql -d tabd -f sql/08_historical_comparisons.sql
```

## Load CAOP Geometries

Inspect detected GeoPackage layers and columns:

```bash
.venv/bin/python etl/load_caop.py --caop-dir data/raw/caop --dry-run
```

Load geometries into `election.territories.geom`:

```bash
.venv/bin/python etl/load_caop.py --caop-dir data/raw/caop --dsn "dbname=tabd"
```

Expected loaded geometry coverage:

```text
district        20 / 21   # national aggregate has no polygon
municipality   308 / 308
parish        3241 / 3394   # after loading 2013, 2017, 2021, and 2025
```

## Run the Flask App

After the database is loaded:

```bash
.venv/bin/flask --app app/app.py run
```

Open:

```text
http://127.0.0.1:5000
http://127.0.0.1:5000/compare
```

The map will show data only after CAOP geometries are loaded. Before that, the app can still query election results directly by URL, for example:

```text
http://127.0.0.1:5000/results?election_code=AL2021&territory_code=010100&organ_code=CM
```

For `Assembleia de Freguesia`, open a municipality result page and select `Assembleia de Freguesia`; the page lists that municipality's freguesias. Click a freguesia to open its `AF` result page, for example:

```text
http://127.0.0.1:5000/results?election_code=AL2025&territory_code=010128&organ_code=AF
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
- `sql/08_historical_comparisons.sql`: historical comparison queries across 2013, 2017, 2021, and 2025.

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
- Parish geometry coverage is partial: 3241 / 3394 parish territories have geometry after the four-election CAOP load. The assignment minimum is still satisfied because district/region and municipality geometries are fully loaded.
- Some elected-member rows do not match normalized candidacies exactly. The difference comes from parish-level elected-member labels/codes. Vote, turnout, mandate, D'Hondt, warehouse, and municipality-level analyses are unaffected.
- The official AL2013 package has one parish-level turnout anomaly: Covelas, Povoa de Lanhoso, AF reports 420 registered voters and 422 voters. The loader preserves the official values and documents this as source-data quality.
- The project supports multiple local-election years, but not multiple election types such as legislative or presidential elections.

## Deliverables Status

- `sql/`: DDL, warehouse, functions, views, triggers, analytical queries, validation queries, historical comparison queries.
- `etl/`: CNE and CAOP loaders.
- `app/`: Flask frontend using `psycopg2`, including map, municipality drill-down, and historical comparison pages.
- `docs/report.tex` and `docs/report.pdf`: two-column report with TikZ diagrams.
- `docs/screenshots/`: frontend screenshots.
- `slides/presentation.tex` and `slides/presentation.pdf`: oral presentation source/PDF.
