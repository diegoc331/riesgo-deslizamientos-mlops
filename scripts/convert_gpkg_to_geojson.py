"""
Convierte el GeoPackage de cuencas HydroSHEDS nivel 10 a GeoJSON.

Uso:
    uv run python scripts/convert_gpkg_to_geojson.py

Genera:
    data/raw/spatial/cuencas_antioquia.geojson  (~2 MB)
"""

from pathlib import Path

import geopandas as gpd

GPKG = Path("data/raw/spatial/hydrobasins_antioquia_lev10.gpkg")
OUT = Path("data/raw/spatial/cuencas_antioquia.geojson")


def main() -> None:
    print(f"Leyendo {GPKG}...")
    gdf = gpd.read_file(GPKG)
    print(f"  {len(gdf)} cuencas cargadas. CRS original: {gdf.crs}")

    cols = [
        c
        for c in ["HYBAS_ID", "SUB_AREA", "UP_AREA", "DIST_MAIN", "ORDER", "geometry"]
        if c in gdf.columns
    ]
    gdf = gdf[cols].to_crs(epsg=4326)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUT, driver="GeoJSON")
    size_mb = OUT.stat().st_size / 1_048_576
    print(f"GeoJSON guardado en {OUT} ({size_mb:.1f} MB, {len(gdf)} features)")


if __name__ == "__main__":
    main()
