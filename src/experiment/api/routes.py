"""
Endpoints de la API de predicción de deslizamientos.

Rutas:
  GET  /             — info del servicio
  GET  /health       — estado del modelo cargado
  GET  /metadata     — metadatos del modelo en producción
  POST /predict      — predicción para una cuenca
  POST /predict/batch — predicción para múltiples cuencas (semana completa)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from experiment.api.dependencies import classify_risk
from experiment.api.schemas import (
    BatchPredictRequest,
    BatchPredictResponse,
    HealthResponse,
    MetadataResponse,
    PredictRequest,
    PredictResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _request_to_df(req: PredictRequest, feature_cols: list[str]) -> pd.DataFrame:
    """
    Convierte un PredictRequest a DataFrame respetando el orden exacto de
    cfg.all_features (base + hidrobasins + seasonality + era5).

    El orden importa: sklearn usa X.values internamente y el modelo fue entrenado
    con las columnas en el orden de cfg.all_features.
    """
    row = {col: getattr(req, col, np.nan) for col in feature_cols}
    return pd.DataFrame([row], columns=feature_cols)


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------


@router.get("/", tags=["info"])
def root():
    return {
        "servicio": "API de predicción de deslizamientos — Antioquia",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse, tags=["salud"])
def health(request: Request):
    state = request.app.state.model
    return HealthResponse(
        status="ok" if state.loaded else "degradado",
        modelo_cargado=state.loaded,
        modelo_nombre=state.model_name or None,
        modelo_version=state.model_version or None,
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# GET /health/live
# ---------------------------------------------------------------------------


@router.get("/health/live", tags=["salud"])
def liveness():
    return {"status": "alive"}


# ---------------------------------------------------------------------------
# GET /health/ready
# ---------------------------------------------------------------------------


@router.get("/health/ready", tags=["salud"])
def readiness(request: Request):
    state = request.app.state.model
    if not state.loaded:
        raise HTTPException(status_code=503, detail="Modelo no cargado aún")
    return {"status": "ready"}


# ---------------------------------------------------------------------------
# GET /metadata
# ---------------------------------------------------------------------------


@router.get("/metadata", response_model=MetadataResponse, tags=["info"])
def metadata(request: Request):
    state = request.app.state.model
    if not state.loaded:
        raise HTTPException(status_code=503, detail="Modelo no disponible")
    cfg = state.cfg
    return MetadataResponse(
        modelo_nombre=state.model_name,
        modelo_version=state.model_version,
        departamento=cfg.geo.departamento,
        periodo_entrenamiento=f"{cfg.periodo.anio_inicio}–{cfg.periodo.anio_fin}",
        features=cfg.all_features,
        n_features=len(cfg.all_features),
        granularidad=cfg.espacial.granularidad,
        umbral_staging_auc=0.60,
        umbral_staging_precision=0.006,
        descripcion=(
            "Modelo BaggingPuClassifier entrenado con CHIRPS + ERA5-Land sobre "
            "549 cuencas HydroSHEDS nivel 10 en Antioquia. "
            "Horizonte de predicción: 7 días. AUC-ROC (grid completo): 0.6088."
        ),
    )


# ---------------------------------------------------------------------------
# POST /predict
# ---------------------------------------------------------------------------


@router.post("/predict", response_model=PredictResponse, tags=["predicción"])
def predict(req: PredictRequest, request: Request):
    state = request.app.state.model
    if not state.loaded:
        raise HTTPException(status_code=503, detail="Modelo no disponible")

    try:
        X = _request_to_df(req, state.feature_cols)
        proba = float(state.pipeline.predict_proba(X)[0, 1])
    except Exception as exc:
        logger.error("Error en predicción para hybas_id=%s: %s", req.hybas_id, exc)
        raise HTTPException(status_code=500, detail=f"Error en predicción: {exc}")

    nivel = classify_risk(proba)
    resp = PredictResponse(
        hybas_id=req.hybas_id,
        probabilidad_deslizamiento=round(proba, 4),
        nivel_riesgo=nivel,
        timestamp=datetime.now(timezone.utc),
    )

    # Registrar en log de predicciones para monitoreo de drift
    try:
        from experiment.monitoring.logger import log_prediction

        log_prediction(req.hybas_id, req.model_dump(), proba, nivel)
    except Exception:
        pass  # El logging no debe bloquear la respuesta

    return resp


# ---------------------------------------------------------------------------
# POST /predict/batch
# ---------------------------------------------------------------------------


@router.post("/predict/batch", response_model=BatchPredictResponse, tags=["predicción"])
def predict_batch(req: BatchPredictRequest, request: Request):
    state = request.app.state.model
    if not state.loaded:
        raise HTTPException(status_code=503, detail="Modelo no disponible")

    rows = [_request_to_df(c, state.feature_cols) for c in req.cuencas]
    X = pd.concat(rows, ignore_index=True)

    try:
        probas = state.pipeline.predict_proba(X)[:, 1]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error en predicción batch: {exc}")

    now = datetime.now(timezone.utc)
    resultados = []
    alto_riesgo = []

    for cuenca, proba in zip(req.cuencas, probas):
        proba_f = round(float(proba), 4)
        nivel = classify_risk(proba_f)
        resultados.append(
            PredictResponse(
                hybas_id=cuenca.hybas_id,
                probabilidad_deslizamiento=proba_f,
                nivel_riesgo=nivel,
                timestamp=now,
            )
        )
        if nivel == "Alto":
            alto_riesgo.append(cuenca.hybas_id)

    semana_iso = now.strftime("%G-W%V")
    return BatchPredictResponse(
        semana=semana_iso,
        n_cuencas=len(resultados),
        resultados=resultados,
        alto_riesgo=alto_riesgo,
    )


# ---------------------------------------------------------------------------
# GET /geojson/cuencas
# ---------------------------------------------------------------------------

_GEOJSON_PATH = Path("data/raw/spatial/cuencas_antioquia.geojson")


@router.get("/geojson/cuencas", tags=["datos"])
def geojson_cuencas():
    """GeoJSON de las 549 cuencas HydroSHEDS nivel 10 (Antioquia)."""
    if not _GEOJSON_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="GeoJSON no encontrado. Ejecutar scripts/convert_gpkg_to_geojson.py primero.",
        )
    return FileResponse(_GEOJSON_PATH, media_type="application/geo+json")


# ---------------------------------------------------------------------------
# GET /impacto
# ---------------------------------------------------------------------------

_IMPACTO_PATH = Path("data/processed/impacto_economico_por_cuenca.csv")


@router.get("/impacto", tags=["datos"])
def impacto_economico():
    """Impacto económico histórico por cuenca UNGRD 2019-2022."""
    if not _IMPACTO_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="Archivo de impacto no encontrado. Ejecutar notebook 05 primero.",
        )
    df = pd.read_csv(_IMPACTO_PATH)
    return df.fillna(0).to_dict(orient="records")


# ---------------------------------------------------------------------------
# GET /predicciones/semana-actual
# ---------------------------------------------------------------------------

_PRED_PATH = Path("data/processed/predicciones_semana_actual.json")


@router.get("/predicciones/semana-actual", tags=["predicción"])
def predicciones_semana_actual():
    """
    Predicciones ML para las 549 cuencas de la semana más reciente.

    Generado por pipelines/prediction_flow.py (Prefect, schedule: lunes 6:30 AM).
    Ejecutar manualmente:
        uv run python pipelines/prediction_flow.py
    """
    if not _PRED_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "No hay predicciones disponibles. "
                "Ejecutar: uv run python pipelines/prediction_flow.py"
            ),
        )
    with open(_PRED_PATH, encoding="utf-8") as f:
        return json.load(f)
