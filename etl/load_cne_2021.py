from __future__ import annotations

import argparse
import csv
import io
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from xlsx_reader import XlsxReader


ELECTION_CODE = "AL2021"
ELECTION_NAME = "Eleições Autárquicas 2021"
VALID_ORGANS = {"CM", "AM", "AF"}

PARTY_LABELS = [
    "A",
    "B.E.",
    "CDS-PP",
    "CH",
    "E",
    "IL",
    "JPP",
    "L",
    "MAS",
    "MPT",
    "NC",
    "PAN",
    "PCTP/MRPP",
    "PDR",
    "PPD/PSD",
    "PPM",
    "PS",
    "PTP",
    "R.I.R.",
    "VP",
]

VOTE_COLUMNS = (
    [(9 + index, label, "party") for index, label in enumerate(PARTY_LABELS)]
    + [(29, "PCP-PEV", "coalition"), (30, "[A]", "coalition"), (31, "[B]", "coalition"), (32, "[C]", "coalition")]
    + [(33, "[D]", "citizen_group"), (34, "[E]", "citizen_group"), (35, "[F]", "citizen_group"), (36, "[G]", "citizen_group")]
)

PERCENT_MANDATE_COLUMNS = (
    [(5 + 2 * index, label, "party") for index, label in enumerate(PARTY_LABELS)]
    + [(45, "PCP-PEV", "coalition"), (47, "[A]", "coalition"), (49, "[B]", "coalition"), (51, "[C]", "coalition")]
    + [(53, "[D]", "citizen_group"), (55, "[E]", "citizen_group"), (57, "[F]", "citizen_group"), (59, "[G]", "citizen_group")]
)

ANEXO_COLUMNS = [
    (5, "[A]", "coalition"),
    (7, "[B]", "coalition"),
    (9, "[C]", "coalition"),
    (11, "[D]", "citizen_group"),
    (13, "[E]", "citizen_group"),
    (15, "[F]", "citizen_group"),
    (17, "[G]", "citizen_group"),
]


@dataclass(frozen=True)
class ParsedCneData:
    result_rows: list[tuple]
    candidate_votes: list[tuple]
    candidate_aliases: list[tuple]
    percent_mandates: list[tuple]
    elected_members: list[tuple]


def normalize_code(value: str) -> str:
    if not value:
        return ""
    cleaned = value.split(".")[0].strip()
    if not cleaned.isdigit():
        return ""
    return cleaned.zfill(6)


def text_or_none(value: str):
    value = re.sub(r"\s+", " ", (value or "")).strip()
    return value or None


