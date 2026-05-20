"""
Scheduling del pipeline de predicción semanal en Prefect.

Ejecutar una vez para registrar el deployment:
    uv run python pipelines/deploy_prediction.py

El flow corre automáticamente cada lunes a las 6:30 AM
(30 min después del training_flow para garantizar que el modelo esté actualizado).
"""

from prediction_flow import prediction_pipeline

if __name__ == "__main__":
    prediction_pipeline.serve(
        name="antioquia-prediccion-semanal",
        cron="30 6 * * 1",  # lunes 06:30 AM
        parameters={},
    )
