"""
Scheduling y deployment del pipeline de deslizamientos con Prefect.

Registra un único deployment en el servidor Prefect (localhost:4200):
  antioquia-weekly  — ETL + entrenamiento cada lunes 5am

Prerequisitos:
  1. prefect server start                          (en otra terminal)
  2. prefect work-pool create --type process local-process
  3. uv run python pipelines/deploy.py            (este script)
  4. prefect worker start --pool local-process    (en otra terminal)

Verificar en: http://localhost:4200/deployments
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT / "pipelines"))

_WORK_POOL = "local-process"

# from_source apunta al directorio raíz del proyecto para que el worker
# sepa dónde está el código cuando arranca el proceso localmente.
_full_pipeline = __import__("data_flow", fromlist=["full_pipeline"]).full_pipeline

_full_deployment = _full_pipeline.from_source(
    source=str(_PROJECT_ROOT),
    entrypoint="pipelines/data_flow.py:full_pipeline",
)


if __name__ == "__main__":
    print("Registrando deployment en el servidor Prefect...")

    _full_deployment.deploy(
        name="antioquia-weekly",
        work_pool_name=_WORK_POOL,
        cron="0 5 * * 1",          # lunes 5am — ETL + entrenamiento
        parameters={
            "umbral_auc":       0.60,
            "umbral_precision": 0.10,
        },
        tags=["etl", "training", "mlflow", "antioquia", "deslizamientos"],
        description=(
            "Pipeline semanal completo: ETL (CHIRPS+UNGRD) seguido de entrenamiento, "
            "evaluacion en grid completo y promocion a Staging si AUC>=0.60 y Precision>=0.10"
        ),
    )
    print("[OK] antioquia-weekly registrado (lunes 5am)")

    print()
    print("Deployment registrado. Verifica en: http://localhost:4200/deployments")
    print("Para activar el schedule, inicia el worker:")
    print("  prefect worker start --pool local-process")
