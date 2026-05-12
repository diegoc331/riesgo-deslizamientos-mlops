"""
Descarga de datos desde APIs públicas de Colombia y fuentes satelitales globales.

Datasets:
  - s54a-sgyg       : Precipitación IDEAM — sensores automáticos (legacy, 3.4% cobertura)
  - wwkg-r6te       : Emergencias UNGRD 2019-2022
  - CHIRPS v2.0     : Precipitación diaria 5.5 km (CHC/UCSB) — sin registro requerido
  - ERA5-Land swvl2 : Humedad suelo 7-28 cm, 9 km (ECMWF/Copernicus) — requiere ~/.cdsapirc
"""

from __future__ import annotations

import time
from calendar import monthrange
from pathlib import Path

import pandas as pd
import requests

RAW_DIR = Path(__file__).parents[2] / "data" / "raw"

BASE_URL = "https://www.datos.gov.co/resource/{dataset_id}.json"

# Dataset IDs verificados y funcionales
IDEAM_PRECIP_ID  = "s54a-sgyg"
UNGRD_EVENTOS_ID = "wwkg-r6te"

# Registros máximos por mes IDEAM — suficientes para cubrir la mayoría
# de departamentos sin saturar la API (~200 estaciones × 25 lecturas/mes)
IDEAM_LIMIT_PER_MONTH = 5_000
SOCRATA_LIMIT = 10_000


def _get(dataset_id: str, params: dict, timeout: int = 90) -> list[dict]:
    """GET a un endpoint Socrata con manejo de timeout."""
    url = BASE_URL.format(dataset_id=dataset_id)
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ReadTimeout:
        print("  ⚠ Timeout — se omite este lote")
        return []


def download_ideam(
    anio_inicio: int = 2019,
    anio_fin: int = 2022,
    save: bool = True,
) -> pd.DataFrame:
    """
    Descarga precipitaciones IDEAM mes a mes (2019-2022).

    Estrategia: 1 llamada por mes, 5000 registros, sensor mm.
    Total: ~48 llamadas × ≤5000 filas = ≤240k filas brutas.
    Después de agregar por departamento quedan ~33 × 48 = ~1584 filas.
    """
    frames: list[pd.DataFrame] = []
    total_calls = (anio_fin - anio_inicio + 1) * 12
    call_n = 0

    for anio in range(anio_inicio, anio_fin + 1):
        for mes in range(1, 13):
            call_n += 1
            dias = monthrange(anio, mes)[1]
            fecha_ini = f"{anio}-{mes:02d}-01T00:00:00.000"
            fecha_fin = f"{anio}-{mes:02d}-{dias:02d}T23:59:59.000"

            params = {
                "$where": (
                    f"unidadmedida='mm' "
                    f"AND fechaobservacion >= '{fecha_ini}' "
                    f"AND fechaobservacion <= '{fecha_fin}'"
                ),
                "$select": "departamento, fechaobservacion, valorobservado",
                "$limit": IDEAM_LIMIT_PER_MONTH,
            }
            batch = _get(IDEAM_PRECIP_ID, params)
            if batch:
                frames.append(pd.DataFrame(batch))
            print(
                f"  [{call_n:02d}/{total_calls}] {anio}-{mes:02d}: "
                f"{len(batch):,} registros",
                flush=True,
            )
            time.sleep(0.3)

    if not frames:
        raise RuntimeError("No se descargó ningún dato de IDEAM. Verifica la conexión.")

    df = pd.concat(frames, ignore_index=True)
    print(f"\nIDEAM total: {len(df):,} registros brutos")

    if save:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        path = RAW_DIR / "ideam_precipitaciones.csv"
        df.to_csv(path, index=False)
        print(f"Guardado en {path}")
    return df


def _socrata_paged(dataset_id: str, params: dict, max_records: int = 30_000) -> list[dict]:
    """Descarga paginada genérica."""
    records: list[dict] = []
    offset = 0
    page = 1
    while True:
        batch = _get(dataset_id, {**params, "$limit": SOCRATA_LIMIT, "$offset": offset})
        if not batch:
            break
        records.extend(batch)
        print(f"  pagina {page}: +{len(batch):,} -> total {len(records):,}")
        if len(batch) < SOCRATA_LIMIT or len(records) >= max_records:
            break
        offset += SOCRATA_LIMIT
        page += 1
        time.sleep(0.3)
    return records[:max_records]


