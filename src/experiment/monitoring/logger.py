"""
Logger de predicciones en producción.

Cada predicción se registra en logs/predictions.jsonl (append-only).
Este log es la base de datos de referencia para detectar drift.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

_LOG_PATH = Path(__file__).resolve().parents[3] / "logs" / "predictions.jsonl"
logger = logging.getLogger(__name__)


def log_prediction(
    hybas_id: int,
    features: dict,
    probabilidad: float,
    nivel_riesgo: str,
) -> None:
    """
    Registra una predicción en el log JSONL.

    Parameters
    ----------
    hybas_id     : ID de la cuenca HydroSHEDS
    features     : dict con las features enviadas al modelo
    probabilidad : probabilidad predicha (clase positiva)
    nivel_riesgo : 'Bajo' | 'Medio' | 'Alto'
    """
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hybas_id": hybas_id,
        "probabilidad": round(probabilidad, 6),
        "nivel_riesgo": nivel_riesgo,
        "features": {
            k: v for k, v in features.items() if k != "hybas_id" and v is not None
        },
    }

    try:
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("No se pudo escribir en log de predicciones: %s", exc)
