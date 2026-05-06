"""Limpieza, join espacial-temporal y feature engineering."""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pandas as pd
import numpy as np

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
