"""
Descarga de datos desde APIs públicas de Colombia (datos.gov.co).

Datasets usados:
  - s54a-sgyg : Precipitación IDEAM (sensores automáticos, mm)
  - wwkg-r6te : Emergencias UNGRD 2019-2022 (eventos hidrometeorológicos)

Estrategia IDEAM:
  El dataset tiene millones de lecturas sub-horarias. En lugar de descargar
  todo y agregar localmente, descargamos mes a mes con un límite de registros
  por mes y luego agregamos por departamento. Esto evita timeouts en GROUP BY
  del servidor y da cobertura temporal completa.
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
        print(f"  página {page}: +{len(batch):,} → total {len(records):,}")
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
