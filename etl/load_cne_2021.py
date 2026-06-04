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


VALID_ORGANS = {"CM", "AM", "AF"}

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


@dataclass(frozen=True)
class CneSourceFiles:
    result_rows: Path
    percent_mandates: Path
    elected_members: Path
    aliases: Path


@dataclass(frozen=True)
class SheetLayout:
    code_col: int
    municipality_col: int
    parish_col: int
    organ_col: int


def normalize_code(value: str) -> str:
    if not value:
        return ""
    cleaned = value.split(".")[0].strip().upper()
    if cleaned.isdigit():
        return cleaned.zfill(6)
    if not cleaned.isalnum():
        return ""
    return cleaned


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


def candidate_group_for(candidate_ref: str) -> str:
    if candidate_ref in {"[D]", "[E]", "[F]", "[G]"}:
        return "citizen_group"
    if candidate_ref.startswith("[") or candidate_ref == "PCP-PEV":
        return "coalition"
    return "party"


def detect_sheet_layout(path: Path) -> SheetLayout:
    for row_number, row in XlsxReader(path).iter_rows():
        if row_number > 10:
            break
        for col_idx, value in row.items():
            cell = text_or_none(value)
            if cell and cell.upper() == "CÓD":
                return SheetLayout(
                    code_col=col_idx,
                    municipality_col=col_idx + 1,
                    parish_col=col_idx + 2,
                    organ_col=col_idx + 3,
                )
    raise ValueError(f"Could not detect CNE code/organ layout in {path}")


def split_alias_value(value: str):
    text = text_or_none(value)
    if not text:
        return None, None

    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()

    if " - " in text:
        sigla, name = text.split(" - ", 1)
    elif "-" in text:
        sigla, name = text.split("-", 1)
    else:
        return text_or_none(text), None

    return text_or_none(sigla), text_or_none(name)


def iter_header_candidates(path: Path, start_column: int, step: int):
    header_row = None
    for row_number, row in XlsxReader(path).iter_rows():
        if row_number > 10:
            break
        code_col = next(
            (
                col_idx for col_idx, value in row.items()
                if (text_or_none(value) or "").upper() == "CÓD"
            ),
            None,
        )
        if code_col is not None and text_or_none(row.get(start_column, "")):
            header_row = row
            break
    if header_row is None:
        raise ValueError(f"Could not find candidate header row in {path}")

    current = start_column
    while current <= max(header_row.keys(), default=0):
        label = text_or_none(header_row.get(current, ""))
        if not label:
            current += step
            continue
        if label.upper().startswith("[SIGLA"):
            break
        yield current, label, candidate_group_for(label)
        current += step


def detect_source_files(source_dir: Path) -> CneSourceFiles:
    xlsx_files = sorted(source_dir.glob("*.xlsx"))
    if not xlsx_files:
        raise FileNotFoundError(
            f"No .xlsx files found in {source_dir}. Convert .ods/.xls files to .xlsx first."
        )

    def choose(*needles: str) -> Path:
        matches = [
            path for path in xlsx_files
            if any(needle in path.name.lower() for needle in needles)
        ]
        if not matches:
            raise FileNotFoundError(
                f"Could not find an .xlsx file matching {needles} in {source_dir}"
            )
        return matches[0]

    return CneSourceFiles(
        result_rows=choose("mapa_1", "01-mapa", "mapa_i", "parte1"),
        percent_mandates=choose("mapa_2", "02-mapa", "mapa_ii", "parte2"),
        elected_members=choose("mapa_3", "03-mapa", "mapaiii", "mapa_iii", "parte3"),
        aliases=choose("anexo", "parte4"),
    )