def download_ungrd(max_records: int = 30_000, save: bool = True) -> pd.DataFrame:
    """Descarga emergencias UNGRD 2019-2022 (wwkg-r6te)."""
    print(f"Descargando emergencias UNGRD (máx {max_records:,} registros)...")
    records = _socrata_paged(UNGRD_EVENTOS_ID, {"$order": "fecha ASC"}, max_records)
    df = pd.DataFrame(records)
    print(f"UNGRD: {len(df):,} registros")
    if save:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        path = RAW_DIR / "ungrd_emergencias.csv"
        df.to_csv(path, index=False)
        print(f"Guardado en {path}")
    return df


def load_ideam(anio_inicio: int = 2019, anio_fin: int = 2022) -> pd.DataFrame:
    path = RAW_DIR / "ideam_precipitaciones.csv"
    if path.exists():
        print(f"Cargando IDEAM desde cache: {path}")
        return pd.read_csv(path, low_memory=False)
    print("Cache IDEAM no encontrado — iniciando descarga mes a mes...")
    return download_ideam(anio_inicio=anio_inicio, anio_fin=anio_fin)


def load_ungrd() -> pd.DataFrame:
    path = RAW_DIR / "ungrd_emergencias.csv"
    if path.exists():
        print(f"Cargando UNGRD desde cache: {path}")
        return pd.read_csv(path, low_memory=False)
    return download_ungrd()


# =============================================================================
# CHIRPS v2.0 — precipitación diaria satelital (sin registro)
# =============================================================================

def download_chirps(
    anio_inicio: int = 2019,
    anio_fin: int = 2022,
    bbox: tuple[float, float, float, float] = (5.0, -77.1, 8.9, -73.9),
    save: bool = True,
) -> pd.DataFrame:
    """
    Descarga CHIRPS v2.0 diario y extrae la precipitación media sobre Antioquia.

    Estrategia: un .tif.gz por día → descomprime en memoria → recorta al bbox
    con una ventana rasterio → calcula media espacial. Los rasters no se
    persisten en disco; solo se guarda el CSV diario ligero (~1500 filas).
    Soporta reanudación: si el CSV existe, solo descarga fechas faltantes.

    Parameters
    ----------
    bbox : (lat_min, lon_min, lat_max, lon_max)
        Bounding box de Antioquia: (5.0, -77.1, 8.9, -73.9)
    """
    try:
        import gzip
        import io
        import rasterio
        from rasterio.io import MemoryFile
        from rasterio.windows import from_bounds
    except ImportError:
        raise ImportError("Instala rasterio: uv add rasterio")

    cache_path = RAW_DIR / "chirps_antioquia_daily.csv"
    lat_min, lon_min, lat_max, lon_max = bbox

    # Reanudación: detectar fechas ya descargadas
    done_dates: set = set()
    df_existing: pd.DataFrame | None = None
    if cache_path.exists():
        df_existing = pd.read_csv(cache_path, parse_dates=["fecha"])
        done_dates = set(df_existing["fecha"].dt.date)

    date_range = pd.date_range(f"{anio_inicio}-01-01", f"{anio_fin}-12-31", freq="D")
    pending = [d for d in date_range if d.date() not in done_dates]

    if not pending:
        print(f"CHIRPS ya completo: {len(df_existing):,} días en caché.")
        return df_existing

    print(f"Descargando CHIRPS: {len(pending)} días pendientes "
          f"(de {len(date_range)} totales)...")

    BASE = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/tifs/p05"
    new_records = []

    for i, date in enumerate(pending, 1):
        y, m, d = date.year, date.month, date.day
        fname = f"chirps-v2.0.{y}.{m:02d}.{d:02d}.tif.gz"
        url = f"{BASE}/{y}/{fname}"
        precip = 0.0

        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            with gzip.open(io.BytesIO(resp.content)) as gz_file:
                tif_bytes = gz_file.read()
            with MemoryFile(tif_bytes) as memfile:
                with memfile.open() as src:
                    window = from_bounds(lon_min, lat_min, lon_max, lat_max, src.transform)
                    data = src.read(1, window=window, masked=True)
                    if data.count() > 0:
                        valid = data.compressed()
                        valid = valid[valid >= 0]
                        if len(valid) > 0:
                            precip = float(valid.mean())
        except Exception as e:
            if i <= 3 or i % 365 == 0:
                print(f"  ⚠ {date.date()}: {e}")

        new_records.append({"fecha": date, "precip_mm": precip})

        if i % 100 == 0 or i == len(pending):
            print(f"  [{i:4d}/{len(pending)}] {date.date()} — {precip:.2f} mm", flush=True)

    df_new = pd.DataFrame(new_records)
    df_new["fecha"] = pd.to_datetime(df_new["fecha"])

    df_final = (
        pd.concat([df_existing, df_new], ignore_index=True)
        if df_existing is not None
        else df_new
    )
    df_final = df_final.sort_values("fecha").reset_index(drop=True)

    if save:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        df_final.to_csv(cache_path, index=False)
        print(f"CHIRPS guardado: {len(df_final):,} dias -> {cache_path}")

    return df_final


