"""
Aplicación FastAPI — Predicción de deslizamientos en Antioquia.

Arrancar en desarrollo:
    uv run uvicorn src.experiment.api.main:app --reload --port 8000

Con Docker:
    docker compose up
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from experiment.api.dependencies import build_model_state
from experiment.api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Carga el modelo al arrancar; libera recursos al cerrar."""
    logger.info("Cargando modelo desde MLflow Registry...")
    app.state.model = build_model_state()
    if app.state.model.loaded:
        logger.info(
            "Modelo listo: %s v%s",
            app.state.model.model_name,
            app.state.model.model_version,
        )
    else:
        logger.warning("Modelo NO pudo cargarse — /predict retornará 503")
    yield
    logger.info("Aplicación cerrando.")


app = FastAPI(
    title="API de Predicción de Deslizamientos — Antioquia",
    description=(
        "Predicción temprana de deslizamientos a nivel de cuenca hidrográfica "
        "(HydroSHEDS nivel 10). Horizonte: 7 días. "
        "Entrenado con CHIRPS + ERA5-Land + UNGRD (2019-2022)."
    ),
    version="1.0.0",
    contact={
        "name": "Grupo MLOps — Universidad de Medellín",
        "email": "diego.castanedaloaiza@gmail.com",
    },
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router)
