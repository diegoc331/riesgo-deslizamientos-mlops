"""
Operaciones espaciales para el pipeline de deslizamientos (Fase 2).

Módulo responsable de:
  - Descargar límite departamental de Antioquia (GADM v4.1)
  - Descargar cuencas HydroSHEDS nivel 5 para Antioquia (HydroBASINS)
  - Descargar inventario SGC-SIMMA de movimientos en masa
  - Asignar eventos puntuales a cuencas por intersección espacial
  - Construir grid (semana × cuenca) con etiquetas binarias
  - Generar pseudo-ausencias defensibles para la clase negativa

Granularidad objetivo: (anio_semana, HYBAS_ID) — ~300 cuencas × 204 semanas
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

RAW_DIR   = Path(__file__).parents[2] / "data" / "raw"
SPATIAL_DIR = RAW_DIR / "spatial"


# =============================================================================
# Descarga de capas geográficas base
# =============================================================================

def download_antioquia_boundary() -> gpd.GeoDataFrame:
    """
    Descarga el límite departamental de Antioquia desde GADM v4.1.

    Fuente: https://gadm.org/
    Licencia: Libre para uso no comercial y académico.
    """
    cache = SPATIAL_DIR / "antioquia_boundary.gpkg"
    if cache.exists():
        return gpd.read_file(cache)

    SPATIAL_DIR.mkdir(parents=True, exist_ok=True)
    url = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_COL_1.json"
    print("Descargando límite departamental Colombia (GADM)...")
    r = requests.get(url, timeout=120)
    r.raise_for_status()

    gdf = gpd.read_file(io.BytesIO(r.content))
    antioquia = gdf[gdf["NAME_1"].str.lower() == "antioquia"].copy()

    if antioquia.empty:
        raise RuntimeError("No se encontró Antioquia en el GeoJSON de GADM.")

    antioquia.to_file(cache, driver="GPKG")
    print(f"Límite Antioquia guardado: {cache}")
    return antioquia


def download_hydrobasins(nivel: int = 5) -> gpd.GeoDataFrame:
    """
    Descarga HydroSHEDS HydroBASINS nivel {nivel} para Suramérica
    y recorta al polígono de Antioquia.

    Nivel 5 ≈ 100–500 km² por cuenca — balance entre resolución y volumen.
    Fuente : https://www.hydrosheds.org/products/hydrobasins
    Licencia: CC BY 4.0 — gratuita sin registro desde versión 1c.

    Columnas clave del resultado:
      HYBAS_ID  : identificador único de cuenca (int64)
      SUB_AREA  : área de la sub-cuenca (km²)
      UP_AREA   : área de drenaje acumulada aguas arriba (km²)
      DIST_MAIN : distancia al cauce principal (km)
      ORDER_    : orden de Strahler del cauce principal
    """
    cache = SPATIAL_DIR / f"hydrobasins_antioquia_lev{nivel:02d}.gpkg"
    if cache.exists():
        print(f"HydroBASINS cargado desde caché: {cache}")
        return gpd.read_file(cache)

    SPATIAL_DIR.mkdir(parents=True, exist_ok=True)
    url = (
        f"https://data.hydrosheds.org/file/hydrobasins/standard/"
        f"hybas_sa_lev{nivel:02d}_v1c.zip"
    )
    print(f"Descargando HydroBASINS nivel {nivel} Suramérica (~50 MB)...")
    r = requests.get(url, timeout=300)
    r.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        shp_name = next(n for n in zf.namelist() if n.endswith(".shp"))
        # Extraer todos los archivos del shapefile (shp, dbf, shx, prj)
        stem = Path(shp_name).stem
        for member in zf.namelist():
            if Path(member).stem == stem:
                zf.extract(member, SPATIAL_DIR)
        gdf_sa = gpd.read_file(SPATIAL_DIR / shp_name)

    antioquia = download_antioquia_boundary()
    gdf_sa = gdf_sa.to_crs(antioquia.crs)

    # Filtro rápido por bbox antes del clip preciso
    bbox = antioquia.total_bounds  # (minx, miny, maxx, maxy)
    gdf_bbox = gdf_sa.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
    gdf = gpd.clip(gdf_bbox, antioquia)
    gdf = gdf[gdf.geometry.area > 0].copy()

    gdf.to_file(cache, driver="GPKG")
    print(f"HydroBASINS Antioquia: {len(gdf)} cuencas → {cache}")
    return gdf


# =============================================================================
# Inventario SGC-SIMMA
# =============================================================================

def download_simma(max_records: int = 5_000) -> gpd.GeoDataFrame:
    """
    Descarga inventario de movimientos en masa SGC-SIMMA para Antioquia
    vía ArcGIS REST Feature Service.

    Portal  : https://datos.sgc.gov.co/datasets/312c8792ddb24954a9d2711bd89d1afe
    Método  : verificación por geólogos del SGC (campo + teledetección)
    Licencia: Datos Abiertos Colombia

    Ventaja sobre UNGRD: incluye eventos sin víctimas humanas
    (deslizamientos en vías o cultivos), reduciendo el sesgo de reportabilidad.
    """
    cache = SPATIAL_DIR / "simma_antioquia.gpkg"
    if cache.exists():
        print(f"SIMMA cargado desde caché: {cache}")
        return gpd.read_file(cache)

    SPATIAL_DIR.mkdir(parents=True, exist_ok=True)
    base_url = (
        "https://services.arcgis.com/uVJRNKDPKhBKqMoQ/arcgis/rest/services/"
        "Inventario_Movimientos_en_Masa/FeatureServer/0/query"
    )
    records = []
    offset = 0
    page_size = 2_000

    while len(records) < max_records:
        params = {
            "where":              "DEPARTAMEN='ANTIOQUIA'",
            "outFields":          "OBJECTID,FECHA_OCUR,MUNICIPIO,TIPO_MOVI,LATITUD,LONGITUD,FUENTE",
            "outSR":              "4326",
            "f":                  "json",
            "resultOffset":       offset,
            "resultRecordCount":  page_size,
        }
        resp = requests.get(base_url, params=params, timeout=60)
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if not features:
            break
        records.extend(f["attributes"] for f in features)
        print(f"  SIMMA: {len(records)} registros descargados")
        if len(features) < page_size:
            break
        offset += page_size

    df = pd.DataFrame(records)
    # FECHA_OCUR viene como epoch milliseconds
    df["fecha"] = pd.to_datetime(df["FECHA_OCUR"], unit="ms", errors="coerce")
    df = df.dropna(subset=["LATITUD", "LONGITUD", "fecha"])
    df = df[(df["LATITUD"] != 0) & (df["LONGITUD"] != 0)]

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["LONGITUD"], df["LATITUD"]),
        crs="EPSG:4326",
    )
    gdf.to_file(cache, driver="GPKG")
    print(f"SIMMA guardado: {len(gdf)} eventos → {cache}")
    return gdf


# =============================================================================
# Asignación de eventos a cuencas
# =============================================================================

def assign_events_to_cuencas(
    df_eventos: pd.DataFrame,
    gdf_cuencas: gpd.GeoDataFrame,
    lat_col: str = "LATITUD",
    lon_col: str = "LONGITUD",
) -> pd.DataFrame:
    """
    Asigna eventos puntuales a cuencas HydroSHEDS por intersección espacial.

    Eventos fuera de cualquier cuenca (coordenadas imprecisas o fuera de
    Antioquia) reciben HYBAS_ID = NaN y se descartan del resultado.

    Returns
    -------
    df_eventos enriquecido con columna HYBAS_ID (int64).
    """
    gdf_ev = gpd.GeoDataFrame(
        df_eventos.copy(),
        geometry=gpd.points_from_xy(df_eventos[lon_col], df_eventos[lat_col]),
        crs="EPSG:4326",
    ).to_crs(gdf_cuencas.crs)

    joined = gpd.sjoin(
        gdf_ev,
        gdf_cuencas[["HYBAS_ID", "geometry"]],
        how="left",
        predicate="within",
    )
    result = df_eventos.copy()
    result["HYBAS_ID"] = joined["HYBAS_ID"].values
    n_sin_cuenca = result["HYBAS_ID"].isna().sum()
    if n_sin_cuenca:
        print(f"  Eventos sin cuenca (fuera del polígono): {n_sin_cuenca} descartados")
    return result.dropna(subset=["HYBAS_ID"])


def build_event_grid(
    df_eventos: pd.DataFrame,
    gdf_cuencas: gpd.GeoDataFrame,
    anio_inicio: int = 2019,
    anio_fin: int = 2022,
) -> pd.DataFrame:
    """
    Construye el grid completo (semana × cuenca) con etiquetas binarias.

    Genera el producto cartesiano de todas las semanas ISO del período
    × todas las cuencas de Antioquia, y marca como 1 las celdas con
    al menos un evento UNGRD/SIMMA reportado.

    Returns
    -------
    DataFrame con [anio_semana, HYBAS_ID, n_eventos, deslizamiento]
    """
    df = df_eventos.copy()
    df["anio_semana"] = df["fecha"].dt.to_period("W")

    eventos_por_cuenca = (
        df.groupby(["anio_semana", "HYBAS_ID"])
        .size()
        .reset_index(name="n_eventos")
    )

    semanas = pd.period_range(
        start=f"{anio_inicio}-01-01",
        end=f"{anio_fin}-12-31",
        freq="W",
    )
    cuenca_ids = gdf_cuencas["HYBAS_ID"].unique()

    grid = pd.MultiIndex.from_product(
        [semanas, cuenca_ids], names=["anio_semana", "HYBAS_ID"]
    ).to_frame(index=False)

    grid = grid.merge(eventos_por_cuenca, on=["anio_semana", "HYBAS_ID"], how="left")
    grid["n_eventos"]     = grid["n_eventos"].fillna(0).astype(int)
    grid["deslizamiento"] = (grid["n_eventos"] > 0).astype(int)

    pct_positivos = 100 * grid["deslizamiento"].mean()
    print(
        f"Grid (semana × cuenca): {len(grid):,} instancias | "
        f"positivas: {grid['deslizamiento'].sum():,} ({pct_positivos:.2f}%)"
    )
    return grid


# =============================================================================
# Pseudo-ausencias defensibles
# =============================================================================

def generate_pseudo_absences(
    df_grid: pd.DataFrame,
    df_precip_semanal: pd.DataFrame,
    gdf_cuencas: gpd.GeoDataFrame,
    precip_percentil: float = 0.25,
    area_percentil: float = 0.25,
) -> pd.DataFrame:
    """
    Filtra el grid (semana × cuenca) para construir negativos confiables.

    Estrategia de 2 criterios combinados (Li et al., 2024, Sci. Reports):
      1. Precipitación: retiene como negativos solo semanas con
         precip_acum_14d ≤ P{precip_percentil*100} histórico departamental.
         Semanas de lluvia intensa pueden tener eventos no reportados.
      2. Morfología: retiene como negativos solo cuencas con
         UP_AREA ≤ P{area_percentil*100} km² (headwaters pequeños con
         menor exposición y menor probabilidad de evento no detectado).
    Todos los positivos se conservan sin filtro.

    Returns
    -------
    DataFrame filtrado con positivos + negativos defensibles.
    """
    precip_threshold = df_precip_semanal["precip_acum_14d"].quantile(precip_percentil)
    area_threshold   = gdf_cuencas["UP_AREA"].quantile(area_percentil)

    low_precip_semanas = set(
        df_precip_semanal.loc[
            df_precip_semanal["precip_acum_14d"] <= precip_threshold,
            "anio_semana",
        ]
    )
    stable_cuencas = set(
        gdf_cuencas.loc[gdf_cuencas["UP_AREA"] <= area_threshold, "HYBAS_ID"]
    )

    mask_pos = df_grid["deslizamiento"] == 1
    mask_neg = (
        (df_grid["deslizamiento"] == 0) &
        df_grid["anio_semana"].isin(low_precip_semanas) &
        df_grid["HYBAS_ID"].isin(stable_cuencas)
    )

    df_out = df_grid[mask_pos | mask_neg].copy()
    print(
        f"Pseudo-ausencias generadas:\n"
        f"  Positivos : {mask_pos.sum():,}\n"
        f"  Negativos : {mask_neg.sum():,} "
        f"(precip ≤ {precip_threshold:.1f} mm | UP_AREA ≤ {area_threshold:.0f} km²)\n"
        f"  Total     : {len(df_out):,}"
    )
    return df_out
