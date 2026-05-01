"""Limpieza, join espacial-temporal y feature engineering."""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pandas as pd

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


def aggregate_monthly(df_ideam: pd.DataFrame, df_ungrd: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega a nivel (departamento, año-mes).

    - IDEAM  → suma y máximo mensual de precipitación
    - UNGRD  → conteo de eventos hidrometeorológicos
    - target = 1 si hubo ≥1 evento ese mes en ese departamento
    """
    precip_monthly = (
        df_ideam.groupby(["departamento", "anio_mes"], observed=True)
        .agg(
            precip_suma=("precip_mm", "sum"),
            precip_max=("precip_mm", "max"),
            precip_dias_lluvia=("precip_mm", lambda x: (x > 0).sum()),
        )
        .reset_index()
    )

    eventos_monthly = (
        df_ungrd.groupby(["departamento", "anio_mes"], observed=True)
        .size()
        .reset_index(name="n_eventos")
    )

    df = precip_monthly.merge(eventos_monthly, on=["departamento", "anio_mes"], how="left")
    df["n_eventos"] = df["n_eventos"].fillna(0).astype(int)
    df["target"] = (df["n_eventos"] >= 1).astype(int)
    df["anio"] = df["anio_mes"].dt.year
    df["mes"] = df["anio_mes"].dt.month
    df = df.sort_values(["departamento", "anio_mes"]).reset_index(drop=True)

    positivos = df["target"].sum()
    print(f"Dataset unido: {len(df):,} filas | "
          f"con evento: {positivos:,} ({df['target'].mean():.1%})")
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula acumulados de precipitación rezagados por departamento.

    - precip_lag1   : precipitación mes anterior
    - precip_acum3m : suma últimos 3 meses
    - precip_acum6m : suma últimos 6 meses
    - precip_max3m  : máximo mensual en últimos 3 meses
    """
    df = df.copy().sort_values(["departamento", "anio_mes"])

    df["precip_lag1"] = df.groupby("departamento", group_keys=False)["precip_suma"].transform(
        lambda x: x.shift(1)
    )
    df["precip_acum3m"] = df.groupby("departamento", group_keys=False)["precip_suma"].transform(
        lambda x: x.shift(1).rolling(3, min_periods=1).sum()
    )
    df["precip_acum6m"] = df.groupby("departamento", group_keys=False)["precip_suma"].transform(
        lambda x: x.shift(1).rolling(6, min_periods=1).sum()
    )
    df["precip_max3m"] = df.groupby("departamento", group_keys=False)["precip_max"].transform(
        lambda x: x.shift(1).rolling(3, min_periods=1).max()
    )

    df = df.dropna(subset=["precip_lag1", "precip_acum3m"])
    print(f"Dataset con features: {len(df):,} filas listas para correlación")
    return df


def save_processed(df: pd.DataFrame, name: str = "dataset_correlacion.csv") -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / name
    df.to_csv(path, index=False)
    print(f"Guardado en {path}")
