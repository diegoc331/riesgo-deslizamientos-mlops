"""
Dependencias compartidas: carga del modelo y configuración.

El modelo se carga UNA sola vez al arrancar la app (lifespan) y se
inyecta en cada endpoint mediante state de FastAPI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import mlflow
import mlflow.sklearn

from experiment.config import ExperimentConfig, load_config

logger = logging.getLogger(__name__)

# src/experiment/api/dependencies.py → parents[3] = riesgo-deslizamientos-mlops/
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class ModelState:
    """Estado global del modelo cargado en memoria."""

    pipeline: Optional[Any] = None
    model_name: str = ""
    model_version: str = ""
    cfg: Optional[ExperimentConfig] = None
    loaded: bool = False
    feature_cols: list[str] = field(default_factory=list)


def load_model_from_registry(cfg: ExperimentConfig) -> tuple[Any, str, str]:
    """
    Carga el modelo más reciente en stage Staging (o cualquier etapa) desde MLflow Registry.

    Devuelve (pipeline, model_name, version).
    """
    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
    model_name = f"{cfg.geo.departamento}_deslizamiento_v3_cuenca"
    client = mlflow.tracking.MlflowClient(cfg.mlflow_tracking_uri)

    # Buscar primero en Staging, luego cualquier versión disponible
    for filter_stage in ("Staging", None):
        filter_str = f"name='{model_name}'"
        if filter_stage:
            filter_str += f" and tags.stage='{filter_stage}'"
        try:
            # Intentar cargar por alias de stage (ruta semántica)
            stage_label = filter_stage or "latest"
            model_uri = f"models:/{model_name}/{filter_stage or 'None'}"
            pipeline = mlflow.sklearn.load_model(model_uri)

            # Obtener versión sin usar get_latest_versions (deprecado en MLflow 2.9+)
            versions = client.search_model_versions(f"name='{model_name}'")
            # Preferir versión en Staging; si no, la más reciente
            staged = [
                v for v in versions if v.current_stage == (filter_stage or "None")
            ]
            version = (
                str(max(int(v.version) for v in staged))
                if staged
                else (
                    str(max(int(v.version) for v in versions))
                    if versions
                    else "unknown"
                )
            )
            logger.info(
                "Modelo cargado: %s (stage=%s, v=%s)", model_name, stage_label, version
            )
            return pipeline, model_name, version
        except Exception as exc:
            logger.warning(
                "No se pudo cargar %s en stage '%s': %s", model_name, filter_stage, exc
            )

    raise RuntimeError(
        f"No hay versiones disponibles del modelo '{model_name}' en MLflow Registry.\n"
        f"Ejecuta primero: uv run python pipelines/training_flow.py"
    )


def build_model_state() -> ModelState:
    """Inicializa el ModelState cargando config y modelo."""
    state = ModelState()
    try:
        cfg = load_config(project_root=_PROJECT_ROOT)
        state.cfg = cfg
        state.feature_cols = cfg.all_features

        pipeline, model_name, version = load_model_from_registry(cfg)
        state.pipeline = pipeline
        state.model_name = model_name
        state.model_version = version
        # Usar las features con las que el modelo fue entrenado (fuente de verdad)
        if hasattr(pipeline, "feature_names_in_"):
            state.feature_cols = list(pipeline.feature_names_in_)
        state.loaded = True
    except Exception as exc:
        logger.error("Error al cargar el modelo: %s", exc)
        # Estado parcial — /health lo reportará como degradado

    return state


def classify_risk(proba: float) -> str:
    """Clasifica la probabilidad en nivel de riesgo."""
    if proba < 0.30:
        return "Bajo"
    if proba < 0.60:
        return "Medio"
    return "Alto"
