"""
Gestión del ciclo de vida de modelos en MLflow Model Registry.

Exporta:
  register_best_model  — registra un run en el Model Registry con tags de trazabilidad
  transition_stage     — promueve a Staging si AUC supera el umbral mínimo
"""

from __future__ import annotations

import mlflow
from mlflow.tracking import MlflowClient

from experiment.config import ExperimentConfig


def register_best_model(
    cfg: ExperimentConfig,
    resultado: dict,
    version_tag: str = "v3",
) -> str:
    """
    Registra el mejor run en el MLflow Model Registry.

    Parameters
    ----------
    cfg        : configuración del experimento (fuente de nombres y periodo)
    resultado  : dict con claves 'run_id', 'nombre', 'auc_roc_mean', 'recall_mean'
                 (output de evaluar_con_panel_cv + run_id del run de MLflow)
    version_tag: etiqueta de versión del dataset/pipeline (ej. "v3")

    Returns
    -------
    str — nombre del modelo registrado en el Registry
    """
    client = MlflowClient(tracking_uri=cfg.mlflow_tracking_uri)
    model_name = f"{cfg.geo.departamento}_deslizamiento_{version_tag}_cuenca"

    run_id    = resultado["run_id"]
    model_uri = f"runs:/{run_id}/model"

    reg = mlflow.register_model(model_uri=model_uri, name=model_name)

    tags = {
        "algoritmo":         resultado.get("nombre", "desconocido"),
        "auc_roc_cv":        f"{resultado.get('auc_roc_mean', 0):.4f}",
        "recall_cv":         f"{resultado.get('recall_mean', 0):.4f}",
        # Métricas sobre grid completo (evaluación primaria)
        "auc_roc_full":      f"{resultado.get('auc_roc_full', 0):.4f}",
        "precision_full":    f"{resultado.get('precision_full', 0):.4f}",
        "recall_full":       f"{resultado.get('recall_full', 0):.4f}",
        "dataset_version":   version_tag,
        "granularidad":      cfg.espacial.granularidad,
        "hydrobasins_nivel": str(cfg.espacial.hydrobasins_nivel),
        "entrenado_con":     (
            f"{cfg.geo.departamento} "
            f"{cfg.periodo.anio_inicio}-{cfg.periodo.anio_fin}"
        ),
    }
    for key, value in tags.items():
        client.set_model_version_tag(
            name=model_name, version=reg.version, key=key, value=value
        )

    print(
        f"Modelo registrado: {model_name} v{reg.version}\n"
        f"  Algoritmo : {tags['algoritmo']}\n"
        f"  AUC-ROC   : {tags['auc_roc_cv']}\n"
        f"  Recall    : {tags['recall_cv']}"
    )
    return model_name


def transition_stage(
    cfg: ExperimentConfig,
    model_name: str,
    version: str,
    umbral_auc: float = 0.60,
    umbral_precision: float = 0.10,
) -> bool:
    """
    Promueve la versión del modelo a Staging si cumple AMBAS condiciones:
      - AUC-ROC (grid completo) >= umbral_auc
      - Precision (grid completo) >= umbral_precision

    Lee las métricas de los tags que register_best_model escribió en el Registry.

    Parameters
    ----------
    cfg               : configuración del experimento
    model_name        : nombre del modelo en el Registry
    version           : versión a promover (str, ej. "1")
    umbral_auc        : AUC mínimo sobre grid completo (default 0.60)
    umbral_precision  : Precision mínima sobre grid completo (default 0.10)

    Returns
    -------
    bool — True si fue promovido, False si no alcanzó ambos umbrales
    """
    client = MlflowClient(tracking_uri=cfg.mlflow_tracking_uri)

    mv            = client.get_model_version(name=model_name, version=version)
    auc_full      = float(mv.tags.get("auc_roc_full", "0"))
    precision_full = float(mv.tags.get("precision_full", "0"))

    cumple_auc       = auc_full      >= umbral_auc
    cumple_precision = precision_full >= umbral_precision

    if cumple_auc and cumple_precision:
        client.transition_model_version_stage(
            name=model_name,
            version=version,
            stage="Staging",
            archive_existing_versions=False,
        )
        print(
            f"Version {version} de '{model_name}' PROMOVIDA a Staging\n"
            f"  AUC grid completo : {auc_full:.4f} >= {umbral_auc}\n"
            f"  Precision full    : {precision_full:.4f} >= {umbral_precision}"
        )
        return True

    razon = []
    if not cumple_auc:
        razon.append(f"AUC {auc_full:.4f} < {umbral_auc}")
    if not cumple_precision:
        razon.append(f"Precision {precision_full:.4f} < {umbral_precision}")

    print(
        f"Version {version} de '{model_name}' NO promovida\n"
        f"  Razon: {' | '.join(razon)}"
    )
    return False
