# Predicción de Deslizamientos — Antioquia, Colombia

![CI](https://github.com/diegoc331/riesgo-deslizamientos-mlops/actions/workflows/ci.yml/badge.svg)

**Estudiantes:** Diego Fernando Nuñez · Mateo Atehortua · Diego Fernando Castañeda  
**Curso:** Proyecto II — Universidad de Medellín

---

Sistema MLOps de predicción temprana de deslizamientos a granularidad de **cuenca hidrográfica** (HydroSHEDS nivel 10). Entrega alertas 7 días antes del evento a Unidades de Gestión de Riesgos (UNGRD/DAGRD).

**BCR = 2.11×** con factor de reducción de daños 40% (escenario conservador). Costo histórico evitable: $210 mil millones COP (2019-2022).

---

## Prerrequisitos

| Requisito | Versión mínima |
|---|---|
| Python | 3.11 |
| uv | 0.4+ |
| Docker + docker-compose | 24+ |
| Modelo entrenado | `mlruns/` con versión en Staging (`uv run python pipelines/training_flow.py`) |

---

## Flujo MLOps completo

```
CHIRPS v2.0          UNGRD Socrata       HydroSHEDS
(precipitación)      (emergencias)       (549 cuencas)
       │                   │                   │
       └───────────────────┴───────────────────┘
                           │
                    Prefect ETL (lunes 5am)
                    data_flow.py
                           │
                    data/processed/
                    grid_cuencas_v3.parquet   (7.630 instancias)
                    grid_completo_v3.parquet  (114.741 instancias)
                           │
                    Prefect Training
                    training_flow.py
                           │
                    MLflow Registry
                    BaggingPuClassifier
                    AUC-ROC real: 0.6088
                           │
                    FastAPI (puerto 8000)
                    POST /predict
                    POST /predict/batch
                           │
                    Docker Compose
                    api + mlflow
                           │
                    Monitoring
                    KS test drift / JSONL logs
```

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Datos | CHIRPS v2.0 (UCSB), UNGRD (Socrata), ERA5-Land (ECMWF) |
| Espacio | GeoPandas + HydroSHEDS nivel 10 (549 cuencas Antioquia) |
| ML | scikit-learn + pulearn (BaggingPuClassifier) |
| Tracking | MLflow + SQLite |
| Orquestación | Prefect 3.x (scheduling lunes 5am) |
| Serving | FastAPI + Uvicorn |
| Containerización | Docker + docker-compose |
| Monitoreo | KS test drift, JSONL predictions log |
| Config | Pydantic v2 + YAML versionado en Git |
| CI/CD | GitHub Actions (ruff + pytest) |

---

## Estructura del repositorio

```
configs/
    antioquia_deslizamientos.yaml   # single source of truth
data/
    raw/                            # CHIRPS CSV, UNGRD CSV, spatial/*.gpkg
    processed/
        grid_cuencas_v3.parquet     # 7.630 instancias (entrenamiento)
        grid_completo_v3.parquet    # 114.741 instancias (evaluación honesta)
        best_params.json            # hiperparámetros óptimos
notebooks/                          # EDA, tracking, tuning, impacto económico
pipelines/
    data_flow.py                    # ETL Prefect
    training_flow.py                # Entrenamiento + evaluación + registry
    deploy.py                       # Scheduling semanal
scripts/
    build_grid_v3.py                # Standalone: regenera grids
    diagnostico_auc.py              # Valida AUC real vs pseudo-ausencias
src/experiment/
    config.py                       # ExperimentConfig (Pydantic v2)
    download.py                     # CHIRPS, UNGRD, ERA5
    process.py                      # Rolling windows + shift(1) anti-leakage
    spatial.py                      # HydroSHEDS, geocodificación, pseudo-ausencias
    train.py                        # make_pipeline(), get_experimentos()
    evaluate.py                     # panel_time_splits(), evaluación honesta
    registry.py                     # MLflow Model Registry
    api/
        main.py                     # FastAPI app (lifespan)
        routes.py                   # GET /health, /metadata · POST /predict, /predict/batch
        schemas.py                  # Pydantic: PredictRequest, PredictResponse
        dependencies.py             # Carga modelo desde MLflow Registry
    monitoring/
        logger.py                   # log_prediction() → logs/predictions.jsonl
        drift.py                    # save_reference(), detect_drift() (KS test)
tests/
    unit/
        test_process.py             # Anti-leakage shift(1)
        test_evaluate.py            # Panel splits disjuntos
        test_api.py                 # Endpoints FastAPI
.github/workflows/ci.yml            # ruff + pytest en GitHub Actions
Dockerfile                          # python:3.11-slim, usuario no-root
docker-compose.yml                  # api (8000) + mlflow (5001)
```

---

## Inicio rápido con Docker

```bash
# 1. Clonar y entrar al directorio
git clone <repo> && cd riesgo-deslizamientos-mlops

# 2. Levantar servicios (requiere modelo entrenado en mlruns/)
docker compose up -d

# 3. Verificar salud
curl http://localhost:8000/health

# 4. Predecir una cuenca
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
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
    "mes_cos": 0.50
  }'

# 5. MLflow UI
open http://localhost:5001

# 6. Documentación interactiva API
open http://localhost:8000/docs
```

---

## Correr el pipeline completo (sin Docker)

```bash
# Instalar dependencias
uv sync

# Generar datasets (requiere datos raw)
uv run python scripts/build_grid_v3.py

# Entrenar y registrar modelo
uv run python pipelines/training_flow.py

# Levantar API en desarrollo
uv run uvicorn experiment.api.main:app --reload --port 8000

# MLflow UI
uv run mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db --port 5001
```

---

## Tests

```bash
uv sync --group dev
uv run pytest tests/unit/ -q
```

---

## Endpoints de la API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/` | Info del servicio |
| GET | `/health` | Estado del modelo + versión |
| GET | `/health/live` | Liveness probe (Docker) |
| GET | `/health/ready` | Readiness probe (Docker) |
| GET | `/metadata` | Metadatos del modelo en producción |
| POST | `/predict` | Predicción para una cuenca |
| POST | `/predict/batch` | Mapa de riesgo (hasta 549 cuencas) |

Documentación interactiva: `http://localhost:8000/docs`

---

## Metodología

- **Unidad de análisis:** cuenca hidrográfica × semana (549 cuencas en Antioquia)
- **Target:** `deslizamiento = 1` si ocurre al menos un evento UNGRD en los próximos 7 días
- **Features:** precipitación acumulada con `.shift(1)` anti-leakage + atributos estáticos HydroSHEDS + estacionalidad cíclica
- **PU-Learning:** los negativos son pseudo-ausencias (no ausencias confirmadas); `BaggingPuClassifier` maneja este sesgo
- **Evaluación honesta:** AUC-ROC en grid completo (114.741 instancias, holdout 2021-2022) = **0.6088**
  - _El AUC de 0.993 en pseudo-ausencias es artificialmente alto (leakage de diseño)_
- **Criterio de Staging:** AUC ≥ 0.60 AND Precision ≥ 0.006 sobre grid completo (1.5× tasa base de eventos 0.4%)

---

## Notebooks de referencia

| Notebook | Descripción |
|---|---|
| `00_experimento_correlacion.ipynb` | EDA: correlación precipitación vs UNGRD |
| `03_pipeline_v3_cuencas.ipynb` | Pipeline v3: HydroSHEDS + CHIRPS + PU-Learning |
| `04_hyperparameter_tuning.ipynb` | Tuning con runs anidados en MLflow |
| `05_impacto_economico.ipynb` | BCR=2.11×, análisis económico UNGRD |

---

## Errores conocidos

### `POST /predict` — feature mismatch con modelo antiguo

**Síntoma:**
```
422 / 500 — "Feature names unseen at fit time: ORDER, soil_moisture_14d"
```

**Causa:** El modelo en MLflow Registry (v1, Staging) fue entrenado con 12 features por un notebook anterior. La configuración actual (`cfg.all_features`) define 14 features — agrega `ORDER` y `soil_moisture_14d`.

**Solución:** Reentrenar el modelo con el pipeline actualizado:
```bash
uv run python pipelines/training_flow.py
```
Esto registra una nueva versión con las 14 features y la API la carga automáticamente en el siguiente arranque.

---

### `FutureWarning` en MLflow — `get_latest_versions` con stages

**Síntoma:**
```
FutureWarning: ``stages`` param is deprecated ... use ``filter_string`` instead
```

**Causa:** MLflow ≥ 2.9 depreca el parámetro `stages` en `get_latest_versions()`.  
**Impacto:** Solo es un warning — no bloquea el funcionamiento. Se resolverá al migrar a `MlflowClient.search_model_versions()`.

---

### API arranca en modo degradado (`status: degradado`)

**Síntoma:** `GET /health` devuelve `"status": "degradado"` y `/predict` responde 503.

**Causa:** No hay ningún modelo registrado en MLflow Registry con stage `Staging` o `None`.

**Solución:**
```bash
# 1. Asegurarse de que MLflow esté corriendo
docker compose up mlflow -d    # o uv run mlflow ui --port 5001

# 2. Entrenar y registrar el modelo
uv run python pipelines/training_flow.py

# 3. Reiniciar la API para que recargue el modelo
docker compose restart api
```
