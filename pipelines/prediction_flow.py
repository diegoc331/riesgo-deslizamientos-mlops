"""
Pipeline de inferencia semanal — Antioquia deslizamientos.

Carga la última semana del grid completo, aplica el modelo registrado en
MLflow Registry y guarda el resultado en:
  data/processed/predicciones_semana_actual.json

La API FastAPI sirve ese archivo con GET /predicciones/semana-actual.
El frontend recarga cada 6 horas para mostrar el mapa actualizado.

Ejecución manual:
    uv run python pipelines/prediction_flow.py

Scheduling automático (Prefect):
    uv run python pipelines/deploy_prediction.py
    → se ejecuta cada lunes a las 6 AM (después del ETL + training)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

import mlflow
import mlflow.sklearn
import pandas as pd
from prefect import flow, get_run_logger, task

from experiment.config import ExperimentConfig, load_config

_DEFAULT_GRID_FULL = str(_PROJECT_ROOT / "data" / "processed" / "grid_completo_v3.parquet")
_DEFAULT_OUTPUT = str(_PROJECT_ROOT / "data" / "processed" / "predicciones_semana_actual.json")


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@task(name="cargar-ultima-semana")
def task_cargar_ultima_semana(grid_full_path: str, cfg: ExperimentConfig) -> tuple[pd.DataFrame, list[str], str]:
    logger = get_run_logger()

    df = pd.read_parquet(grid_full_path)
    df["anio_semana"] = pd.PeriodIndex(df["anio_semana"], freq="W")
    df = df.sort_values("anio_semana")

    ultima_semana = df["anio_semana"].max()
    df_semana = df[df["anio_semana"] == ultima_semana].copy().reset_index(drop=True)

    feature_cols = [f for f in cfg.all_features if f in df_semana.columns]
    logger.info(
        f"Semana de inferencia: {ultima_semana} | "
        f"cuencas: {len(df_semana)} | features: {len(feature_cols)}"
    )
    return df_semana, feature_cols, str(ultima_semana)


@task(name="cargar-modelo-registry")
def task_cargar_modelo(cfg: ExperimentConfig, model_name: str):
    logger = get_run_logger()
    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)

    # Intentar Staging primero, luego cualquier versión disponible
    for stage in ("Staging", "None"):
        try:
            model = mlflow.sklearn.load_model(f"models:/{model_name}/{stage}")
            logger.info(f"Modelo cargado: {model_name}/{stage}")
            return model
        except Exception:
            continue

    raise RuntimeError(
        f"No se encontró el modelo '{model_name}' en MLflow Registry. "
        "Ejecutar training_flow.py primero."
    )


@task(name="inferencia-549-cuencas")
def task_inferir(
    df_semana: pd.DataFrame,
    feature_cols: list[str],
    model,
    semana: str,
    output_path: str,
) -> dict:
    logger = get_run_logger()

    X = df_semana[feature_cols]
    probas = model.predict_proba(X)[:, 1]

    ahora = datetime.now(timezone.utc).isoformat()
    resultados = []
    alto_riesgo = []

    for i, row in df_semana.iterrows():
        prob = round(float(probas[i]), 4)
        nivel = "Alto" if prob >= 0.60 else "Medio" if prob >= 0.30 else "Bajo"
        hybas = int(row["HYBAS_ID"])
        resultados.append({
            "hybas_id": hybas,
            "probabilidad_deslizamiento": prob,
            "nivel_riesgo": nivel,
            "timestamp": ahora,
        })
        if nivel == "Alto":
            alto_riesgo.append(hybas)

    n_alto = len(alto_riesgo)
    n_medio = sum(1 for r in resultados if r["nivel_riesgo"] == "Medio")
    n_bajo = sum(1 for r in resultados if r["nivel_riesgo"] == "Bajo")
    logger.info(
        f"Inferencia completa: {len(resultados)} cuencas | "
        f"Alto={n_alto} Medio={n_medio} Bajo={n_bajo}"
    )

    output = {
        "semana": semana,
        "n_cuencas": len(resultados),
        "resultados": resultados,
        "alto_riesgo": alto_riesgo,
        "resumen": {"alto": n_alto, "medio": n_medio, "bajo": n_bajo},
        "generado_utc": ahora,
        "features_usadas": feature_cols,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)

    logger.info(f"Predicciones guardadas en {output_path}")
    return output


# ---------------------------------------------------------------------------
# Flow principal
# ---------------------------------------------------------------------------


@flow(name="antioquia-deslizamientos-prediction", log_prints=True)
def prediction_pipeline(
    grid_full_path: str | None = None,
    output_path: str | None = None,
    model_name: str | None = None,
    config_path: str | None = None,
) -> dict:
    """
    Genera predicciones semanales para las 549 cuencas de Antioquia
    usando el modelo registrado en MLflow Registry.

    1. Carga la última semana disponible del grid_completo_v3.parquet
    2. Carga el modelo desde MLflow (Staging o None)
    3. Ejecuta predict_proba() para todas las cuencas
    4. Guarda resultados en data/processed/predicciones_semana_actual.json
    5. La API sirve ese JSON con GET /predicciones/semana-actual

    Parameters
    ----------
    grid_full_path : ruta al parquet completo (None = default)
    output_path    : donde guardar el JSON (None = default)
    model_name     : nombre en MLflow Registry (None = auto desde config)
    config_path    : ruta YAML (None = auto-detectar)
    """
    cfg = load_config(config_path, project_root=_PROJECT_ROOT)

    if grid_full_path is None:
        grid_full_path = _DEFAULT_GRID_FULL
    if output_path is None:
        output_path = _DEFAULT_OUTPUT
    if model_name is None:
        model_name = f"{cfg.geo.departamento}_deslizamiento_v3_cuenca"

    df_semana, feature_cols, semana = task_cargar_ultima_semana(grid_full_path, cfg)
    model = task_cargar_modelo(cfg, model_name)
    resultado = task_inferir(df_semana, feature_cols, model, semana, output_path)

    return resultado


if __name__ == "__main__":
    resultado = prediction_pipeline()
    print(f"\nSemana: {resultado['semana']}")
    print(f"Cuencas: {resultado['n_cuencas']}")
    r = resultado["resumen"]
    print(f"Alto: {r['alto']} | Medio: {r['medio']} | Bajo: {r['bajo']}")
    print(f"Guardado en: {_DEFAULT_OUTPUT}")