def parse_anexo(path: Path, election_code: str):
    aliases = []
    alias_lookup = {}
    layout = detect_sheet_layout(path)

    header = {}
    for row_number, row in XlsxReader(path).iter_rows():
        if row_number > 10:
            break
        if (text_or_none(row.get(layout.code_col, "")) or "").upper() == "CÓD":
            header = row
            break

    inline_alias_columns = []
    for col_idx, value in header.items():
        label = text_or_none(value) or ""
        match = re.match(r"(\[[A-Z]\])\s+SIGLA", label.upper())
        if match:
            candidate_ref = match.group(1)
            inline_alias_columns.append((col_idx, candidate_ref, candidate_group_for(candidate_ref)))

    for row_number, row in XlsxReader(path).iter_rows():
        if row_number == 1:
            continue

        code = normalize_code(row.get(layout.code_col, ""))
        organ = text_or_none(row.get(layout.organ_col, ""))
        if not code or organ not in VALID_ORGANS:
            continue

        alias_columns = inline_alias_columns or ANEXO_COLUMNS
        for sigla_col, candidate_ref, candidate_group in alias_columns:
            if inline_alias_columns:
                sigla, name = split_alias_value(row.get(sigla_col, ""))
            else:
                sigla = text_or_none(row.get(sigla_col, ""))
                name = text_or_none(row.get(sigla_col + 1, ""))
            if not sigla and not name:
                continue

            record = (
                path.name,
                row_number,
                election_code,
                code,
                text_or_none(row.get(layout.municipality_col, "")),
                text_or_none(row.get(layout.parish_col, "")),
                organ,
                candidate_ref,
                candidate_group,
                sigla,
                name,
            )
            aliases.append(record)
            alias_lookup[(code, organ, candidate_ref)] = (sigla, name)

    return aliases, alias_lookup


