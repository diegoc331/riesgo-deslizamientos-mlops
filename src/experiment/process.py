"""Limpieza, join espacial-temporal y feature engineering."""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import numpy as np

if TYPE_CHECKING:
    import geopandas as gpd

PROCESSED_DIR = Path(__file__).parents[2] / "data" / "processed"

# Eventos UNGRD considerados hidrometeorológicos de alta precipitación
# (proxy de deslizamientos + inundaciones causados por lluvia intensa)
HYDRO_EVENTS = [
    "avenida torrencial",
    "creciente subita",
    "inundacion",
    "deslizamiento",
    "derrumbe",
    "movimiento en masa",
    "flujo de lodo",
]


def _normalize(s: str) -> str:
    """Minúsculas sin tildes."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def clean_ideam(df: pd.DataFrame) -> pd.DataFrame:
    """
    Limpia precipitaciones IDEAM (dataset s54a-sgyg).

    Columnas esperadas: fechaobservacion, valorobservado, departamento, municipio
    """
    df = df.copy()

    date_col = next((c for c in df.columns if "fecha" in c.lower()), None)
    if date_col is None:
        raise ValueError(f"No se encontró columna de fecha. Columnas: {list(df.columns)}")

    df["fecha"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=["fecha"])

    val_col = next((c for c in df.columns if "valor" in c.lower()), None)
    if val_col is None:
        raise ValueError(f"No se encontró columna de valor. Columnas: {list(df.columns)}")

    df["precip_mm"] = pd.to_numeric(df[val_col], errors="coerce")
    df = df.dropna(subset=["precip_mm"])
    df = df[(df["precip_mm"] >= 0) & (df["precip_mm"] <= 500)]

    dpto_col = next((c for c in df.columns if "depart" in c.lower()), None)
    df["departamento"] = df[dpto_col].apply(_normalize) if dpto_col else "desconocido"

    df["anio"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month
    df["anio_mes"] = df["fecha"].dt.to_period("M")

    print(f"IDEAM limpio: {len(df):,} registros | {df['fecha'].min().date()} → {df['fecha'].max().date()}")
    return df[["fecha", "anio", "mes", "anio_mes", "departamento", "precip_mm"]]


def clean_ungrd(df: pd.DataFrame) -> pd.DataFrame:
    """
    Limpia emergencias UNGRD (dataset wwkg-r6te).

    Filtra eventos hidrometeorológicos: avenidas torrenciales, crecientes,
    inundaciones y deslizamientos — todos causados por precipitación intensa.
    """
    df = df.copy()
    print(f"UNGRD columnas: {list(df.columns)}")

    evento_col = next(
        (c for c in df.columns if any(k in c.lower() for k in ["evento", "tipo"])),
        None,
    )
    if evento_col:
        mask = df[evento_col].apply(
            lambda v: any(k in _normalize(str(v)) for k in HYDRO_EVENTS)
        )
        df_filtrado = df[mask].copy()
        total_eventos = df[evento_col].nunique()
        print(f"UNGRD: {len(df):,} total → {len(df_filtrado):,} eventos hidrometeorológicos "
              f"(de {total_eventos} tipos de evento)")
        df = df_filtrado
    else:
        print("UNGRD: no se encontró columna 'evento' — usando todos los registros")

    date_col = next((c for c in df.columns if "fecha" in c.lower()), None)
    if date_col is None:
        raise ValueError(f"No se encontró columna de fecha. Columnas: {list(df.columns)}")

    df["fecha"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=["fecha"])

    dpto_col = next((c for c in df.columns if "depart" in c.lower()), None)
    df["departamento"] = df[dpto_col].apply(_normalize) if dpto_col else "desconocido"

    evento_col_out = evento_col or "evento"
    if evento_col_out not in df.columns:
        df["evento"] = "desconocido"

    df["anio"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month
    df["anio_mes"] = df["fecha"].dt.to_period("M")

    print(f"UNGRD limpio: {len(df):,} eventos | {df['fecha'].min().date()} → {df['fecha'].max().date()}")
    return df[["fecha", "anio", "mes", "anio_mes", "departamento", evento_col_out]]

def aggregate_weekly_ideam(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega precipitación IDEAM a nivel diario primero, luego construye
    ventanas deslizantes de 14 días por semana ISO.

    La agregación diaria es el paso intermedio necesario: los sensores
    pueden tener múltiples lecturas por día y necesitamos una sola
    cifra diaria antes de acumular la ventana.
    """
    df = df.copy()

    # Paso 1: agregar a nivel diario
    df["fecha_dia"] = df["fecha"].dt.date
    diario = (
        df.groupby("fecha_dia")
        .agg(
            precip_diaria  = ("precip_mm", "sum"),
            n_estaciones   = ("precip_mm", "count"),
        )
        .reset_index()
    )
    diario["fecha_dia"] = pd.to_datetime(diario["fecha_dia"])


    # Paso 2: crear índice diario completo (detecta días sin datos)
    idx_completo = pd.date_range(
        diario["fecha_dia"].min(),
        diario["fecha_dia"].max(),
        freq="D"
    )
    diario = (
        diario.set_index("fecha_dia")
        .reindex(idx_completo)
        .rename_axis("fecha_dia")
        .reset_index()
    )
    # Imputar días sin datos con 0 (ausencia de reporte ≠ ausencia de lluvia,
    # pero es la única opción conservadora sin datos SIATA)
    diario["precip_diaria"]  = diario["precip_diaria"].fillna(0)
    diario["n_estaciones"]   = diario["n_estaciones"].fillna(0)

    # Paso 3: construir ventanas deslizantes por semana ISO
    # Cada semana toma los 14 días anteriores como ventana de precipitación
    diario = diario.sort_values("fecha_dia").reset_index(drop=True)
    diario["semana_iso"]     = diario["fecha_dia"].dt.isocalendar().week.astype(int)
    diario["anio_iso"]       = diario["fecha_dia"].dt.isocalendar().year.astype(int)
    diario["anio_semana"]    = (
        diario["fecha_dia"].dt.to_period("W")
    )

    # Rolling sobre el índice diario — shift(1) para no incluir la semana actual
    diario["precip_acum_14d"]        = diario["precip_diaria"].rolling(14, min_periods=7).sum()
    diario["precip_acum_7d"]         = diario["precip_diaria"].rolling(7,  min_periods=4).sum()
    diario["precip_acum_3d"]         = diario["precip_diaria"].rolling(3,  min_periods=2).sum()
    diario["precip_max_diario_14d"]  = diario["precip_diaria"].rolling(14, min_periods=7).max()
    diario["precip_dias_lluvia_14d"] = (
        (diario["precip_diaria"] > 0).rolling(14, min_periods=7).sum()
    )

    # Paso 4: colapsar a nivel semanal tomando el último día de cada semana
    # (el acumulado de 14 días al final de la semana es la feature del modelo)
    semanal = (
        diario.groupby("anio_semana", observed=True)
        .agg(
            precip_acum_14d        = ("precip_acum_14d",        "last"),
            precip_acum_7d         = ("precip_acum_7d",         "last"),
            precip_acum_3d         = ("precip_acum_3d",         "last"),
            precip_max_diario_14d  = ("precip_max_diario_14d",  "last"),
            precip_dias_lluvia_14d = ("precip_dias_lluvia_14d", "last"),
            n_estaciones           = ("n_estaciones",           "mean"),
            fecha_fin_semana       = ("fecha_dia",              "last"),
        )
        .reset_index()
    )
    semanal["mes"]        = semanal["fecha_fin_semana"].dt.month
    semanal["semana_sin"] = np.sin(2 * np.pi * semanal["fecha_fin_semana"].dt.isocalendar().week / 52)
    semanal["semana_cos"] = np.cos(2 * np.pi * semanal["fecha_fin_semana"].dt.isocalendar().week / 52)
    semanal["mes_sin"]    = np.sin(2 * np.pi * semanal["mes"] / 12)
    semanal["mes_cos"]    = np.cos(2 * np.pi * semanal["mes"] / 12)

    print(f"IDEAM semanal: {len(semanal):,} semanas")
    return semanal

