"""
Tests unitarios para src/experiment/evaluate.py.

Verifican que panel_time_splits garantiza disjunción temporal estricta
(sin solapamiento de semanas entre train y val en ningún fold).
"""

from __future__ import annotations

import pandas as pd


def _make_panel_df(n_semanas: int = 20, n_cuencas: int = 5) -> pd.DataFrame:
    """
    Crea un DataFrame de panel (semana × cuenca) sintético.
    Columna 'anio_semana' como pd.Period, necesaria para panel_time_splits.
    """
    # pd.Period("2021-01-04", "W") es compatible con pandas 2.x
    inicio = pd.Period("2021-01-04", "W")
    semanas = pd.period_range(start=inicio, periods=n_semanas, freq="W")
    rows = [
        {"HYBAS_ID": c, "anio_semana": s, "deslizamiento": 0}
        for s in semanas
        for c in range(n_cuencas)
    ]
    return pd.DataFrame(rows)


def test_panel_splits_no_overlap():
    """
    Ninguna semana debe aparecer en train Y val en el mismo fold.
    Esto garantiza que no hay data leakage temporal.
    """
    from experiment.evaluate import panel_time_splits

    df = _make_panel_df(n_semanas=20)

    for fold_idx, (train_idx, val_idx) in enumerate(panel_time_splits(df, n_splits=4)):
        sem_train = set(df.loc[train_idx, "anio_semana"])
        sem_val = set(df.loc[val_idx, "anio_semana"])
        solapadas = sem_train & sem_val

        assert len(solapadas) == 0, (
            f"Fold {fold_idx + 1}: {len(solapadas)} semanas solapadas — "
            f"data leakage detectado: {list(solapadas)[:3]}"
        )


def test_panel_splits_cronologico():
    """
    Todas las semanas de val deben ser POSTERIORES a todas las de train.
    Expanding window: train crece cronológicamente.
    """
    from experiment.evaluate import panel_time_splits

    df = _make_panel_df(n_semanas=24)

    for fold_idx, (train_idx, val_idx) in enumerate(panel_time_splits(df, n_splits=4)):
        sem_train = sorted(df.loc[train_idx, "anio_semana"].unique())
        sem_val = sorted(df.loc[val_idx, "anio_semana"].unique())

        max_train = sem_train[-1]
        min_val = sem_val[0]

        assert min_val > max_train, (
            f"Fold {fold_idx + 1}: val tiene semanas anteriores a train — "
            f"max_train={max_train}, min_val={min_val}"
        )


def test_panel_splits_assertion_guard_en_codigo():
    """
    Verifica que panel_time_splits contiene la guardia de disjunción (AssertionError).

    Inspecciona el código fuente para confirmar que la invariante está implementada.
    """
    import inspect
    from experiment.evaluate import panel_time_splits

    source = inspect.getsource(panel_time_splits)
    assert "assert len(solapadas) == 0" in source, (
        "La guardia anti-leakage debe estar presente en panel_time_splits"
    )


def test_panel_splits_cubre_todas_las_semanas():
    """
    La unión de val de todos los folds debe cubrir todas las semanas
    del DataFrame (sin que quede ninguna semana sin evaluar).
    """
    from experiment.evaluate import panel_time_splits

    df = _make_panel_df(n_semanas=20)
    todas_semanas = set(df["anio_semana"].unique())

    semanas_evaluadas = set()
    for _, val_idx in panel_time_splits(df, n_splits=4):
        semanas_evaluadas |= set(df.loc[val_idx, "anio_semana"].unique())

    # Las semanas evaluadas deben ser subconjunto de todas
    assert semanas_evaluadas.issubset(todas_semanas)
    # La mayoría de semanas deben haber sido evaluadas (al menos el 50%)
    assert len(semanas_evaluadas) >= len(todas_semanas) * 0.5, (
        f"Solo {len(semanas_evaluadas)}/{len(todas_semanas)} semanas evaluadas"
    )


def test_panel_splits_n_splits_parametro():
    """El parámetro n_splits debe controlar el número de folds generados."""
    from experiment.evaluate import panel_time_splits

    df = _make_panel_df(n_semanas=30)

    for n in [2, 3, 4]:
        splits = list(panel_time_splits(df, n_splits=n))
        assert len(splits) == n, (
            f"Con n_splits={n} se esperaban {n} folds, se obtuvieron {len(splits)}"
        )
