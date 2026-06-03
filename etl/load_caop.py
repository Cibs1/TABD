"""
Load CAOP administrative boundaries into election.territories.geom.

Supports DGT CAOP GeoPackage files such as:
    Continente_CAOP2025.gpkg
    ArqMadeira_CAOP2025.gpkg
    ArqAcores_GCentral_GOriental_CAOP2025.gpkg
    ArqAcores_GOcidental_CAOP2025.gpkg

The assignment recommends CAOP 2021 for the 2021 election. CAOP 2025 is still
usable if the report explicitly states it was chosen as a newer compatible DGT
boundary dataset.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

SRID = 3763  # PT-TM06 / ETRS89, used by election.territories.geom.


def _zero_pad(value: str, width: int) -> str:
    return str(value).split(".")[0].strip().zfill(width)


def _district_code_from_dt(value: str) -> str:
    code = _zero_pad(value, 2)
    if code in {"31", "32"}:
        return "300000"
    if "41" <= code <= "49":
        return "400000"
    return code + "0000"


def _district_name_from_code(code: str, original_name: str) -> str:
    if code == "300000":
        return "R.A. Madeira"
    if code == "400000":
        return "R.A. Açores"
    return original_name


def _vector_files(directory: Path) -> list[Path]:
    files = []
    for suffix in ("*.gpkg", "*.shp"):
        for path in directory.rglob(suffix):
            if any(part in {".venv", "venv", "__pycache__"} for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def _matching_layers(path: Path, keyword: str) -> list[str | None]:
    if path.suffix.lower() == ".shp":
        return [None] if keyword in path.stem.lower() else []

    import pyogrio

    layers = pyogrio.list_layers(path)
    return [
        layer_name
        for layer_name, geometry_type in layers
        if geometry_type is not None and keyword in layer_name.lower()
    ]


def _read_layers(files: list[Path], keyword: str):
    import geopandas as gpd
    import pandas as pd

    frames = []
    for path in files:
        for layer in _matching_layers(path, keyword):
            label = f"{path.name}:{layer}" if layer else path.name
            print(f"Reading {label}")
            frame = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
            if frame.empty:
                continue
            frame = _to_project_srid(frame)
            frames.append(frame)

    if not frames:
        return None

    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)


def _to_project_srid(gdf):
    if gdf.crs is None:
        raise ValueError("CAOP layer has no CRS; cannot safely load geometries.")
    if gdf.crs.to_epsg() != SRID:
        return gdf.to_crs(epsg=SRID)
    return gdf


def _detect_column(gdf, candidates: list[str]) -> str:
    lower_map = {col.lower(): col for col in gdf.columns}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    raise ValueError(f"None of {candidates} found in columns: {list(gdf.columns)}")


def _prepare_municipalities(gdf):
    gdf = _to_project_srid(gdf)
    code_col = _detect_column(gdf, ["dtmn", "dicofre", "codmun", "cod_mun"])
    name_col = _detect_column(gdf, ["municipio", "concelho", "nome", "designacao"])
    out = gdf.copy()
    out["territory_code"] = out[code_col].apply(lambda value: _zero_pad(str(value)[:4], 4) + "00")
    out["territory_name"] = out[name_col].astype(str).str.strip()
    out = out.dissolve(by=["territory_code", "territory_name"], as_index=False)
    return out[["territory_code", "territory_name", "geometry"]]


def _prepare_districts(gdf):
    gdf = _to_project_srid(gdf)
    code_col = _detect_column(gdf, ["dt", "codigo", "coddist"])
    name_col = _detect_column(gdf, ["distrito", "distrito_ilha", "nome", "designacao"])
    out = gdf.copy()
    out["territory_code"] = out[code_col].apply(_district_code_from_dt)
    out["territory_name"] = [
        _district_name_from_code(code, name)
        for code, name in zip(out["territory_code"], out[name_col].astype(str).str.strip(), strict=False)
    ]
    out = out.dissolve(by=["territory_code", "territory_name"], as_index=False)
    return out[["territory_code", "territory_name", "geometry"]]


def _prepare_parishes(gdf):
    gdf = _to_project_srid(gdf)
    code_col = _detect_column(gdf, ["dtmnfr", "dicofre", "codfreg"])
    name_col = _detect_column(gdf, ["freguesia", "nome", "designacao"])
    out = gdf.copy()
    out["territory_code"] = out[code_col].apply(lambda value: _zero_pad(value, 6))
    out["territory_name"] = out[name_col].astype(str).str.strip()
    out = out.dissolve(by=["territory_code", "territory_name"], as_index=False)
    return out[["territory_code", "territory_name", "geometry"]]


def load_caop(dsn: str | None, caop_dir: Path, dry_run: bool = False):
    try:
        import psycopg2
        from shapely.wkb import dumps as wkb_dumps
    except ImportError as exc:
        raise SystemExit("psycopg2 and shapely are required. Install project requirements first.") from exc

    caop_dir = Path(caop_dir)
    files = _vector_files(caop_dir)
    if not files:
        raise SystemExit(f"No .gpkg or .shp files found under {caop_dir}")

    print("CAOP files:")
    for path in files:
        print(f"  {path}")

    municipalities_raw = _read_layers(files, "municipios")
    districts_raw = _read_layers(files, "distritos")
    parishes_raw = _read_layers(files, "freguesias")

    if municipalities_raw is None:
        raise SystemExit("No municipality layer found. Expected a layer containing 'municipios'.")

    municipalities = _prepare_municipalities(municipalities_raw)
    districts = _prepare_districts(districts_raw) if districts_raw is not None else None
    parishes = _prepare_parishes(parishes_raw) if parishes_raw is not None else None

    print(f"\nPrepared municipalities: {len(municipalities)}")
    print(municipalities[["territory_code", "territory_name"]].head(10).to_string(index=False))

    if districts is not None:
        print(f"\nPrepared districts/regions: {len(districts)}")
        print(districts[["territory_code", "territory_name"]].to_string(index=False))
    else:
        print("\nNo district layers found; districts/regions will be dissolved from municipalities.")
        districts = municipalities.copy()
        districts["territory_code"] = districts["territory_code"].str[:2].apply(_district_code_from_dt)
        districts["territory_name"] = districts["territory_code"].map({
            "300000": "R.A. Madeira",
            "400000": "R.A. Açores",
        }).fillna(districts["territory_code"].str[:2])
        districts = districts.dissolve(by=["territory_code", "territory_name"], as_index=False)
        districts = districts[["territory_code", "territory_name", "geometry"]]

    if parishes is not None:
        print(f"\nPrepared parishes: {len(parishes)}")
        print(parishes[["territory_code", "territory_name"]].head(10).to_string(index=False))
    else:
        print("\nNo parish layers found; parish geometries will not be loaded.")

    if dry_run:
        print("\nDry run complete. Re-run without --dry-run to update PostGIS geometries.")
        return

    if not dsn:
        raise SystemExit("Missing --dsn or DATABASE_URL.")

    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    cur = conn.cursor()

    def update_geom(gdf, label: str):
        updated = 0
        skipped = 0
        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                skipped += 1
                continue
            wkb = wkb_dumps(geom, hex=True, include_srid=True, srid=SRID)
            cur.execute(
                """
                UPDATE election.territories
                SET geom = ST_Multi(%s::geometry)
                WHERE territory_code = %s
                """,
                (wkb, row["territory_code"]),
            )
            updated += cur.rowcount
            if cur.rowcount == 0:
                skipped += 1
        print(f"{label}: updated={updated} skipped/unmatched={skipped}")

    update_geom(municipalities, "Municipalities")
    update_geom(districts, "Districts/regions")
    if parishes is not None:
        update_geom(parishes, "Parishes")

    conn.commit()
    cur.close()
    conn.close()
    print("\nCAOP geometry load complete.")


def main():
    parser = argparse.ArgumentParser(description="Load CAOP boundaries into election.territories.geom.")
    parser.add_argument("--caop-dir", default=".", type=Path)
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    load_caop(args.dsn, args.caop_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
