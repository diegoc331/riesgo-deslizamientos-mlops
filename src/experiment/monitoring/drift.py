"""
Detección de data drift en features de precipitación.

Flujo:
  1. save_reference(df)   — guarda estadísticas de referencia (en entrenamiento)
  2. detect_drift(df_new) — KS test por feature vs referencia

Uso:
    from experiment.monitoring.drift import save_reference, detect_drift

    # Al entrenar:
    save_reference(X_train)

    # En producción (periódicamente):
    resultado = detect_drift(df_reciente)
    if resultado["drift_detectado"]:
        print("Alerta: drift en", resultado["features_con_drift"])
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)

_STATS_PATH = (
    Path(__file__).resolve().parents[4] / "data" / "processed" / "reference_stats.json"
)

# Features de precipitación que monitoreamos (más sensibles al cambio climático)
_PRECIP_FEATURES = [
    "precip_acum_14d",
    "precip_acum_7d",
    "precip_acum_3d",
    "precip_max_diario_14d",
    "precip_dias_lluvia_14d",
    "soil_moisture_14d",
]

_ALPHA = 0.05  # umbral de significancia para KS test


def save_reference(df: pd.DataFrame) -> None:
    """
    Guarda estadísticas de referencia (media, std, percentiles) de las features
    de precipitación para uso futuro en detect_drift().

    Parameters
    ----------
    df : DataFrame con las features de entrenamiento (sin target)
    """
    _STATS_PATH.parent.mkdir(parents=True, exist_ok=True)

    stats_dict: dict[str, Any] = {}
    for col in _PRECIP_FEATURES:
        if col not in df.columns:
            continue
        vals = df[col].dropna().values
        if len(vals) == 0:
            continue
        stats_dict[col] = {
            "mean": float(np.mean(vals)),
            "std": float(np.std(vals)),
            "p25": float(np.percentile(vals, 25)),
            "p50": float(np.percentile(vals, 50)),
            "p75": float(np.percentile(vals, 75)),
            "n": int(len(vals)),
            # Guardamos una muestra representativa para el KS test
            "sample": vals[:: max(1, len(vals) // 500)].tolist(),
        }

    with _STATS_PATH.open("w", encoding="utf-8") as f:
        json.dump(stats_dict, f, ensure_ascii=False, indent=2)

    logger.info(
        "Estadísticas de referencia guardadas en %s (%d features)",
        _STATS_PATH,
        len(stats_dict),
    )


def detect_drift(df_new: pd.DataFrame, alpha: float = _ALPHA) -> dict[str, Any]:
    """
    Detecta drift en features de precipitación mediante el test KS de dos muestras.

    Parameters
    ----------
    df_new : DataFrame con datos recientes de producción (mismas columnas que el train)
    alpha  : nivel de significancia (default 0.05)

    Returns
    -------
    dict con claves:
      - drift_detectado   : bool
      - features_con_drift: list[str]
      - detalle           : dict[feature, {p_value, estadistico, drift}]
    """
    if not _STATS_PATH.exists():
        logger.warning(
            "No se encontraron estadísticas de referencia en %s. "
            "Ejecuta save_reference(X_train) primero.",
            _STATS_PATH,
        )
        return {"drift_detectado": False, "features_con_drift": [], "detalle": {}}

    with _STATS_PATH.open("r", encoding="utf-8") as f:
        ref_stats = json.load(f)

    detalle: dict[str, Any] = {}
    features_con_drift: list[str] = []

    for col in _PRECIP_FEATURES:
        if col not in ref_stats or col not in df_new.columns:
            continue

        ref_sample = np.array(ref_stats[col]["sample"])
        new_sample = df_new[col].dropna().values

        if len(new_sample) < 10:
            logger.debug("Muestra insuficiente para %s (%d obs)", col, len(new_sample))
            continue

        ks_stat, p_value = stats.ks_2samp(ref_sample, new_sample)
        tiene_drift = bool(p_value < alpha)

        detalle[col] = {
            "estadistico_ks": round(float(ks_stat), 4),
            "p_value": round(float(p_value), 6),
            "drift": tiene_drift,
            "n_referencia": len(ref_sample),
            "n_produccion": len(new_sample),
        }

        if tiene_drift:
            features_con_drift.append(col)
            logger.warning(
                "DRIFT detectado en '%s': KS=%.3f, p=%.4f (alpha=%.2f)",
                col,
                ks_stat,
                p_value,
                alpha,
            )

    drift_detectado = len(features_con_drift) > 0

    if drift_detectado:
        logger.warning(
            "Data drift detectado en %d features: %s",
            len(features_con_drift),
            features_con_drift,
        )
    else:
        logger.info("Sin drift detectado en %d features monitoreadas.", len(detalle))

    return {
        "drift_detectado": drift_detectado,
        "features_con_drift": features_con_drift,
        "detalle": detalle,
    }
