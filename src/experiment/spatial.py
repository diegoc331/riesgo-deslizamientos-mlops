"""
Operaciones espaciales para el pipeline de deslizamientos (Fase 2).

Modulo responsable de:
  - Descargar limite departamental de Antioquia (GADM v4.1)
  - Descargar cuencas HydroSHEDS nivel 10 para Antioquia (HydroBASINS)
  - Descargar centroides municipales de Antioquia (GADM nivel 2)
  - Descargar inventario SGC-SIMMA de movimientos en masa (sin fechas)
  - Geocodificar eventos UNGRD usando centroides municipales
  - Asignar eventos puntuales a cuencas por interseccion espacial
  - Construir grid (semana x cuenca) con etiquetas binarias
  - Generar pseudo-ausencias defensibles para la clase negativa

Granularidad objetivo: (anio_semana, HYBAS_ID) ~300 cuencas x 204 semanas

Nota SIMMA: el FeatureServer de SGC devuelve el inventario espacial de
cicatrices (sin campo FECHA). Para etiquetas temporales usar UNGRD
geocodificado via get_ungrd_with_coords().
"""

from __future__ import annotations

import io
import unicodedata
import warnings
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

RAW_DIR = Path(__file__).parents[2] / "data" / "raw"
SPATIAL_DIR = RAW_DIR / "spatial"

# URL corregida del servicio SIMMA (validada 2025-05)
_SIMMA_BASE_URL = (
    "https://services1.arcgis.com/Og2nrTKe5bptW02d/arcgis/rest/services/"
    "Inventario_de_movimientos_en_masa/FeatureServer/0/query"
)


