# Predicción de Deslizamientos — Antioquia, Colombia

Sistema de clasificación binaria para predecir la ocurrencia de deslizamientos en
Antioquia con 7 días de anticipación, usando señales de precipitación acumulada
(CHIRPS v2.0) y reportes históricos de emergencias (UNGRD).

## Arquitectura

```
configs/
    antioquia_deslizamientos.yaml   # single source of truth (parámetros, umbrales)
data/
    raw/                            # ungrd_emergencias.csv (descargado)
    processed/
        grid_cuencas_v3.parquet     # 7,629 instancias — pseudo-ausencias (entrenamiento)
        grid_completo_v3.parquet    # 114,741 instancias — todas las cuencas (evaluación)
        best_params.json            # hiperparámetros óptimos por modelo
notebooks/
    03_pipeline_v3_cuencas.ipynb    # pipeline v3 completo (referencia)
    04_hyperparameter_tuning.ipynb  # tuning con runs anidados en MLflow
pipelines/
    data_flow.py                    # ETL Prefect: descarga → grid → validación
    training_flow.py                # Entrenamiento Prefect: CV → grid completo → registry
    deploy.py                       # Scheduling semanal (lunes 5am ETL, 7am training)
scripts/
    build_grid_v3.py                # Script standalone para regenerar los grids
src/experiment/
    config.py                       # Pydantic v2: ExperimentConfig, load_config()
    download.py                     # load_chirps(), load_ungrd()
    evaluate.py                     # panel_time_splits(), evaluar_con_panel_cv(), evaluar_en_grid_completo()
    process.py                      # aggregate_weekly_chirps() con shift anti-leakage
    registry.py                     # register_best_model(), transition_stage()
    spatial.py                      # download_hydrobasins(), build_event_grid(), generate_pseudo_absences()
    train.py                        # make_pipeline(), get_experimentos()
```

## Stack tecnológico

- **Python 3.13** / uv
- **MLflow + SQLite** — experiment tracking y Model Registry
- **Prefect 3.x** — orquestación y scheduling
- **scikit-learn + pulearn** — modelos (LR, RF, BaggingPuClassifier)
- **GeoPandas / HydroBASINS nivel 10** — granularidad espacial por cuenca

## Metodología

- **Unidad de análisis:** cuenca hidrográfica × semana (~549 cuencas en Antioquia)
- **Target:** `deslizamiento = 1` si ocurrió al menos un evento UNGRD esa semana en esa cuenca
- **Features:** precipitación acumulada (3d, 7d, 14d) y días con lluvia de la **semana anterior** (shift anti-leakage), atributos estáticos de cuenca (SUB_AREA, UP_AREA, DIST_MAIN, ORDER), estacionalidad cíclica (semana, mes)
- **Entrenamiento:** grid con pseudo-ausencias (precip ≤ P25, area ≤ P25) para balancear clases
- **Evaluación primaria:** AUC sobre grid completo (todos los negativos no confirmados, horizonte 2021-2022)
- **Modelo ganador:** BaggingPuClassifier (AUC grid completo ≈ 0.67)
- **Criterio de Staging:** AUC ≥ 0.60 **Y** Precision ≥ 0.10 sobre grid completo

## Correr el pipeline

### Prerequisitos

```bash
# 1. Instalar dependencias
uv sync

# 2. Iniciar MLflow (en otra terminal)
uv run mlflow server --backend-store-uri sqlite:///mlruns/mlflow.db --port 5000

# 3. Iniciar servidor Prefect (en otra terminal)
uv run prefect server start

# 4. Crear work pool (solo la primera vez)
uv run prefect work-pool create --type process local-process

# 5. Configurar URL de la API Prefect
uv run prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api
```

### Solo ETL (regenerar grids)

```bash
uv run python scripts/build_grid_v3.py
```

### Solo entrenamiento (requiere grids previos)

```bash
uv run python -c "
from pipelines.training_flow import training_pipeline
resultado = training_pipeline()
print(f'Mejor modelo: {resultado[\"nombre\"]} AUC={resultado[\"auc_roc_full\"]:.3f}')
"
```

### Pipeline completo con Prefect (local)

```bash
# En una terminal: worker
uv run prefect worker start --pool local-process

# En otra terminal: registrar deployment (solo si no está registrado)
uv run python pipelines/deploy.py

# Disparar manualmente
uv run prefect deployment run "antioquia-full-pipeline/antioquia-weekly"
```

Verificar ejecuciones en: http://localhost:4200/flow-runs

### Scheduling automático

El deployment registrado corre cada lunes:
- **5:00 am** — `antioquia-weekly`: ETL (CHIRPS + UNGRD) → entrenamiento → evaluación en grid completo → registro en MLflow

Verificar deployment en: http://localhost:4200/deployments

## MLflow UI

```bash
uv run mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db
```

Experimento principal: `antioquia-deslizamientos-v3`

Navegar a: http://localhost:5000

## Notebooks de referencia

| Notebook | Descripción |
|---|---|
| `03_pipeline_v3_cuencas.ipynb` | Pipeline completo v3: HydroSHEDS + CHIRPS + PU-Learning |
| `04_hyperparameter_tuning.ipynb` | Tuning con RandomizedSearchCV y runs anidados en MLflow |
