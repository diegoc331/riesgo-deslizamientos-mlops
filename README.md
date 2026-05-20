# Predicción de Deslizamientos — Antioquia, Colombia

![CI](https://github.com/diegoc331/riesgo-deslizamientos-mlops/actions/workflows/ci.yml/badge.svg)

**Estudiantes:** Diego Fernando Nuñez · Mateo Atehortua · Diego Fernando Castañeda  
**Curso:** Proyecto II — Universidad de Medellín

---

Sistema MLOps de predicción temprana de deslizamientos a granularidad de **cuenca hidrográfica** (HydroSHEDS nivel 10). Entrega alertas 7 días antes del evento a Unidades de Gestión de Riesgos (UNGRD/DAGRD), con un dashboard operacional para visualización y análisis.

**BCR = 2.11×** con factor de reducción de daños 40% (escenario conservador). Costo histórico evitable: $210 mil millones COP (2019-2022).

---

## Prerrequisitos

| Requisito | Versión mínima |
|---|---|
| Python | 3.11 |
| Node.js | 18+ |
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
                    Prefect Training (lunes 6am)
                    training_flow.py
                           │
                    MLflow Registry
                    BaggingPuClassifier / Staging
                    AUC-ROC real: 0.6088
                           │
                    Prefect Prediction (lunes 6:30am)
                    prediction_flow.py
                           │
                    predicciones_semana_actual.json
                    (549 cuencas con probabilidad ML)
                           │
                    FastAPI (puerto 8000)
                    POST /predict · /predict/batch
                    GET  /predicciones/semana-actual
                    GET  /geojson/cuencas · /impacto
                           │
                    Docker Compose
                    api + mlflow
                           │
                    Monitoring
                    KS test drift / JSONL logs
                           │
                    Dashboard UNGRD (puerto 3000)
                    React + Leaflet + Recharts
                    Mapa · Predicción · Impacto · Monitoring · Modelo
```

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Datos | CHIRPS v2.0 (UCSB), UNGRD (Socrata), ERA5-Land (ECMWF) |
| Espacio | GeoPandas + HydroSHEDS nivel 10 (549 cuencas Antioquia) |
| ML | scikit-learn + pulearn (BaggingPuClassifier) |
| Tracking | MLflow + SQLite |
| Orquestación | Prefect 3.x (ETL lunes 5am · training 6am · inferencia 6:30am) |
| Serving | FastAPI + Uvicorn |
| Containerización | Docker + docker-compose |
| Monitoreo | KS test drift, JSONL predictions log |
| Config | Pydantic v2 + YAML versionado en Git |
| CI/CD | GitHub Actions (ruff + pytest) |
| Frontend | React 18 + TypeScript + Vite + Leaflet + Recharts |

---

## Estructura del repositorio

```
configs/
    antioquia_deslizamientos.yaml   # single source of truth
data/
    raw/
        chirps_antioquia_daily.csv  # 1461 días 2019-2022
        ungrd_emergencias.csv       # 25k eventos
        spatial/
            hydrobasins_antioquia_lev10.gpkg   # 549 cuencas (fuente)
            cuencas_antioquia.geojson          # 549 cuencas (Leaflet)
    processed/
        grid_cuencas_v3.parquet     # 7.630 instancias (entrenamiento)
        grid_completo_v3.parquet    # 114.741 instancias (evaluación + inferencia)
        best_params.json            # hiperparámetros óptimos
        impacto_economico_por_cuenca.csv   # análisis BCR por cuenca
        predicciones_semana_actual.json    # output del prediction_flow
frontend/
    public/
        cuencas_antioquia.geojson   # GeoJSON estático (Leaflet)
        impacto.json                # impacto económico estático (fallback)
        predicciones_semana_actual.json    # predicciones ML estáticas (fallback)
    src/
        api/                        # hooks React Query (client, health, metadata, predict)
        components/
            layout/                 # Navbar
            map/                    # RiskMap (Leaflet coroplético)
            charts/                 # RiskGauge (Recharts)
            ui/                     # RiskBadge, KpiCard
        pages/
            MapaRiesgo.tsx          # mapa principal (homepage)
            Prediccion.tsx          # predicción individual
            ImpactoEconomico.tsx    # análisis económico + BCR slider
            Monitoring.tsx          # drift + log de predicciones
            Modelo.tsx              # metadatos del modelo
        types/index.ts              # tipos TS espejando schemas Pydantic
notebooks/                          # EDA, tracking, tuning, impacto económico
pipelines/
    data_flow.py                    # ETL Prefect
    training_flow.py                # Entrenamiento + evaluación + registry
    prediction_flow.py              # Inferencia semanal → JSON 549 cuencas
    deploy.py                       # Scheduling training (lunes 6am)
    deploy_prediction.py            # Scheduling predicción (lunes 6:30am)
scripts/
    build_grid_v3.py                # Standalone: regenera grids
    convert_gpkg_to_geojson.py      # GeoPackage → GeoJSON para Leaflet
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
        main.py                     # FastAPI app (lifespan + CORS)
        routes.py                   # 10 endpoints REST
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

## Inicio rápido

### Con Docker (backend + MLflow)

```bash
# 1. Clonar
git clone <repo> && cd riesgo-deslizamientos-mlops

# 2. Levantar servicios
docker compose up -d

# 3. Verificar salud
curl http://localhost:8000/health

# 4. MLflow UI
open http://localhost:5001

# 5. Documentación interactiva API
open http://localhost:8000/docs
```

### Dashboard frontend

```bash
# Generar GeoJSON y predicciones (solo la primera vez)
uv run python scripts/convert_gpkg_to_geojson.py
uv run python pipelines/prediction_flow.py

# Instalar dependencias frontend
cd frontend && npm install

# Iniciar dashboard
npm run dev
# → http://localhost:3000
```

### Pipeline completo (sin Docker)

```bash
# Instalar dependencias
uv sync

# Generar datasets
uv run python scripts/build_grid_v3.py

# Entrenar modelo
uv run python pipelines/training_flow.py

# Generar predicciones semanales
uv run python pipelines/prediction_flow.py

# Levantar API
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
| GET | `/geojson/cuencas` | GeoJSON de las 549 cuencas HydroSHEDS (Leaflet) |
| GET | `/impacto` | Impacto económico histórico por cuenca UNGRD 2019-2022 |
| GET | `/predicciones/semana-actual` | Predicciones ML del pipeline semanal (549 cuencas) |
| POST | `/predict` | Predicción para una cuenca |
| POST | `/predict/batch` | Mapa de riesgo (hasta 549 cuencas) |

Documentación interactiva: `http://localhost:8000/docs`

---

## Dashboard — Vistas

| Vista | URL | Descripción |
|---|---|---|
| Mapa de Riesgo | `/` | Mapa coroplético Leaflet con 549 cuencas coloreadas por predicción ML semanal. Click en cuenca → detalle + navegación a predicción. |
| Predicción | `/prediccion/:id?` | Formulario de 14 features → gauge circular de probabilidad + badge de nivel. Se puede navegar desde el mapa. |
| Impacto Económico | `/impacto` | Bar chart top 20 cuencas por costo histórico, scatter eventos vs costo, slider interactivo de BCR (40%–90%). |
| Monitoring | `/monitoring` | Estado del sistema, tabla de drift KS por feature, log de predicciones recientes. |
| Modelo | `/modelo` | Metadatos live desde MLflow: versión, 15 features agrupadas, métricas de rendimiento, umbrales. |

---

## Metodología

- **Unidad de análisis:** cuenca hidrográfica × semana (549 cuencas en Antioquia)
- **Target:** `deslizamiento = 1` si ocurre al menos un evento UNGRD en los próximos 7 días
- **Features:** precipitación acumulada con `.shift(1)` anti-leakage + atributos estáticos HydroSHEDS + estacionalidad cíclica
- **PU-Learning:** los negativos son pseudo-ausencias (no ausencias confirmadas); `BaggingPuClassifier` maneja este sesgo
- **Evaluación honesta:** AUC-ROC en grid completo (114.741 instancias, holdout 2021-2022) = **0.6088**
  - _El AUC de 0.993 en pseudo-ausencias es artificialmente alto (leakage de diseño)_
- **Criterio de Staging:** AUC ≥ 0.60 AND Precision ≥ 0.006 sobre grid completo (1.5× tasa base de eventos 0.4%)
- **Interpretación del mapa:** el modelo tiene recall=0.80 / precision=0.15. En semanas de alta precipitación muchas cuencas aparecen en rojo — usar en conjunto con el índice de impacto económico para priorización operacional.

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
**Solución:** Reentrenar el modelo:
```bash
uv run python pipelines/training_flow.py
```

### `FutureWarning` en MLflow — `get_latest_versions` con stages

**Síntoma:** `FutureWarning: stages param is deprecated`  
**Impacto:** Solo warning — no bloquea el funcionamiento.

### API arranca en modo degradado (`status: degradado`)

**Síntoma:** `GET /health` devuelve `"status": "degradado"` y `/predict` responde 503.

**Solución:**
```bash
# Entrenar y registrar el modelo
uv run python pipelines/training_flow.py

# Reiniciar la API
docker compose restart api
```

### Mapa con demasiadas cuencas en rojo

**Causa:** El modelo tiene precision=0.15 y recall=0.80. En semanas con precipitación extrema (ej. diciembre 2022, peor año del dataset), la mayoría de cuencas supera el umbral de Alto (≥0.60). Es técnicamente correcto dado el diseño PU-Learning.

**Uso operacional recomendado:** Ordenar las cuencas de Alto riesgo por `indice_riesgo` histórico (impacto económico × eventos pasados) para priorizar la respuesta.
