"""
Load CAOP 2021 administrative boundaries into election.territories.geom.

Usage:
    python3 etl/load_caop.py --caop-dir data/caop2021 --dsn postgresql://...

Expected shapefile layout inside --caop-dir:
    Cont_AAD_CAOP2021.shp   (or similar) - districts (Áreas de Distrito)
    Cont_Conc_CAOP2021.shp               - municipalities (Concelhos)
    Cont_Freg_CAOP2021.shp               - parishes (Freguesias)

The shapefile attribute names vary slightly by CAOP version.
Run with --dry-run first to print detected columns before committing.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

SRID = 3763  # PT-TM06 / ETRS89 — matches election.territories.geom


def _find_shapefile(directory: Path, keywords: list[str]) -> Path | None:
    for path in sorted(directory.glob("*.shp")):
        name_lower = path.stem.lower()
        if all(k in name_lower for k in keywords):
            return path
    return None


def _detect_code_column(gdf, candidates: list[str]) -> str:
    for col in candidates:
        if col in gdf.columns:
            return col
    raise ValueError(f"None of {candidates} found in columns: {list(gdf.columns)}")


def _detect_name_column(gdf, candidates: list[str]) -> str:
    for col in candidates:
        if col in gdf.columns:
            return col
    raise ValueError(f"None of {candidates} found in columns: {list(gdf.columns)}")


def _zero_pad(value: str, width: int = 6) -> str:
    cleaned = str(value).split(".")[0].strip().zfill(width)
    return cleaned


def load_caop(dsn: str, caop_dir: Path, dry_run: bool = False):
    try:
        import geopandas as gpd
        import psycopg2
    except ImportError as exc:
        raise SystemExit(
            "geopandas and psycopg2 are required. Install with: pip install geopandas psycopg2-binary"
        ) from exc

    caop_dir = Path(caop_dir)
    if not caop_dir.is_dir():
        raise SystemExit(f"CAOP directory not found: {caop_dir}")

    # --- Locate shapefiles ---
    dist_shp = _find_shapefile(caop_dir, ["aad"]) or _find_shapefile(caop_dir, ["dist"])
    conc_shp = _find_shapefile(caop_dir, ["conc"])
    freg_shp = _find_shapefile(caop_dir, ["freg"])

    if not conc_shp:
        raise SystemExit(
            f"Could not find municipality shapefile in {caop_dir}. "
            "Expected a file with 'conc' in the name (e.g. Cont_Conc_CAOP2021.shp)."
        )

    print(f"Districts shapefile : {dist_shp}")
    print(f"Municipalities      : {conc_shp}")
    print(f"Parishes            : {freg_shp}")

    # --- Load and reproject to SRID 3763 ---
    def load_shp(path):
        gdf = gpd.read_file(path)
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        if gdf.crs.to_epsg() != SRID:
            gdf = gdf.to_crs(epsg=SRID)
        return gdf

    # --- Municipalities (mandatory) ---
    conc_gdf = load_shp(conc_shp)
    print(f"\nMunicipality columns: {list(conc_gdf.columns)}")

    conc_code_col = _detect_code_column(conc_gdf, ["Dicofre", "DICOFRE", "CodMunic", "CODMUN", "COD_MUN", "DICO"])
    conc_name_col = _detect_name_column(conc_gdf, ["Concelho", "CONCELHO", "Designacao", "DESIGNACAO", "Nome", "NOME"])

    # Municipality codes in CAOP are 4-digit (DDMM); pad to 6 digits (DDMM00)
    conc_gdf["territory_code"] = conc_gdf[conc_code_col].apply(
        lambda v: _zero_pad(str(v)[:4], 4) + "00"
    )
    conc_gdf["territory_name"] = conc_gdf[conc_name_col].str.strip()

    if dry_run:
        print("\nMunicipality sample:")
        print(conc_gdf[["territory_code", "territory_name"]].head(10).to_string(index=False))

    # --- Districts (optional — derive from municipalities if shapefile missing) ---
    if dist_shp:
        dist_gdf = load_shp(dist_shp)
        print(f"\nDistrict columns: {list(dist_gdf.columns)}")
        dist_code_col = _detect_code_column(dist_gdf, ["Codigo", "CODIGO", "CodDist", "CODDIST", "Dico", "DICO"])
        dist_name_col = _detect_name_column(dist_gdf, ["Distrito", "DISTRITO", "Designacao", "DESIGNACAO", "Nome", "NOME"])
        dist_gdf["territory_code"] = dist_gdf[dist_code_col].apply(
            lambda v: _zero_pad(str(v)[:2], 2) + "0000"
        )
        dist_gdf["territory_name"] = dist_gdf[dist_name_col].str.strip()
        if dry_run:
            print("\nDistrict sample:")
            print(dist_gdf[["territory_code", "territory_name"]].head(5).to_string(index=False))
    else:
        dist_gdf = None
        print("\nNo district shapefile found — district geometries will be dissolved from municipalities.")

    # --- Parishes (optional) ---
    if freg_shp:
        freg_gdf = load_shp(freg_shp)
        print(f"\nParish columns: {list(freg_gdf.columns)}")
        freg_code_col = _detect_code_column(freg_gdf, ["Dicofre", "DICOFRE", "Dico", "DICO", "CodFreg", "CODFREG"])
        freg_name_col = _detect_name_column(freg_gdf, ["Freguesia", "FREGUESIA", "Designacao", "DESIGNACAO", "Nome", "NOME"])
        freg_gdf["territory_code"] = freg_gdf[freg_code_col].apply(
            lambda v: _zero_pad(str(v), 6)
        )
        freg_gdf["territory_name"] = freg_gdf[freg_name_col].str.strip()
        if dry_run:
            print("\nParish sample:")
            print(freg_gdf[["territory_code", "territory_name"]].head(5).to_string(index=False))
    else:
        freg_gdf = None
        print("\nNo parish shapefile found — parish geometries will not be loaded.")

    if dry_run:
        print("\nDry run complete. Re-run without --dry-run to load into PostgreSQL.")
        return

    # --- Write to PostgreSQL ---
    from shapely.wkb import dumps as wkb_dumps

    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    cur = conn.cursor()

    def update_geom(gdf, code_col="territory_code"):
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
                SET geom = %s::geometry
                WHERE territory_code = %s
                """,
                (wkb, row[code_col]),
            )
            updated += cur.rowcount
            if cur.rowcount == 0:
                skipped += 1
        return updated, skipped

    print("\nUpdating municipality geometries...")
    u, s = update_geom(conc_gdf)
    print(f"  updated={u}  skipped/unmatched={s}")

    if dist_gdf is not None:
        print("Updating district geometries...")
        u, s = update_geom(dist_gdf)
        print(f"  updated={u}  skipped/unmatched={s}")
    else:
        print("Dissolving district geometries from municipalities...")
        dist_dissolved = conc_gdf.copy()
        dist_dissolved["dist_code"] = dist_dissolved["territory_code"].str[:2] + "0000"
        dist_dissolved = dist_dissolved.dissolve(by="dist_code", as_index=False)[["dist_code", "geometry"]]
        dist_dissolved.rename(columns={"dist_code": "territory_code"}, inplace=True)
        u, s = update_geom(dist_dissolved)
        print(f"  updated={u}  skipped/unmatched={s}")

    if freg_gdf is not None:
        print("Updating parish geometries...")
        u, s = update_geom(freg_gdf)
        print(f"  updated={u}  skipped/unmatched={s}")

    conn.commit()
    cur.close()
    conn.close()
    print("\nCAOP geometry load complete.")


def main():
    parser = argparse.ArgumentParser(description="Load CAOP 2021 boundaries into election.territories.geom.")
    parser.add_argument("--caop-dir", default="data/caop2021", type=Path,
                        help="Directory containing CAOP shapefiles (default: data/caop2021)")
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"),
                        help="PostgreSQL DSN (or set DATABASE_URL env var)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print detected columns and sample data without touching the database")
    args = parser.parse_args()

    if not args.dry_run and not args.dsn:
        raise SystemExit("Missing --dsn or DATABASE_URL. Use --dry-run to inspect without connecting.")

    load_caop(args.dsn, args.caop_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