def load_chirps(anio_inicio: int = 2019, anio_fin: int = 2022) -> pd.DataFrame:
    """Carga CHIRPS desde caché o descarga si faltan fechas."""
    return download_chirps(anio_inicio=anio_inicio, anio_fin=anio_fin)


# =============================================================================
# ERA5-Land — humedad de suelo (requiere cuenta Copernicus CDS)
# =============================================================================

def download_era5(
    anio_inicio: int = 2019,
    anio_fin: int = 2022,
    variables: list[str] | None = None,
    area: list[float] | None = None,
    save: bool = True,
) -> pd.DataFrame:
    """
    Descarga ERA5-Land (humedad suelo capa 2, swvl2) vía CDSAPI.

    Requiere ~/.cdsapirc con URL y key de https://cds.climate.copernicus.eu/user/register
    (registro gratuito, aprobación instantánea).

    Estrategia: una petición por año con variable swvl2 a las 00:00 UTC.
    swvl2 es instantanea -> snapshot diario a 00:00 UTC es un proxy valido.
    Resultado: CSV diario con [fecha, soil_moisture_m3m3].
    """
    try:
        import cdsapi
    except ImportError:
        raise ImportError("Instala cdsapi: uv add cdsapi")
    try:
        import xarray as xr
    except ImportError:
        raise ImportError("Instala xarray y netCDF4: uv add xarray netCDF4")

    if variables is None:
        variables = ["volumetric_soil_water_layer_2"]
    if area is None:
        area = [8.9, -77.1, 5.0, -73.9]  # N, W, S, E

    cache_path = RAW_DIR / "era5_antioquia_daily.csv"
    if cache_path.exists():
        print(f"Cargando ERA5-Land desde caché: {cache_path}")
        return pd.read_csv(cache_path, parse_dates=["fecha"])

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    c = cdsapi.Client()
    nc_files: list[Path] = []

    for year in range(anio_inicio, anio_fin + 1):
        nc_path = RAW_DIR / f"era5_antioquia_{year}.nc"
        nc_files.append(nc_path)
        if nc_path.exists():
            print(f"  {year}: ya descargado ({nc_path.name})")
            continue
        print(f"  Descargando ERA5-Land {year} ({variables})...")
        c.retrieve(
            "reanalysis-era5-land",
            {
                "product_type": "reanalysis",
                "variable": variables,
                "year": str(year),
                "month": [str(m).zfill(2) for m in range(1, 13)],
                "day":   [str(d).zfill(2) for d in range(1, 32)],
                "time":  "00:00",
                "area":  area,
                "format": "netcdf",
            },
            str(nc_path),
        )

    # Consolidar años en serie diaria
    records = []
    for nc_path in nc_files:
        import numpy as np
        ds = xr.open_dataset(nc_path)
        # swvl2 o primer nombre de variable disponible
        var_name = "swvl2" if "swvl2" in ds else next(iter(ds.data_vars))
        da = ds[var_name].mean(dim=["latitude", "longitude"])
        for t_val, sm_val in zip(da.time.values, da.values):
            records.append({
                "fecha": pd.Timestamp(t_val).normalize(),
                "soil_moisture_m3m3": float(sm_val) if not np.isnan(sm_val) else np.nan,
            })
        ds.close()

    df = pd.DataFrame(records)
    df["fecha"] = pd.to_datetime(df["fecha"])
    df = df.sort_values("fecha").reset_index(drop=True)

    if save:
        df.to_csv(cache_path, index=False)
        print(f"ERA5-Land guardado: {len(df):,} dias -> {cache_path}")

    return df


def load_era5(anio_inicio: int = 2019, anio_fin: int = 2022) -> pd.DataFrame:
    """Carga ERA5-Land desde caché o descarga si no existe."""
    return download_era5(anio_inicio=anio_inicio, anio_fin=anio_fin)