def _normalize_name(s: str) -> str:
    """Minusculas, sin tildes, sin espacios — para join robusto de municipios."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFD", s.lower().strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace(" ", "").replace("-", "")


# =============================================================================
# Descarga de capas geograficas base
# =============================================================================


def download_antioquia_boundary() -> gpd.GeoDataFrame:
    """
    Descarga el limite departamental de Antioquia desde GADM v4.1.

    Fuente: https://gadm.org/
    Licencia: Libre para uso no comercial y academico.
    """
    cache = SPATIAL_DIR / "antioquia_boundary.gpkg"
    if cache.exists():
        return gpd.read_file(cache)

    SPATIAL_DIR.mkdir(parents=True, exist_ok=True)
    url = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_COL_1.json"
    print("Descargando limite departamental Colombia (GADM)...")
    r = requests.get(url, timeout=120)
    r.raise_for_status()

    gdf = gpd.read_file(io.BytesIO(r.content))
    antioquia = gdf[gdf["NAME_1"].str.lower() == "antioquia"].copy()

    if antioquia.empty:
        raise RuntimeError("No se encontro Antioquia en el GeoJSON de GADM.")

    antioquia.to_file(cache, driver="GPKG")
    print(f"Limite Antioquia guardado: {cache}")
    return antioquia


def download_hydrobasins(nivel: int = 10) -> gpd.GeoDataFrame:
    """
    Descarga HydroSHEDS HydroBASINS nivel {nivel} para Suramerica
    y recorta al poligono de Antioquia.

    Nivel 10 aprox 100-500 km^2 por cuenca (~300 cuencas en Antioquia).
    Fuente : https://www.hydrosheds.org/products/hydrobasins
    Licencia: CC BY 4.0 - gratuita sin registro desde version 1c.

    Columnas clave del resultado:
      HYBAS_ID  : identificador unico de cuenca (int64)
      SUB_AREA  : area de la sub-cuenca (km^2)
      UP_AREA   : area de drenaje acumulada aguas arriba (km^2)
      DIST_MAIN : distancia al cauce principal (km)
      ORDER     : orden de Strahler del cauce principal
    """
    cache = SPATIAL_DIR / f"hydrobasins_antioquia_lev{nivel:02d}.gpkg"
    if cache.exists():
        print(f"HydroBASINS cargado desde cache: {cache}")
        return gpd.read_file(cache)

    SPATIAL_DIR.mkdir(parents=True, exist_ok=True)
    url = (
        f"https://data.hydrosheds.org/file/hydrobasins/standard/"
        f"hybas_sa_lev{nivel:02d}_v1c.zip"
    )
    print(f"Descargando HydroBASINS nivel {nivel} Suramerica (~50-150 MB)...")
    r = requests.get(url, timeout=600)
    r.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        shp_name = next(n for n in zf.namelist() if n.endswith(".shp"))
        stem = Path(shp_name).stem
        for member in zf.namelist():
            if Path(member).stem == stem:
                zf.extract(member, SPATIAL_DIR)
        gdf_sa = gpd.read_file(SPATIAL_DIR / shp_name)

    antioquia = download_antioquia_boundary()
    gdf_sa = gdf_sa.to_crs(antioquia.crs)

    bbox = antioquia.total_bounds
    gdf_bbox = gdf_sa.cx[bbox[0] : bbox[2], bbox[1] : bbox[3]]
    gdf = gpd.clip(gdf_bbox, antioquia)
    gdf = gdf[gdf.geometry.area > 0].copy()

    gdf.to_file(cache, driver="GPKG")
    print(f"HydroBASINS Antioquia: {len(gdf)} cuencas -> {cache}")
    return gdf


# =============================================================================
# Centroides municipales (para geocodificar eventos UNGRD)
# =============================================================================


def download_municipio_centroids() -> gpd.GeoDataFrame:
    """
    Descarga los municipios de Antioquia (GADM v4.1 nivel 2) y calcula
    sus centroides. Sirve para geocodificar eventos UNGRD que solo tienen
    nombre de municipio.

    Retorna GeoDataFrame con columnas:
      municipio_norm : nombre normalizado (sin tildes, minusculas)
      NAME_2         : nombre oficial
      geometry       : centroide del poligono municipal (punto)
    """
    cache = SPATIAL_DIR / "municipios_antioquia_centroids.gpkg"
    if cache.exists():
        return gpd.read_file(cache)

    SPATIAL_DIR.mkdir(parents=True, exist_ok=True)
    url = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_COL_2.json"
    print("Descargando municipios Colombia (GADM nivel 2) ~30 MB...")
    r = requests.get(url, timeout=300)
    r.raise_for_status()

    gdf = gpd.read_file(io.BytesIO(r.content))
    antioquia = gdf[gdf["NAME_1"].str.lower() == "antioquia"].copy()

    if antioquia.empty:
        raise RuntimeError("No se encontraron municipios de Antioquia en GADM nivel 2.")

    antioquia = antioquia.to_crs("EPSG:4326")
    antioquia["municipio_norm"] = antioquia["NAME_2"].apply(_normalize_name)
    antioquia["geometry"] = antioquia.geometry.centroid

    result = antioquia[["municipio_norm", "NAME_2", "geometry"]].copy()
    result.to_file(cache, driver="GPKG")
    print(f"Centroides municipales Antioquia: {len(result)} municipios -> {cache}")
    return result


def get_ungrd_with_coords(
    df_ungrd: pd.DataFrame,
    gdf_municipios: gpd.GeoDataFrame | None = None,
) -> gpd.GeoDataFrame:
    """
    Geocodifica eventos UNGRD usando centroides de municipios de Antioquia.

    UNGRD tiene fecha + municipio pero no coordenadas individuales.
    La asignacion usa el centroide del municipio como posicion aproximada.

    Parameters
    ----------
    df_ungrd : DataFrame con columnas [fecha, departamento, municipio, evento]
    gdf_municipios : centroides municipales (de download_municipio_centroids).
                     Si es None, se descarga automaticamente.

    Returns
    -------
    GeoDataFrame con geometria puntual (centroide municipal) + columnas originales.
    Eventos cuyo municipio no se encuentra en GADM son descartados.
    """
    if gdf_municipios is None:
        gdf_municipios = download_municipio_centroids()

    df = df_ungrd.copy()
    df["municipio_norm"] = df["municipio"].apply(_normalize_name)

    merged = df.merge(
        gdf_municipios[["municipio_norm", "geometry"]],
        on="municipio_norm",
        how="left",
    )
    n_sin_coord = merged["geometry"].isna().sum()
    if n_sin_coord:
        print(f"  UNGRD: {n_sin_coord} eventos sin centroide municipal (descartados)")

    merged = merged.dropna(subset=["geometry"])
    gdf = gpd.GeoDataFrame(merged, geometry="geometry", crs="EPSG:4326")
    print(f"  UNGRD geocodificado: {len(gdf)} eventos con coordenadas")
    return gdf


# =============================================================================
# Inventario SGC-SIMMA (inventario espacial, sin fechas temporales)
# =============================================================================


def download_simma(max_records: int = 5_000) -> gpd.GeoDataFrame:
    """
    Descarga inventario de movimientos en masa SGC-SIMMA para Antioquia.

    NOTA: este servicio devuelve el inventario espacial de cicatrices de
    deslizamientos (TIPO, SUBTIPO) pero SIN campo de fecha de ocurrencia.
    Util como capa de referencia espacial, no para etiquetas temporales.
    Para etiquetas temporales usar get_ungrd_with_coords() con UNGRD.

    Fuente: https://datos.sgc.gov.co/datasets/312c8792ddb24954a9d2711bd89d1afe
    """
    cache = SPATIAL_DIR / "simma_antioquia.gpkg"
    if cache.exists():
        print(f"SIMMA cargado desde cache: {cache}")
        return gpd.read_file(cache)

    SPATIAL_DIR.mkdir(parents=True, exist_ok=True)
    antioquia = download_antioquia_boundary()
    bbox = antioquia.total_bounds  # (minx, miny, maxx, maxy)

    records = []
    offset = 0
    page_size = 2_000

    while len(records) < max_records:
        params = {
            "where": "1=1",
            "outFields": "FID,OBJECTID,TIPO,SUBTIPO,CLAS_MAPA",
            "outSR": "4326",
            "returnGeometry": "true",
            "geometryType": "esriGeometryEnvelope",
            "geometry": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
            "spatialRel": "esriSpatialRelIntersects",
            "f": "json",
            "resultOffset": offset,
            "resultRecordCount": page_size,
        }
        resp = requests.get(_SIMMA_BASE_URL, params=params, timeout=60)
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if not features:
            break
        for feat in features:
            attrs = feat.get("attributes", {})
            geo = feat.get("geometry", {})
            attrs["LONGITUD"] = geo.get("x")
            attrs["LATITUD"] = geo.get("y")
            records.append(attrs)
        print(f"  SIMMA: {len(records)} registros descargados")
        if len(features) < page_size:
            break
        offset += page_size

    if not records:
        raise RuntimeError("SIMMA devolvio 0 registros. Verificar endpoint.")

    df = pd.DataFrame(records)
    df = df.dropna(subset=["LATITUD", "LONGITUD"])
    df = df[(df["LATITUD"] != 0) & (df["LONGITUD"] != 0)]

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["LONGITUD"], df["LATITUD"]),
        crs="EPSG:4326",
    )
    gdf.to_file(cache, driver="GPKG")
    print(f"SIMMA guardado: {len(gdf)} cicatrices -> {cache}")
    return gdf


# =============================================================================
# Asignacion de eventos a cuencas
# =============================================================================


def assign_events_to_cuencas(
    gdf_eventos: gpd.GeoDataFrame,
    gdf_cuencas: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Asigna eventos puntuales a cuencas HydroSHEDS por interseccion espacial.

    Eventos fuera de cualquier cuenca (coordenadas imprecisas o fuera de
    Antioquia) reciben HYBAS_ID = NaN y se descartan del resultado.

    Parameters
    ----------
    gdf_eventos : GeoDataFrame con geometria puntual y columna 'fecha'
    gdf_cuencas : GeoDataFrame de HydroBASINS con columna 'HYBAS_ID'

    Returns
    -------
    GeoDataFrame de eventos enriquecido con columna HYBAS_ID (int64).
    """
    gdf_ev = gdf_eventos.to_crs(gdf_cuencas.crs)

    joined = gpd.sjoin(
        gdf_ev,
        gdf_cuencas[["HYBAS_ID", "geometry"]],
        how="left",
        predicate="within",
    )
    n_sin_cuenca = joined["HYBAS_ID"].isna().sum()
    if n_sin_cuenca:
        print(f"  Eventos sin cuenca (fuera del poligono): {n_sin_cuenca} descartados")
    return joined.dropna(subset=["HYBAS_ID"])


