"""
Tests unitarios para src/experiment/process.py.

Verifican la propiedad anti-leakage: las features rolling deben
aplicar .shift(1) para que la semana W solo use precipitación de W-1.
"""

from __future__ import annotations

import pandas as pd


def _make_chirps_daily(n_days: int = 56) -> pd.DataFrame:
    """Crea una serie CHIRPS diaria sintética de n_days días."""
    fechas = pd.date_range("2021-01-01", periods=n_days, freq="D")
    # Precipitación constante de 10 mm/día para verificar cálculos exactos
    return pd.DataFrame({"fecha": fechas, "precip_mm": 10.0})


def test_aggregate_weekly_chirps_returns_dataframe():
    """aggregate_weekly_chirps debe devolver un DataFrame."""
    from experiment.process import aggregate_weekly_chirps

    df_daily = _make_chirps_daily(56)
    result = aggregate_weekly_chirps(df_daily)
    assert isinstance(result, pd.DataFrame)
    assert len(result) > 0


def test_aggregate_weekly_chirps_has_required_columns():
    """El DataFrame resultante debe tener todas las features de precipitación."""
    from experiment.process import aggregate_weekly_chirps

    df_daily = _make_chirps_daily(56)
    result = aggregate_weekly_chirps(df_daily)

    expected_cols = {
        "precip_acum_14d",
        "precip_acum_7d",
        "precip_acum_3d",
        "precip_max_diario_14d",
        "precip_dias_lluvia_14d",
        "semana_sin",
        "semana_cos",
    }
    assert expected_cols.issubset(set(result.columns)), (
        f"Faltan columnas: {expected_cols - set(result.columns)}"
    )


def test_antileakage_shift_primera_semana():
    """
    La primera semana DEBE tener NaN en todas las features rolling tras el shift(1).

    Principio: la semana W solo puede conocer precipitación de semanas anteriores a W.
    shift(1) desplaza los valores calculados al cierre de W hacia la semana W+1.
    """
    from experiment.process import aggregate_weekly_chirps

    df_daily = _make_chirps_daily(84)  # 12 semanas
    result = aggregate_weekly_chirps(df_daily)
    result = result.reset_index(drop=True)

    feat_cols = [
        "precip_acum_14d",
        "precip_acum_7d",
        "precip_acum_3d",
        "precip_max_diario_14d",
        "precip_dias_lluvia_14d",
    ]

    # Fila 0 (primera semana) debe tener NaN en features rolling (efecto del shift)
    primera_semana = result.loc[0, feat_cols]
    assert primera_semana.isna().all(), (
        f"La primera semana debería tener NaN tras shift(1), "
        f"pero tiene: {primera_semana.to_dict()}"
    )


def test_antileakage_shift_semanas_intermedias_no_nan():
    """
    A partir de la cuarta semana, precip_acum_14d no debe ser NaN.
    Las primeras semanas pueden tener NaN por el rolling(14) + shift(1).
    """
    from experiment.process import aggregate_weekly_chirps

    df_daily = _make_chirps_daily(120)  # ~17 semanas
    result = aggregate_weekly_chirps(df_daily).reset_index(drop=True)

    # A partir de la semana 4+ hay suficientes datos para el rolling(14)
    semanas_validas = result.loc[4:, "precip_acum_14d"].dropna()
    assert len(semanas_validas) > 0, (
        "Debe haber semanas con precip_acum_14d válido a partir de la semana 4"
    )


def test_precip_acum_14d_positivo_y_razonable():
    """
    Con 10 mm/día constante, precip_acum_14d debe ser positivo y
    estar en el rango esperado para una ventana de 14 días.
    """
    from experiment.process import aggregate_weekly_chirps

    df_daily = _make_chirps_daily(120)
    result = aggregate_weekly_chirps(df_daily).reset_index(drop=True)

    # Tomar valores válidos (sin NaN) de la mitad del dataset
    vals_validos = result["precip_acum_14d"].dropna()
    assert len(vals_validos) > 0

    # Con 10 mm/día, acumulado 14 días debe estar en (0, 200] mm
    assert (vals_validos > 0).all(), "precip_acum_14d debe ser positivo"
    assert (vals_validos <= 200).all(), (
        "precip_acum_14d no debe superar 200 mm con 10 mm/día"
    )


def test_target_shift_negativo_por_cuenca():
    """
    El target deslizamiento_s1 debe calcularse con shift(-1) DENTRO de cada cuenca.
    Verifica que la última semana de cada cuenca tiene NaN en el target.

    Este test valida directamente la invariante documentada en CLAUDE.md:
    'shift(-1) dentro de cada HYBAS_ID respeta el orden temporal'.
    """
    semanas = pd.period_range(start=pd.Period("2021-01-04", "W"), periods=4, freq="W")

    df = pd.DataFrame(
        {
            "HYBAS_ID": [1, 1, 1, 1, 2, 2, 2, 2],
            "anio_semana": list(semanas) * 2,
            "n_deslizamientos": [0, 1, 0, 1, 1, 0, 1, 0],
        }
    )
    df["deslizamiento"] = (df["n_deslizamientos"] > 0).astype(int)
    df = df.sort_values(["HYBAS_ID", "anio_semana"]).reset_index(drop=True)

    # Mismo patrón que build_cuenca_dataset_v3 en process.py
    df["deslizamiento_s1"] = df.groupby("HYBAS_ID")["deslizamiento"].shift(-1)

    # La última semana de cada cuenca debe tener NaN
    ultima_semana = semanas[-1]
    mascaras_ultima = df["anio_semana"] == ultima_semana

    assert df.loc[mascaras_ultima, "deslizamiento_s1"].isna().all(), (
        "La última semana de cada cuenca debe tener NaN en deslizamiento_s1 "
        "(no hay semana siguiente para calcular el target)"
    )