def int_or_none(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(Decimal(value))
    except (InvalidOperation, ValueError):
        return None


def decimal_or_none(value: str):
    value = (value or "").strip().replace(",", ".")
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def parse_anexo(path: Path):
    aliases = []
    alias_lookup = {}

    for row_number, row in XlsxReader(path).iter_rows():
        if row_number == 1:
            continue

        code = normalize_code(row.get(1, ""))
        organ = text_or_none(row.get(4, ""))
        if not code or organ not in VALID_ORGANS:
            continue

        for sigla_col, candidate_ref, candidate_group in ANEXO_COLUMNS:
            sigla = text_or_none(row.get(sigla_col, ""))
            name = text_or_none(row.get(sigla_col + 1, ""))
            if not sigla and not name:
                continue

            record = (
                "mapa_anexo.xlsx",
                row_number,
                ELECTION_CODE,
                code,
                text_or_none(row.get(2, "")),
                text_or_none(row.get(3, "")),
                organ,
                candidate_ref,
                candidate_group,
                sigla,
                name,
            )
            aliases.append(record)
            alias_lookup[(code, organ, candidate_ref)] = (sigla, name)

    return aliases, alias_lookup


def parse_resultados(path: Path, alias_lookup: dict):
    result_rows = []
    candidate_votes = []

    for row_number, row in XlsxReader(path).iter_rows():
        code = normalize_code(row.get(1, ""))
        if not code:
            continue

        organ = text_or_none(row.get(4, ""))
        result_rows.append(
            (
                "mapa_1_resultados.xlsx",
                row_number,
                ELECTION_CODE,
                code,
                text_or_none(row.get(2, "")),
                text_or_none(row.get(3, "")),
                organ,
                int_or_none(row.get(5, "")),
                int_or_none(row.get(6, "")),
                int_or_none(row.get(7, "")),
                int_or_none(row.get(8, "")),
            )
        )

        if organ not in VALID_ORGANS:
            continue

        for column, candidate_ref, candidate_group in VOTE_COLUMNS:
            votes = int_or_none(row.get(column, ""))
            if votes is None:
                continue
            resolved_sigla, resolved_name = alias_lookup.get((code, organ, candidate_ref), (candidate_ref, None))
            candidate_votes.append(
                (
                    "mapa_1_resultados.xlsx",
                    row_number,
                    ELECTION_CODE,
                    code,
                    organ,
                    candidate_ref,
                    candidate_group,
                    resolved_sigla,
                    resolved_name,
                    votes,
                )
            )

    return result_rows, candidate_votes


def parse_percent_mandates(path: Path, alias_lookup: dict):
    rows = []

    for row_number, row in XlsxReader(path).iter_rows():
        code = normalize_code(row.get(1, ""))
        organ = text_or_none(row.get(4, ""))
        if not code or organ not in VALID_ORGANS:
            continue

        for percent_col, candidate_ref, candidate_group in PERCENT_MANDATE_COLUMNS:
            vote_percent = decimal_or_none(row.get(percent_col, ""))
            mandates = int_or_none(row.get(percent_col + 1, ""))
            if vote_percent is None and mandates is None:
                continue
            resolved_sigla, resolved_name = alias_lookup.get((code, organ, candidate_ref), (candidate_ref, None))
            rows.append(
                (
                    "mapa_2_perc_mandatos.xlsx",
                    row_number,
                    ELECTION_CODE,
                    code,
                    organ,
                    candidate_ref,
                    candidate_group,
                    resolved_sigla,
                    resolved_name,
                    vote_percent,
                    mandates,
                )
            )

    return rows


def parse_eleitos(path: Path):
    """
    Parse mapa_3_eleitos.xlsx (elected members list).

    The file uses a repeating block structure:
    - Territory row: col4 = organ code (CM/AM/AF), col1 = code, col2 = municipality, col3 = parish
    - Party header row: immediately follows, col1..N = resolved party/coalition siglas
    - Name rows: one elected member per party column, in list order, until next territory row
    """
    elected = []
    territory_code = None
    municipality_name = None
    parish_name = None
    organ_code = None
    party_cols: dict[int, str] = {}
    position_counter: dict[int, int] = {}
    state = "looking"

    for row_number, row in XlsxReader(path).iter_rows():
        if row_number <= 2:
            continue

        organ = text_or_none(row.get(4, ""))
        if organ in VALID_ORGANS:
            territory_code = normalize_code(row.get(1, ""))
            municipality_name = text_or_none(row.get(2, ""))
            parish_name = text_or_none(row.get(3, ""))
            organ_code = organ
            party_cols = {}
            position_counter = {}
            state = "need_parties"
            continue

        if state == "need_parties":
            for col_idx, val in row.items():
                sigla = text_or_none(val)
                if sigla:
                    party_cols[col_idx] = sigla
                    position_counter[col_idx] = 0
            state = "in_members"
            continue

        if state == "in_members" and territory_code:
            for col_idx, sigla in party_cols.items():
                name = text_or_none(row.get(col_idx, ""))
                if not name:
                    continue
                position_counter[col_idx] += 1
                elected.append((
                    "mapa_3_eleitos.xlsx",
                    row_number,
                    ELECTION_CODE,
                    territory_code,
                    municipality_name,
                    parish_name,
                    organ_code,
                    sigla,
                    position_counter[col_idx],
                    name,
                ))

    return elected


def parse_cne_2021(source_dir: Path) -> ParsedCneData:
    aliases, alias_lookup = parse_anexo(source_dir / "mapa_anexo.xlsx")
    result_rows, candidate_votes = parse_resultados(source_dir / "mapa_1_resultados.xlsx", alias_lookup)
    percent_mandates = parse_percent_mandates(source_dir / "mapa_2_perc_mandatos.xlsx", alias_lookup)
    elected_members = parse_eleitos(source_dir / "mapa_3_eleitos.xlsx")
    return ParsedCneData(result_rows, candidate_votes, aliases, percent_mandates, elected_members)


def copy_rows(cursor, table: str, columns: list[str], rows: list[tuple]):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    buffer.seek(0)
    column_sql = ", ".join(columns)
    cursor.copy_expert(f"COPY {table} ({column_sql}) FROM STDIN WITH (FORMAT csv)", buffer)


def execute_sql_files(connection, paths: list[Path]):
    with connection.cursor() as cursor:
        for path in paths:
            cursor.execute(path.read_text(encoding="utf-8"))
    connection.commit()


def load_database(dsn: str, data: ParsedCneData, setup: bool):
    try:
        import psycopg2
    except ImportError as exc:
        raise SystemExit("psycopg2 is not installed. Install psycopg2-binary or psycopg2 to load PostgreSQL.") from exc

    repo_root = Path(__file__).resolve().parents[1]
    sql_files = [
        repo_root / "sql" / "00_extensions_and_schemas.sql",
        repo_root / "sql" / "01_staging_schema.sql",
        repo_root / "sql" / "02_operational_schema.sql",
        repo_root / "sql" / "03_warehouse_schema.sql",
        repo_root / "sql" / "04_functions_views_triggers.sql",
        repo_root / "sql" / "06_materialized_views.sql",
    ]

    with psycopg2.connect(dsn) as connection:
        if setup:
            execute_sql_files(connection, sql_files)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                TRUNCATE
                    staging.cne_elected_members,
                    staging.cne_percent_mandates,
                    staging.cne_candidate_aliases,
                    staging.cne_candidate_votes,
                    staging.cne_result_rows
                RESTART IDENTITY;
                """
            )

            copy_rows(
                cursor,
                "staging.cne_result_rows",
                [
                    "source_file",
                    "source_row",
                    "election_code",
                    "territory_code",
                    "municipality_name",
                    "parish_name",
                    "organ_code",
                    "registered_voters",
                    "voters",
                    "blank_votes",
                    "null_votes",
                ],
                data.result_rows,
            )
            copy_rows(
                cursor,
                "staging.cne_candidate_aliases",
                [
                    "source_file",
                    "source_row",
                    "election_code",
                    "territory_code",
                    "municipality_name",
                    "parish_name",
                    "organ_code",
                    "candidate_ref",
                    "candidate_group",
                    "resolved_sigla",
                    "resolved_name",
                ],
                data.candidate_aliases,
            )
            copy_rows(
                cursor,
                "staging.cne_candidate_votes",
                [
                    "source_file",
                    "source_row",
                    "election_code",
                    "territory_code",
                    "organ_code",
                    "candidate_ref",
                    "candidate_group",
                    "resolved_sigla",
                    "resolved_name",
                    "votes",
                ],
                data.candidate_votes,
            )
            copy_rows(
                cursor,
                "staging.cne_percent_mandates",
                [
                    "source_file",
                    "source_row",
                    "election_code",
                    "territory_code",
                    "organ_code",
                    "candidate_ref",
                    "candidate_group",
                    "resolved_sigla",
                    "resolved_name",
                    "vote_percent",
                    "mandates",
                ],
                data.percent_mandates,
            )

            copy_rows(
                cursor,
                "staging.cne_elected_members",
                [
                    "source_file",
                    "source_row",
                    "election_code",
                    "territory_code",
                    "municipality_name",
                    "parish_name",
                    "organ_code",
                    "candidate_sigla",
                    "list_position",
                    "member_name",
                ],
                data.elected_members,
            )

            cursor.execute("CALL election.load_from_staging();")
            cursor.execute("CALL dw.refresh_from_operational();")

        connection.commit()


def export_processed(data: ParsedCneData, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "cne_result_rows.csv": data.result_rows,
        "cne_candidate_aliases.csv": data.candidate_aliases,
        "cne_candidate_votes.csv": data.candidate_votes,
        "cne_percent_mandates.csv": data.percent_mandates,
        "cne_elected_members.csv": data.elected_members,
    }
    for filename, rows in files.items():
        with (output_dir / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Load CNE Autarquicas 2021 spreadsheets into PostgreSQL.")
    parser.add_argument("--source-dir", default="2021al_mapa_oficial", type=Path)
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--setup", action="store_true", help="Run SQL schema/function files before loading data.")
    parser.add_argument("--dry-run", action="store_true", help="Parse files and print counts without connecting to PostgreSQL.")
    parser.add_argument("--export-processed", type=Path, help="Write parsed CSV files to this directory.")
    args = parser.parse_args()

    data = parse_cne_2021(args.source_dir)
    print(f"result rows:       {len(data.result_rows)}")
    print(f"candidate aliases: {len(data.candidate_aliases)}")
    print(f"candidate votes:   {len(data.candidate_votes)}")
    print(f"percent/mandates:  {len(data.percent_mandates)}")
    print(f"elected members:   {len(data.elected_members)}")

    if args.export_processed:
        export_processed(data, args.export_processed)
        print(f"processed CSV files written to {args.export_processed}")

    if args.dry_run:
        return

    if not args.dsn:
        raise SystemExit("Missing --dsn or DATABASE_URL. Use --dry-run to parse without loading PostgreSQL.")

    load_database(args.dsn, data, args.setup)
    print("database load completed")


if __name__ == "__main__":
    main()
