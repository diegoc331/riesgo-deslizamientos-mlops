"""
Evaluación con CV de panel para datos semana × cuenca.

Exporta:
  panel_time_splits          — generador de índices train/val sobre semanas únicas
  evaluar_con_panel_cv       — evalúa un pipeline y retorna métricas por fold
  evaluar_en_grid_completo   — evalúa un modelo entrenado sobre el grid sin filtro PA
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit


def panel_time_splits(df: pd.DataFrame, n_splits: int = 4):
    """
    Genera índices de train/val cronológicos para datos de panel (semana × cuenca).

    Opera sobre semanas únicas (no sobre filas individuales) para garantizar
    que todas las cuencas de una misma semana caen en el mismo fold.
    Garantiza disjunción temporal estricta: ninguna semana aparece en train y val.

    Parameters
    ----------
    df : DataFrame con columna 'anio_semana' (pd.Period o comparable)
    n_splits : número de folds (expanding window)

    Yields
    ------
    train_rows, val_rows : listas de índices de filas del DataFrame original
    """
    semanas_unicas = sorted(df["anio_semana"].unique())
    n_sem = len(semanas_unicas)
    tss = TimeSeriesSplit(n_splits=n_splits)

    for train_sem_idx, val_sem_idx in tss.split(range(n_sem)):
        train_semanas = {semanas_unicas[i] for i in train_sem_idx}
        val_semanas   = {semanas_unicas[i] for i in val_sem_idx}

        # Aserción de disjunción — falla inmediatamente si hay solapamiento
        solapadas = train_semanas & val_semanas
        assert len(solapadas) == 0, (
            f"panel_time_splits: {len(solapadas)} semanas solapadas entre "
            f"train y val — data leakage detectado."
        )

        train_rows = df.index[df["anio_semana"].isin(train_semanas)].tolist()
        val_rows   = df.index[df["anio_semana"].isin(val_semanas)].tolist()
        yield train_rows, val_rows


def evaluar_con_panel_cv(
    pipeline,
    X: pd.DataFrame,
    y: pd.Series,
    df_ref: pd.DataFrame,
    n_splits: int = 4,
) -> dict:
    """
    Evalúa un pipeline con CV de panel y retorna métricas promediadas.

    En cada fold verifica que los conjuntos de semanas de train y val sean
    disjuntos (aserción anti-leakage). Maneja graciosamente folds con clase
    única (los salta con aviso).

    Parameters
    ----------
    pipeline : estimador sklearn con fit/predict[_proba]
    X        : features (mismo índice que df_ref)
    y        : target binario (mismo índice que df_ref)
    df_ref   : DataFrame con columna 'anio_semana' para derivar los splits
    n_splits : número de folds

    Returns
    -------
    dict con claves '{metrica}_mean' y '{metrica}_std' para:
      auc_roc, f1, precision, recall
    """
    metricas: dict[str, list[float]] = {
        "auc_roc": [], "f1": [], "precision": [], "recall": []
    }

    for fold, (train_idx, val_idx) in enumerate(
        panel_time_splits(df_ref, n_splits=n_splits), 1
    ):
        X_tr, y_tr = X.loc[train_idx], y.loc[train_idx]
        X_va, y_va = X.loc[val_idx],   y.loc[val_idx]

        # Aserción de no-solapamiento temporal a nivel de filas
        sem_train = set(df_ref.loc[train_idx, "anio_semana"])
        sem_val   = set(df_ref.loc[val_idx,   "anio_semana"])
        assert len(sem_train & sem_val) == 0, (
            f"Fold {fold}: {len(sem_train & sem_val)} semanas solapadas "
            f"entre train y val — data leakage."
        )

        if y_tr.nunique() < 2 or y_va.nunique() < 2:
            print(f"  Fold {fold}: saltado (clase única en train o val)")
            continue

        try:
            pipeline.fit(X_tr, y_tr)

            if hasattr(pipeline, "predict_proba"):
                y_proba = pipeline.predict_proba(X_va)[:, 1]
                auc = roc_auc_score(y_va, y_proba)
            else:
                y_pred_fold = pipeline.predict(X_va)
                auc = roc_auc_score(y_va, y_pred_fold)

            y_pred = pipeline.predict(X_va)
            metricas["auc_roc"].append(auc)
            metricas["f1"].append(f1_score(y_va, y_pred, zero_division=0))
            metricas["precision"].append(precision_score(y_va, y_pred, zero_division=0))
            metricas["recall"].append(recall_score(y_va, y_pred, zero_division=0))

        except Exception as e:
            print(f"  Fold {fold} error: {e}")

    result: dict[str, float] = {}
    for k, vals in metricas.items():
        arr = np.array(vals) if vals else np.array([0.0])
        result[f"{k}_mean"] = float(arr.mean())
        result[f"{k}_std"]  = float(arr.std())
    return result


def evaluar_en_grid_completo(
    pipeline,
    grid_completo_path: str | Path,
    feature_cols: list[str],
    target_col: str = "deslizamiento",
    anio_inicio: int | None = None,
    anio_fin: int | None = None,
) -> dict:
    """
    Evalúa un pipeline ya entrenado sobre el grid completo (sin filtro PA).

    Esta es la métrica primaria de rendimiento real: el modelo ve todas las
    cuencas × semanas, incluyendo negativos no confirmados (PU-Learning setup).

    Parameters
    ----------
    pipeline          : estimador sklearn ya ajustado con .predict_proba()
    grid_completo_path: ruta a grid_completo_v3.parquet
    feature_cols      : lista de columnas de features usadas en entrenamiento
    target_col        : columna target binaria (default: 'deslizamiento')
    anio_inicio       : año de inicio del período de evaluación (inclusive)
    anio_fin          : año de fin del período de evaluación (inclusive)

    Returns
    -------
    dict con claves: auc_roc, recall, precision, f1, n_total, n_positivos, n_negativos
    """
    df = pd.read_parquet(grid_completo_path)

    # anio_semana guardado como string tipo "2021-01-04/2021-01-10"
    # Extraer anio del inicio del periodo (primeros 4 caracteres)
    if anio_inicio is not None or anio_fin is not None:
        annos = df["anio_semana"].str[:4].astype(int)
        mask  = pd.Series(True, index=df.index)
        if anio_inicio is not None:
            mask &= (annos >= anio_inicio)
        if anio_fin is not None:
            mask &= (annos <= anio_fin)
        df = df[mask]

    # Mantener solo features disponibles en el grid completo
    cols_presentes = [c for c in feature_cols if c in df.columns]
    cols_ausentes  = [c for c in feature_cols if c not in df.columns]
    if cols_ausentes:
        print(f"  [AVISO] Features no presentes en grid completo: {cols_ausentes}")

    df = df.dropna(subset=cols_presentes + [target_col])
    X_eval = df[cols_presentes]
    y_eval = df[target_col]

    if hasattr(pipeline, "predict_proba"):
        y_proba = pipeline.predict_proba(X_eval)[:, 1]
        auc = roc_auc_score(y_eval, y_proba)
    else:
        y_pred_score = pipeline.predict(X_eval)
        auc = roc_auc_score(y_eval, y_pred_score)

    y_pred = pipeline.predict(X_eval)
    n_pos = int(y_eval.sum())
    n_neg = int((y_eval == 0).sum())

    return {
        "auc_roc_full":    float(auc),
        "recall_full":     float(recall_score(y_eval, y_pred, zero_division=0)),
        "precision_full":  float(precision_score(y_eval, y_pred, zero_division=0)),
        "f1_full":         float(f1_score(y_eval, y_pred, zero_division=0)),
        "n_total_full":    n_pos + n_neg,
        "n_positivos_full": n_pos,
        "n_negativos_full": n_neg,
    }