def build_event_grid(
    df_eventos: pd.DataFrame,
    gdf_cuencas: gpd.GeoDataFrame,
    anio_inicio: int = 2019,
    anio_fin: int = 2022,
) -> pd.DataFrame:
    """
    Construye el grid completo (semana x cuenca) con etiquetas binarias.

    Genera el producto cartesiano de todas las semanas ISO del periodo
    x todas las cuencas de Antioquia, y marca como 1 las celdas con
    al menos un evento UNGRD/SIMMA reportado.

    Returns
    -------
    DataFrame con [anio_semana, HYBAS_ID, n_eventos, deslizamiento]
    """
    df = df_eventos.copy()
    df["anio_semana"] = df["fecha"].dt.to_period("W")

    eventos_por_cuenca = (
        df.groupby(["anio_semana", "HYBAS_ID"]).size().reset_index(name="n_eventos")
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
    grid["n_eventos"] = grid["n_eventos"].fillna(0).astype(int)
    grid["deslizamiento"] = (grid["n_eventos"] > 0).astype(int)

    pct_positivos = 100 * grid["deslizamiento"].mean()
    print(
        f"Grid (semana x cuenca): {len(grid):,} instancias | "
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
    strict_mode: bool = True,
) -> pd.DataFrame:
    """
    Filtra el grid (semana x cuenca) para construir negativos confiables.

    Estrategia de 2 criterios combinados (Li et al., 2024, Sci. Reports):
      1. Precipitacion: retiene como negativos solo semanas con
         precip_acum_14d <= P{precip_percentil*100} historico departamental.
      2. Morfologia: retiene como negativos solo cuencas con
         UP_AREA <= P{area_percentil*100} km^2 (headwaters pequenos).
    Todos los positivos se conservan sin filtro.

    Parameters
    ----------
    strict_mode : bool, default True
        Si True, lanza ValueError cuando se detecta que precip_acum_14d
        contiene conteos de eventos en lugar de mm de precipitacion real
        (sesgo circular: el target contamina la seleccion de negativos).
        Si False, lanza UserWarning y continua con el calculo sesgado.

    Returns
    -------
    DataFrame filtrado con positivos + negativos defensibles.
    """
    # --- Guardia contra proxy circular ---
    precip_vals = df_precip_semanal["precip_acum_14d"]
    _max_val = precip_vals.max()
    _is_integer_like = (precip_vals % 1 == 0).all()
    if _is_integer_like and _max_val < 20:
        _msg = (
            "SESGO CIRCULAR DETECTADO en generate_pseudo_absences(): "
            f"'precip_acum_14d' parece ser un conteo de eventos "
            f"(max={_max_val:.0f}, todos enteros), no precipitacion en mm. "
            "Usar n_eventos como proxy contamina la seleccion de negativos con el target. "
            "Soluciones: (1) proporcione datos reales de CHIRPS/IDEAM, "
            "o (2) use df_grid.copy() directamente sin filtrar pseudo-ausencias."
        )
        if strict_mode:
            raise ValueError(_msg)
        warnings.warn(_msg, UserWarning, stacklevel=2)

    precip_threshold = df_precip_semanal["precip_acum_14d"].quantile(precip_percentil)
    area_threshold = gdf_cuencas["UP_AREA"].quantile(area_percentil)

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
        (df_grid["deslizamiento"] == 0)
        & df_grid["anio_semana"].isin(low_precip_semanas)
        & df_grid["HYBAS_ID"].isin(stable_cuencas)
    )

    df_out = df_grid[mask_pos | mask_neg].copy()
    print(
        f"Pseudo-ausencias generadas:\n"
        f"  Positivos : {mask_pos.sum():,}\n"
        f"  Negativos : {mask_neg.sum():,} "
        f"(precip <= {precip_threshold:.1f} mm | UP_AREA <= {area_threshold:.0f} km2)\n"
        f"  Total     : {len(df_out):,}"
    )
    return df_out