def parse_resultados(path: Path, alias_lookup: dict, election_code: str):
    result_rows = []
    candidate_votes = []
    layout = detect_sheet_layout(path)
    vote_columns = list(iter_header_candidates(path, layout.organ_col + 5, 1))

    for row_number, row in XlsxReader(path).iter_rows():
        code = normalize_code(row.get(layout.code_col, ""))
        if not code:
            continue

        organ = text_or_none(row.get(layout.organ_col, ""))
        result_rows.append(
            (
                path.name,
                row_number,
                election_code,
                code,
                text_or_none(row.get(layout.municipality_col, "")),
                text_or_none(row.get(layout.parish_col, "")),
                organ,
                int_or_none(row.get(layout.organ_col + 1, "")),
                int_or_none(row.get(layout.organ_col + 2, "")),
                int_or_none(row.get(layout.organ_col + 3, "")),
                int_or_none(row.get(layout.organ_col + 4, "")),
            )
        )

        if organ not in VALID_ORGANS:
            continue

        for column, candidate_ref, candidate_group in vote_columns:
            votes = int_or_none(row.get(column, ""))
            if votes is None:
                continue
            resolved_sigla, resolved_name = alias_lookup.get((code, organ, candidate_ref), (candidate_ref, None))
            candidate_votes.append(
                (
                    path.name,
                    row_number,
                    election_code,
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


def parse_percent_mandates(path: Path, alias_lookup: dict, election_code: str):
    rows = []
    layout = detect_sheet_layout(path)
    percent_mandate_columns = list(iter_header_candidates(path, layout.organ_col + 1, 2))

    for row_number, row in XlsxReader(path).iter_rows():
        code = normalize_code(row.get(layout.code_col, ""))
        organ = text_or_none(row.get(layout.organ_col, ""))
        if not code or organ not in VALID_ORGANS:
            continue

        for percent_col, candidate_ref, candidate_group in percent_mandate_columns:
            vote_percent = decimal_or_none(row.get(percent_col, ""))
            mandates = int_or_none(row.get(percent_col + 1, ""))
            if vote_percent is None and mandates is None:
                continue
            resolved_sigla, resolved_name = alias_lookup.get((code, organ, candidate_ref), (candidate_ref, None))
            rows.append(
                (
                    path.name,
                    row_number,
                    election_code,
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


def parse_eleitos(path: Path, election_code: str):
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
    layout = detect_sheet_layout(path)

    for row_number, row in XlsxReader(path).iter_rows():
        if row_number <= 2:
            continue

        organ = text_or_none(row.get(layout.organ_col, ""))
        if organ in VALID_ORGANS:
            territory_code = normalize_code(row.get(layout.code_col, ""))
            municipality_name = text_or_none(row.get(layout.municipality_col, ""))
            parish_name = text_or_none(row.get(layout.parish_col, ""))
            organ_code = organ
            party_cols = {}
            position_counter = {}
            state = "need_parties"
            continue

        if state == "need_parties":
            compact_cells = []
            for col_idx, val in row.items():
                lines = [
                    text_or_none(line)
                    for line in str(val or "").splitlines()
                ]
                lines = [line for line in lines if line]
                if len(lines) > 1:
                    compact_cells.append((col_idx, lines))

            if compact_cells:
                for _col_idx, lines in compact_cells:
                    sigla = lines[0]
                    for position, name in enumerate(lines[1:], start=1):
                        elected.append((
                            path.name,
                            row_number,
                            election_code,
                            territory_code,
                            municipality_name,
                            parish_name,
                            organ_code,
                            sigla,
                            position,
                            name,
                        ))
                state = "looking"
                continue

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
                    path.name,
                    row_number,
                    election_code,
                    territory_code,
                    municipality_name,
                    parish_name,
                    organ_code,
                    sigla,
                    position_counter[col_idx],
                    name,
                ))

    return elected


def parse_cne(source_dir: Path, election_code: str) -> ParsedCneData:
    files = detect_source_files(source_dir)
    aliases, alias_lookup = parse_anexo(files.aliases, election_code)
    result_rows, candidate_votes = parse_resultados(files.result_rows, alias_lookup, election_code)
    percent_mandates = parse_percent_mandates(files.percent_mandates, alias_lookup, election_code)
    elected_members = parse_eleitos(files.elected_members, election_code)
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


def load_database(
    dsn: str,
    data: ParsedCneData,
    setup: bool,
    election_code: str,
    election_name: str,
    election_date: str,
    source_name: str,
):
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
                ALTER TABLE staging.cne_elected_members
                  DROP CONSTRAINT IF EXISTS cne_elected_members_pkey;
                ALTER TABLE staging.cne_elected_members
                  ADD CONSTRAINT cne_elected_members_pkey
                  PRIMARY KEY (source_file, source_row, election_code, candidate_sigla, list_position);
                """
            )
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

            cursor.execute(
                "CALL election.load_from_staging(%s, %s, %s::date, %s);",
                (election_code, election_name, election_date, source_name),
            )
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
    parser = argparse.ArgumentParser(description="Load CNE Autarquicas spreadsheets into PostgreSQL.")
    parser.add_argument("--source-dir", default="data/raw/cne/2021al_mapa_oficial", type=Path)
    parser.add_argument("--election-code", default="AL2021")
    parser.add_argument("--election-name", default="Eleições Autárquicas 2021")
    parser.add_argument("--election-date", default="2021-09-26")
    parser.add_argument("--source-name", default=None)
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--setup", action="store_true", help="Run SQL schema/function files before loading data.")
    parser.add_argument("--dry-run", action="store_true", help="Parse files and print counts without connecting to PostgreSQL.")
    parser.add_argument("--export-processed", type=Path, help="Write parsed CSV files to this directory.")
    args = parser.parse_args()

    source_name = args.source_name or f"CNE mapa oficial {args.election_code}"
    data = parse_cne(args.source_dir, args.election_code)
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

    load_database(
        args.dsn,
        data,
        args.setup,
        args.election_code,
        args.election_name,
        args.election_date,
        source_name,
    )
    print("database load completed")


if __name__ == "__main__":
    main()
