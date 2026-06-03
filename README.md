# Election Analytics Platform for Portugal

Database-centred project for the Advanced Topics in Databases practical assignment.

Current scope:

- Official CNE Autarquicas 2021 spreadsheet package.
- Staging schema for raw Excel-derived rows.
- Normalized operational schema for elections, organs, territories, candidacies, turnout, votes, and mandates.
- Data warehouse schema for analytical queries.
- PL/pgSQL routines, triggers, views, and D'Hondt allocation function.

## Source Data

Place the CNE files in:

```text
2021al_mapa_oficial/
```

The ETL currently uses:

- `mapa_1_resultados.xlsx`: votes, registered voters, turnout, blank votes, null votes.
- `mapa_anexo.xlsx`: resolution of `[A]..[G]` local coalition and citizen-group labels.
- `mapa_2_perc_mandatos.xlsx`: official vote percentages and mandates.

CAOP 2021 boundaries still need to be added for PostGIS map geometries.

## Setup

Create a PostgreSQL database with PostGIS available, then install Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set a connection string:

```bash
export DATABASE_URL="postgresql://USER:PASSWORD@localhost:5432/tabd"
```

Run the full schema setup and CNE load:

```bash
python3 etl/load_cne_2021.py --setup
```

To only test the spreadsheet parser without touching the database:

```bash
python3 etl/load_cne_2021.py --dry-run
```

Expected parser counts with the current CNE files:

```text
result rows:       3719
candidate aliases: 2755
candidate votes:   12277
percent/mandates:  12277
```

To export processed CSV files for inspection:

```bash
python3 etl/load_cne_2021.py --dry-run --export-processed data/processed
```

## SQL Files

- `sql/00_extensions_and_schemas.sql`: PostGIS extension and schema reset.
- `sql/01_staging_schema.sql`: raw CNE staging tables.
- `sql/02_operational_schema.sql`: normalized operational model.
- `sql/03_warehouse_schema.sql`: star-schema warehouse.
- `sql/04_functions_views_triggers.sql`: PL/pgSQL routines, triggers, views, turnout/vote-share functions, D'Hondt function.
- `sql/05_analytical_queries.sql`: required analytical query examples.

## Next Work

1. Add CAOP 2021 shapefiles and load municipality geometries into `election.territories.geom`.
2. Build the Flask frontend on top of explicit SQL queries.
3. Add report diagrams and screenshots.
4. Validate D'Hondt outputs against `mapa_2_perc_mandatos.xlsx`.