def aggregate_weekly_ungrd(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega eventos UNGRD a nivel semanal.
    Usa la fecha del evento (no de reporte) si está disponible.
    """
    df = df.copy()
    df["anio_semana"] = df["fecha"].dt.to_period("W")

    semanal = (
        df.groupby("anio_semana", observed=True)
        .size()
        .reset_index(name="n_deslizamientos")
    )
    return semanal

def save_processed(df: pd.DataFrame, name: str = "dataset_correlacion.csv") -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / name
    df.to_csv(path, index=False)
    print(f"Guardado en {path}")


# =============================================================================
# CHIRPS v2.0 — agregación semanal (reemplaza aggregate_weekly_ideam)
# =============================================================================

def aggregate_weekly_chirps(df: pd.DataFrame) -> pd.DataFrame:
    """
    Construye features semanales de precipitación desde una serie CHIRPS diaria.

    CHIRPS tiene cobertura 100% (sin huecos), por lo que no se imputan ceros
    por falta de datos — solo se rellena si faltan fechas por error de descarga.

    Parameters
    ----------
    df : DataFrame con columnas [fecha, precip_mm]

    Returns
    -------
    DataFrame semanal con features de precipitación + codificaciones cíclicas,
    indexado por anio_semana (Period[W]).
    """
    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"])
    df = df.sort_values("fecha").reset_index(drop=True)

    # Índice diario completo — rellena huecos de descarga con 0
    idx_completo = pd.date_range(df["fecha"].min(), df["fecha"].max(), freq="D")
    df = (
        df.set_index("fecha")
        .reindex(idx_completo)
        .rename_axis("fecha")
        .reset_index()
    )
    n_huecos = df["precip_mm"].isna().sum()
    if n_huecos > 0:
        print(f"  CHIRPS: {n_huecos} días sin datos → imputados con 0")
    df["precip_mm"] = df["precip_mm"].fillna(0.0)

    # Rolling windows sobre serie diaria continua
    df["anio_semana"] = df["fecha"].dt.to_period("W")
    df["precip_acum_14d"]        = df["precip_mm"].rolling(14, min_periods=7).sum()
    df["precip_acum_7d"]         = df["precip_mm"].rolling(7,  min_periods=4).sum()
    df["precip_acum_3d"]         = df["precip_mm"].rolling(3,  min_periods=2).sum()
    df["precip_max_diario_14d"]  = df["precip_mm"].rolling(14, min_periods=7).max()
    df["precip_dias_lluvia_14d"] = (df["precip_mm"] > 0).rolling(14, min_periods=7).sum()

    # Colapsar a nivel semanal (último día = acumulado final de la ventana)
    semanal = (
        df.groupby("anio_semana", observed=True)
        .agg(
            precip_acum_14d        = ("precip_acum_14d",        "last"),
            precip_acum_7d         = ("precip_acum_7d",         "last"),
            precip_acum_3d         = ("precip_acum_3d",         "last"),
            precip_max_diario_14d  = ("precip_max_diario_14d",  "last"),
            precip_dias_lluvia_14d = ("precip_dias_lluvia_14d", "last"),
            fecha_fin_semana       = ("fecha",                  "last"),
        )
        .reset_index()
    )

    # Shift de 1 semana: la fila para la semana W ahora contiene el rolling
    # calculado al cierre de W-1, es decir, datos disponibles antes de que
    # empiece la ventana de prediccion. Evita leakage concurrente.
    # Las features de estacionalidad NO se shiftean: la posicion en el
    # calendario es conocida de antemano.
    _FEAT_COLS = [
        "precip_acum_14d", "precip_acum_7d", "precip_acum_3d",
        "precip_max_diario_14d", "precip_dias_lluvia_14d",
    ]
    semanal[_FEAT_COLS] = semanal[_FEAT_COLS].shift(1)

    semanal["mes"]        = semanal["fecha_fin_semana"].dt.month
    semanal["semana_sin"] = np.sin(2 * np.pi * semanal["fecha_fin_semana"].dt.isocalendar().week / 52)
    semanal["semana_cos"] = np.cos(2 * np.pi * semanal["fecha_fin_semana"].dt.isocalendar().week / 52)
    semanal["mes_sin"]    = np.sin(2 * np.pi * semanal["mes"] / 12)
    semanal["mes_cos"]    = np.cos(2 * np.pi * semanal["mes"] / 12)

    print(
        f"CHIRPS semanal: {len(semanal)} semanas | "
        f"precip_acum_14d media={semanal['precip_acum_14d'].mean():.1f} mm "
        f"(vs IDEAM ~16 mm con 96.6% ceros)"
    )
    return semanal


# =============================================================================
# ERA5-Land — agregación semanal de humedad de suelo
# =============================================================================

def aggregate_weekly_era5(df: pd.DataFrame, ventana_dias: int = 14) -> pd.DataFrame:
    """
    Construye features semanales de humedad de suelo desde ERA5-Land diario.

    Parameters
    ----------
    df : DataFrame con columnas [fecha, soil_moisture_m3m3]
    ventana_dias : int
        Días de ventana para el rolling mean (default 14).

    Returns
    -------
    DataFrame semanal con [anio_semana, soil_moisture_14d, fecha_fin_semana].
    """
    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"])
    df = df.sort_values("fecha").reset_index(drop=True)

    # Índice diario completo con interpolación lineal para días faltantes
    idx_completo = pd.date_range(df["fecha"].min(), df["fecha"].max(), freq="D")
    df = (
        df.set_index("fecha")
        .reindex(idx_completo)
        .rename_axis("fecha")
        .reset_index()
    )
    n_gaps = df["soil_moisture_m3m3"].isna().sum()
    if n_gaps > 0:
        df["soil_moisture_m3m3"] = df["soil_moisture_m3m3"].interpolate(method="linear")
        print(f"  ERA5-Land: {n_gaps} días interpolados linealmente")

    # Rolling mean de ventana_dias días
    df["anio_semana"] = df["fecha"].dt.to_period("W")
    df[f"soil_moisture_{ventana_dias}d"] = (
        df["soil_moisture_m3m3"]
        .rolling(ventana_dias, min_periods=ventana_dias // 2)
        .mean()
    )

    semanal = (
        df.groupby("anio_semana", observed=True)
        .agg(
            soil_moisture_14d = (f"soil_moisture_{ventana_dias}d", "last"),
            fecha_fin_semana  = ("fecha",                         "last"),
        )
        .reset_index()
    )

    # Shift de 1 semana: igual que CHIRPS, la humedad de suelo para la semana
    # W refleja el rolling calculado al cierre de W-1 (sin leakage concurrente).
    semanal["soil_moisture_14d"] = semanal["soil_moisture_14d"].shift(1)

    print(
        f"ERA5-Land semanal: {len(semanal)} semanas | "
        f"soil_moisture_14d media={semanal['soil_moisture_14d'].mean():.4f} m3/m3"
    )
    return semanal


def build_weekly_dataset_v2(
    df_chirps_semanal: pd.DataFrame,
    df_era5_semanal: pd.DataFrame,
    df_ungrd_semanal: pd.DataFrame,
    periodo: tuple[int, int] = (2019, 2022),
) -> pd.DataFrame:
    """
    Combina CHIRPS semanal + ERA5-Land semanal + etiquetas UNGRD en un
    único DataFrame listo para modelar (dataset v2).

    Parameters
    ----------
    df_chirps_semanal : salida de aggregate_weekly_chirps()
    df_era5_semanal   : salida de aggregate_weekly_era5()
    df_ungrd_semanal  : salida de aggregate_weekly_ungrd() con target binario
    periodo           : (anio_inicio, anio_fin) para filtrar semanas

    Returns
    -------
    DataFrame con index anio_semana, features de precipitación + humedad
    + codificaciones cíclicas + target binario.
    """
    # Join por semana ISO
    df = df_chirps_semanal.merge(
        df_era5_semanal[["anio_semana", "soil_moisture_14d"]],
        on="anio_semana",
        how="left",
    )
    df = df.merge(df_ungrd_semanal, on="anio_semana", how="left")

    # Rellenar semanas sin eventos como 0 (ningún deslizamiento reportado)
    df["n_deslizamientos"] = df["n_deslizamientos"].fillna(0).astype(int)

    # Target: ¿ocurrirá al menos un deslizamiento la PRÓXIMA semana?
    df["deslizamiento"] = (df["n_deslizamientos"].shift(-1) > 0).astype(int)

    # Filtrar al período configurado
    anio_ini, anio_fin = periodo
    fecha_ini = pd.Period(f"{anio_ini}-W01", "W")
    fecha_fin = pd.Period(f"{anio_fin}-W52", "W")
    df = df[(df["anio_semana"] >= fecha_ini) & (df["anio_semana"] <= fecha_fin)]

    # Eliminar última semana (no tiene target — shift(-1) produce NaN)
    df = df.dropna(subset=["deslizamiento", "precip_acum_14d"])

    df = df.reset_index(drop=True)
    print(
        f"\nDataset v2 construido: {len(df)} semanas × {df.shape[1]} columnas\n"
        f"  Target: {df['deslizamiento'].sum()} positivas / "
        f"{(df['deslizamiento'] == 0).sum()} negativas\n"
        f"  soil_moisture_14d NaN: {df['soil_moisture_14d'].isna().sum()}"
    )
    return df


# =============================================================================
# Fase 2 — Dataset (semana × cuenca) con PU-Learning
# =============================================================================

def build_cuenca_dataset_v3(
    df_chirps_semanal: pd.DataFrame,
    df_era5_semanal: pd.DataFrame,
    df_grid: pd.DataFrame,
    gdf_cuencas: "gpd.GeoDataFrame",
    periodo: tuple[int, int] = (2019, 2022),
) -> pd.DataFrame:
    """
    Construye el dataset v3 indexado por (anio_semana × HYBAS_ID).

    Combina:
    - Features dinámicas semanales (CHIRPS + ERA5) — iguales para todas las cuencas
      en una semana dada (proxy departamental, válido para Fase 2)
    - Features estáticas de cuenca (HydroSHEDS): SUB_AREA, UP_AREA, DIST_MAIN, ORDER_
    - Etiquetas (semana S+1): ¿ocurrió al menos un evento en esta cuenca?

    El target usa shift(-1 semana) por cuenca para respetar el horizonte de
    predicción configurado (prediccion_dias = 7 → 1 semana).

    Parameters
    ----------
    df_chirps_semanal : salida de aggregate_weekly_chirps()
    df_era5_semanal   : salida de aggregate_weekly_era5()
    df_grid           : salida de spatial.build_event_grid() con pseudo-ausencias ya
                        aplicadas (salida de generate_pseudo_absences())
    gdf_cuencas       : HydroBASINS con columnas estáticas
    periodo           : (anio_inicio, anio_fin) para filtrar semanas

    Returns
    -------
    DataFrame con MultiIndex (anio_semana, HYBAS_ID) — listo para sklearn/pulearn.
    Columnas: features dinámicas + estáticas + n_eventos + deslizamiento (target S+1)
    """
    # ------------------------------------------------------------------
    # 1. Features estáticas por cuenca (de HydroSHEDS)
    # ------------------------------------------------------------------
    static_cols = ["HYBAS_ID", "SUB_AREA", "UP_AREA", "DIST_MAIN", "ORDER", "ORDER_"]
    available = [c for c in static_cols if c in gdf_cuencas.columns]
    df_static = pd.DataFrame(gdf_cuencas[available])

    # ------------------------------------------------------------------
    # 2. Features dinámicas semanales (CHIRPS + ERA5)
    # ------------------------------------------------------------------
    df_dinamicas = df_chirps_semanal.merge(
        df_era5_semanal[["anio_semana", "soil_moisture_14d"]],
        on="anio_semana",
        how="left",
    )

    # ------------------------------------------------------------------
    # 3. Join: grid (semana × cuenca) ← features dinámicas ← estáticas
    # ------------------------------------------------------------------
    df = df_grid.merge(df_dinamicas, on="anio_semana", how="left")
    df = df.merge(df_static, on="HYBAS_ID", how="left")

    # ------------------------------------------------------------------
    # 4. Target con horizonte S+1 por cuenca
    #    shift(-1) dentro de cada HYBAS_ID respeta el orden temporal
    # ------------------------------------------------------------------
    df = df.sort_values(["HYBAS_ID", "anio_semana"]).reset_index(drop=True)
    df["deslizamiento_s1"] = (
        df.groupby("HYBAS_ID")["deslizamiento"]
        .shift(-1)
    )

    # ------------------------------------------------------------------
    # 5. Filtrar al período y eliminar última semana (sin target)
    # ------------------------------------------------------------------
    anio_ini, anio_fin = periodo
    semana_ini = pd.Period(f"{anio_ini}-01-01", "W")
    semana_fin = pd.Period(f"{anio_fin}-12-31", "W")
    df = df[
        (df["anio_semana"] >= semana_ini) &
        (df["anio_semana"] <= semana_fin)
    ]
    df = df.dropna(subset=["deslizamiento_s1", "precip_acum_14d"])
    df["deslizamiento_s1"] = df["deslizamiento_s1"].astype(int)

    # Renombrar target para uniformidad con v1/v2
    df = df.rename(columns={"deslizamiento_s1": "deslizamiento"})
    df = df.drop(columns=["n_eventos"], errors="ignore")

    df = df.reset_index(drop=True)
    n_pos = df["deslizamiento"].sum()
    n_neg = (df["deslizamiento"] == 0).sum()
    print(
        f"\nDataset v3 (semana × cuenca) construido:\n"
        f"  Instancias : {len(df):,}\n"
        f"  Positivas  : {n_pos:,} ({100 * n_pos / len(df):.2f}%)\n"
        f"  Negativas  : {n_neg:,} ({100 * n_neg / len(df):.2f}%)\n"
        f"  Cuencas    : {df['HYBAS_ID'].nunique()}\n"
        f"  Semanas    : {df['anio_semana'].nunique()}\n"
        f"  Columnas   : {list(df.columns)}"
    )
    return df
