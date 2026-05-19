"""
Tests unitarios para la API FastAPI.

Usa TestClient de Starlette con un modelo mock para evitar
dependencia de MLflow Registry en el entorno de CI.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixture: ModelState mock reutilizable
# ---------------------------------------------------------------------------


def _build_mock_state():
    """Construye un ModelState mockeado sin necesidad de MLflow."""
    from experiment.api.dependencies import ModelState

    mock_pipeline = MagicMock()
    mock_pipeline.predict_proba.return_value = np.array([[0.25, 0.75]])
    mock_pipeline.predict.return_value = np.array([1])

    cfg_mock = MagicMock()
    cfg_mock.geo.departamento = "antioquia"
    cfg_mock.periodo.anio_inicio = 2019
    cfg_mock.periodo.anio_fin = 2022
    cfg_mock.all_features = [
        "precip_acum_14d",
        "precip_max_diario_14d",
        "precip_dias_lluvia_14d",
        "precip_acum_7d",
        "precip_acum_3d",
        "SUB_AREA",
        "UP_AREA",
        "DIST_MAIN",
        "ORDER",
        "soil_moisture_14d",
        "semana_sin",
        "semana_cos",
        "mes_sin",
        "mes_cos",
    ]
    cfg_mock.espacial.granularidad = "cuenca"

    return ModelState(
        pipeline=mock_pipeline,
        model_name="antioquia_deslizamiento_v3_cuenca",
        model_version="1",
        loaded=True,
        cfg=cfg_mock,
    )


@pytest.fixture
def client():
    """TestClient con ModelState mockeado (sin MLflow real).

    Parchea build_model_state para que el lifespan de FastAPI use el mock
    en lugar de intentar conectarse a MLflow Registry.
    """
    from experiment.api.main import app

    mock_state = _build_mock_state()

    with patch("experiment.api.main.build_model_state", return_value=mock_state):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


@pytest.fixture
def valid_payload() -> dict:
    """Payload válido para POST /predict."""
    return {
        "hybas_id": 4080792720,
        "precip_acum_14d": 82.4,
        "precip_acum_7d": 45.1,
        "precip_acum_3d": 18.2,
        "precip_max_diario_14d": 22.7,
        "precip_dias_lluvia_14d": 9.0,
        "SUB_AREA": 245.8,
        "UP_AREA": 1823.4,
        "DIST_MAIN": 18.6,
        "ORDER": 4,
        "soil_moisture_14d": 0.31,
        "semana_sin": 0.83,
        "semana_cos": 0.56,
        "mes_sin": 0.87,
        "mes_cos": 0.50,
    }


# ---------------------------------------------------------------------------
# Tests: endpoints de salud
# ---------------------------------------------------------------------------


def test_liveness_endpoint(client):
    """GET /health/live siempre debe devolver 200."""
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


def test_health_endpoint_model_loaded(client):
    """GET /health devuelve status=ok cuando el modelo está cargado."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["modelo_cargado"] is True
    assert body["modelo_nombre"] == "antioquia_deslizamiento_v3_cuenca"


def test_readiness_endpoint_model_loaded(client):
    """GET /health/ready devuelve 200 cuando el modelo está listo."""
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_root_endpoint(client):
    """GET / devuelve información del servicio."""
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert "servicio" in body
    assert "docs" in body


# ---------------------------------------------------------------------------
# Tests: endpoint /predict
# ---------------------------------------------------------------------------


def test_predict_valido(client, valid_payload):
    """POST /predict con payload válido devuelve probabilidad y nivel de riesgo."""
    resp = client.post("/predict", json=valid_payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["hybas_id"] == valid_payload["hybas_id"]
    assert 0.0 <= body["probabilidad_deslizamiento"] <= 1.0
    assert body["nivel_riesgo"] in ("Bajo", "Medio", "Alto")
    assert "timestamp" in body


def test_predict_nivel_alto_para_proba_075(client, valid_payload):
    """Con probabilidad 0.75, nivel_riesgo debe ser 'Alto'."""
    resp = client.post("/predict", json=valid_payload)
    assert resp.status_code == 200
    assert resp.json()["nivel_riesgo"] == "Alto"


def test_predict_falta_campo_requerido(client, valid_payload):
    """POST /predict sin campo requerido debe devolver 422 (validación Pydantic)."""
    payload_incompleto = {
        k: v for k, v in valid_payload.items() if k != "precip_acum_14d"
    }
    resp = client.post("/predict", json=payload_incompleto)
    assert resp.status_code == 422


def test_predict_precip_negativa_rechazada(client, valid_payload):
    """Precipitación negativa debe ser rechazada por Pydantic (ge=0)."""
    payload_invalido = {**valid_payload, "precip_acum_14d": -5.0}
    resp = client.post("/predict", json=payload_invalido)
    assert resp.status_code == 422


def test_predict_hybas_id_en_respuesta(client, valid_payload):
    """El hybas_id del request debe aparecer en la respuesta."""
    resp = client.post("/predict", json=valid_payload)
    assert resp.json()["hybas_id"] == valid_payload["hybas_id"]


# ---------------------------------------------------------------------------
# Tests: endpoint /predict/batch
# ---------------------------------------------------------------------------


def test_predict_batch_multiples_cuencas(valid_payload):
    """POST /predict/batch devuelve resultados para cada cuenca enviada."""
    from experiment.api.main import app

    mock_state = _build_mock_state()
    # predict_proba devuelve 3 filas para 3 cuencas
    mock_state.pipeline.predict_proba.return_value = np.array(
        [[0.25, 0.75], [0.70, 0.30], [0.45, 0.55]]
    )
    mock_state.pipeline.predict.return_value = np.array([1, 0, 1])

    with patch("experiment.api.main.build_model_state", return_value=mock_state):
        with TestClient(app) as c:
            payload2 = {**valid_payload, "hybas_id": 4080792721}
            payload3 = {**valid_payload, "hybas_id": 4080792722}
            batch_payload = {"cuencas": [valid_payload, payload2, payload3]}
            resp = c.post("/predict/batch", json=batch_payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["n_cuencas"] == 3
    assert len(body["resultados"]) == 3
    assert "semana" in body
    assert "alto_riesgo" in body


# ---------------------------------------------------------------------------
# Tests: endpoint /metadata
# ---------------------------------------------------------------------------


def test_metadata_endpoint(client):
    """GET /metadata devuelve información del modelo."""
    resp = client.get("/metadata")
    assert resp.status_code == 200
    body = resp.json()
    assert body["departamento"] == "antioquia"
    assert body["n_features"] == 14
    assert body["granularidad"] == "cuenca"
    assert 0 < body["umbral_staging_auc"] < 1
