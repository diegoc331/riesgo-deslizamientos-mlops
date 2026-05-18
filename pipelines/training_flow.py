"""
Prefect flow de entrenamiento: carga el grid, evalua modelos con CV de panel,
selecciona el mejor, evalua en grid completo y registra en MLflow Model Registry.

Exporta:
  training_pipeline — flow completo que retorna el dict del mejor modelo
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

import mlflow
import mlflow.sklearn
import pandas as pd
from prefect import flow, task, get_run_logger
from sklearn.base import clone

from experiment.config import ExperimentConfig, load_config
from experiment.evaluate import evaluar_con_panel_cv, evaluar_en_grid_completo
from experiment.registry import register_best_model, transition_stage
from experiment.train import get_experimentos, make_pipeline

# Años usados como holdout para la decisión de Staging
# (últimos 2 años del período configurado)
_HOLDOUT_ANIOS = 2


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@task(name="cargar-dataset-entrenamiento")
def task_cargar_dataset(grid_pa_path: str, cfg: ExperimentConfig):
    logger = get_run_logger()
    df = pd.read_parquet(grid_pa_path)
    df["anio_semana"] = pd.PeriodIndex(df["anio_semana"], freq="W")
    df = df.sort_values("anio_semana").reset_index(drop=True)

    feature_cols = [f for f in cfg.all_features if f in df.columns]
    X = df[feature_cols]
    y = df[cfg.target.nombre]

    logger.info(
        f"Dataset PA cargado: {df.shape} | "
        f"pos={int(y.sum())} ({y.mean():.2%}) | "
        f"features={len(feature_cols)}"
    )
    return X, y, df, feature_cols


@task(name="entrenar-modelo")
def task_entrenar_modelo(
    nombre: str,
    clf,
    X: pd.DataFrame,
    y: pd.Series,
    df_ref: pd.DataFrame,
    cfg: ExperimentConfig,
) -> dict:
    logger = get_run_logger()

    pipeline = make_pipeline(clone(clf))

    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
    mlflow.set_experiment(cfg.mlflow.experiment_name)

    run_tags = {**cfg.mlflow.run_tags, "modelo": nombre, "fase": "entrenamiento_cv"}

    with mlflow.start_run(run_name=nombre, tags=run_tags) as run:
        # CV de panel sobre pseudo-ausencias
        metricas_cv = evaluar_con_panel_cv(pipeline, X, y, df_ref, n_splits=4)
        mlflow.log_metrics(metricas_cv)

        # Parámetros del clasificador (serializables)
        try:
            clf_params = {
                k: (v if not hasattr(v, "__len__") or isinstance(v, str) else str(v))
                for k, v in clf.get_params().items()
            }
            mlflow.log_params(clf_params)
        except Exception:
            pass

        # Re-ajustar en todos los datos de train y loguear artefacto
        pipeline.fit(X, y)
        mlflow.sklearn.log_model(pipeline, name="model")
        run_id = run.info.run_id

    logger.info(
        f"{nombre}: AUC_CV={metricas_cv['auc_roc_mean']:.4f} "
        f"Recall_CV={metricas_cv['recall_mean']:.4f}"
    )
    return {
        "nombre":       nombre,
        "pipeline":     pipeline,
        "run_id":       run_id,
        **metricas_cv,
    }


@task(name="evaluar-grid-completo")
def task_evaluar_grid_completo(
    resultado: dict,
    grid_full_path: str,
    feature_cols: list[str],
    cfg: ExperimentConfig,
) -> dict:
    logger = get_run_logger()

    anio_eval_ini = cfg.periodo.anio_fin - _HOLDOUT_ANIOS + 1
    anio_eval_fin = cfg.periodo.anio_fin

    metricas_full = evaluar_en_grid_completo(
        resultado["pipeline"],
        grid_full_path,
        feature_cols=feature_cols,
        anio_inicio=anio_eval_ini,
        anio_fin=anio_eval_fin,
    )

    # Agregar métricas del grid completo al run de MLflow existente
    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
    with mlflow.start_run(run_id=resultado["run_id"]):
        mlflow.log_metrics(metricas_full)
        mlflow.log_param("eval_tipo", "grid_completo_holdout")
        mlflow.log_param("eval_periodo", f"{anio_eval_ini}-{anio_eval_fin}")

    logger.info(
        f"{resultado['nombre']} en grid completo "
        f"{anio_eval_ini}-{anio_eval_fin}: "
        f"AUC={metricas_full['auc_roc_full']:.4f} "
        f"Prec={metricas_full['precision_full']:.4f} "
        f"Recall={metricas_full['recall_full']:.4f} "
        f"(n={metricas_full['n_total_full']:,} pos={metricas_full['n_positivos_full']})"
    )
    return metricas_full


@task(name="registrar-mejor-modelo")
def task_registrar_modelo(cfg: ExperimentConfig, resultado: dict) -> tuple[str, str]:
    logger = get_run_logger()

    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
    model_name = register_best_model(cfg, resultado, version_tag="v3")

    # Obtener versión recién creada
    client = mlflow.tracking.MlflowClient(tracking_uri=cfg.mlflow_tracking_uri)
    versiones = client.search_model_versions(f"name='{model_name}'")
    version = str(max(int(v.version) for v in versiones))

    logger.info(f"Modelo registrado: {model_name} v{version}")
    return model_name, version


@task(name="transition-staging")
def task_transition_staging(
    cfg: ExperimentConfig,
    model_name: str,
    version: str,
    umbral_auc: float = 0.60,
    umbral_precision: float = 0.10,
) -> bool:
    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
    promovido = transition_stage(
        cfg, model_name, version,
        umbral_auc=umbral_auc,
        umbral_precision=umbral_precision,
    )
    return promovido


# ---------------------------------------------------------------------------
# Flow principal
# ---------------------------------------------------------------------------

@flow(name="antioquia-training-pipeline", log_prints=True)
def training_pipeline(
    grid_pa_path: str | None = None,
    grid_full_path: str | None = None,
    config_path: str | None = None,
    umbral_auc: float = 0.60,
    umbral_precision: float = 0.10,
) -> dict:
    """
    Entrena todos los modelos configurados, evalua cada uno en el grid completo
    (holdout temporal), selecciona el mejor por AUC en grid completo y registra
    en MLflow Model Registry.

    El modelo se promueve a Staging si cumple AMBAS condiciones:
      - AUC en grid completo >= umbral_auc
      - Precision en grid completo >= umbral_precision

    Parameters
    ----------
    grid_pa_path      : ruta a grid_cuencas_v3.parquet (pseudo-ausencias)
    grid_full_path    : ruta a grid_completo_v3.parquet (evaluacion honesta)
    config_path       : ruta al YAML de configuracion (None = auto-detectar)
    umbral_auc        : AUC minimo sobre grid completo para Staging
    umbral_precision  : Precision minima sobre grid completo para Staging

    Returns
    -------
    dict con el resultado del mejor modelo (metricas CV + full grid + run_id)
    """
    cfg = load_config(config_path, project_root=_PROJECT_ROOT)

    processed_dir = _PROJECT_ROOT / "data" / "processed"
    if grid_pa_path is None:
        grid_pa_path   = str(processed_dir / "grid_cuencas_v3.parquet")
    if grid_full_path is None:
        grid_full_path = str(processed_dir / "grid_completo_v3.parquet")

    # 1. Cargar datos
    X, y, df_ref, feature_cols = task_cargar_dataset(grid_pa_path, cfg)
    n_positivos = int(y.sum())

    # 2. Entrenar (CV + fit completo) y evaluar en grid completo todos los modelos
    #    El CV sobre PA sirve para diagnostico; la seleccion usa auc_roc_full.
    experimentos = get_experimentos(cfg, n_positivos)
    resultados = []
    for nombre, clf in experimentos.items():
        res = task_entrenar_modelo(nombre, clf, X, y, df_ref, cfg)
        if nombre != "baseline_dummy":
            metricas_full = task_evaluar_grid_completo(
                res, grid_full_path, feature_cols, cfg
            )
            res.update(metricas_full)
        resultados.append(res)

    # 3. Seleccionar mejor modelo por AUC en grid completo (criterio primario)
    candidatos = [r for r in resultados if r["nombre"] != "baseline_dummy"]
    mejor = max(candidatos, key=lambda r: r["auc_roc_full"])

    # 4. Registrar en Model Registry
    model_name, version = task_registrar_modelo(cfg, mejor)

    # 5. Transicion a Staging si cumple ambos umbrales
    task_transition_staging(cfg, model_name, version, umbral_auc, umbral_precision)

    return mejor
