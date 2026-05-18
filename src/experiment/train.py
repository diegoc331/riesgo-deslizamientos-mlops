"""
Definición de pipelines y experimentos para clasificación de deslizamientos.

Exporta:
  make_pipeline      — construye un Pipeline sklearn con imputación + escalado + clf
  get_experimentos   — retorna el diccionario de clasificadores configurados desde YAML
"""

from __future__ import annotations

from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    from pulearn import BaggingPuClassifier
    _PULEARN_AVAILABLE = True
except ImportError:
    _PULEARN_AVAILABLE = False


def make_pipeline(classifier) -> Pipeline:
    """
    Pipeline con imputación + escalado + clasificador.
    Imputación y escalado se ajustan solo con datos de train (sin leakage).
    """
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler",  StandardScaler()),
        ("clf",     classifier),
    ])


def get_experimentos(cfg, n_positivos: int) -> dict:
    """
    Retorna el diccionario de clasificadores configurados desde el YAML.

    Lee hiperparámetros desde `cfg.modelos` (sección `modelos:` en el YAML),
    que contiene los valores óptimos encontrados en el notebook 04 de tuning.

    Parameters
    ----------
    cfg : ExperimentConfig — fuente única de verdad para class_weight e hiperparámetros
    n_positivos : número de positivos en el dataset de train;
                  BaggingPuClassifier lo usa como max_samples para balancear bootstraps

    Returns
    -------
    dict[str, estimador sklearn] — cada valor es un clasificador listo para
    ser envuelto en make_pipeline() y ajustado con .fit()
    """
    class_weight = cfg.target.class_weight
    m = cfg.modelos

    experimentos = {
        "baseline_dummy": DummyClassifier(
            strategy="stratified",
            random_state=42,
        ),
        "logistic_regression": LogisticRegression(
            C=m.logistic_regression.C,
            solver=m.logistic_regression.solver,
            class_weight=class_weight,
            max_iter=500,
            random_state=42,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=m.random_forest.n_estimators,
            max_depth=m.random_forest.max_depth,
            min_samples_leaf=m.random_forest.min_samples_leaf,
            class_weight=class_weight,
            random_state=42,
            n_jobs=-1,
        ),
    }

    if _PULEARN_AVAILABLE:
        experimentos["bagging_pu"] = BaggingPuClassifier(
            estimator=RandomForestClassifier(
                max_depth=m.bagging_pu.estimator_max_depth,
                random_state=42,
            ),
            n_estimators=m.bagging_pu.n_estimators,
            max_samples=n_positivos,
            n_jobs=-1,
            random_state=42,
        )
    else:
        import warnings
        warnings.warn(
            "pulearn no está instalado — bagging_pu omitido. "
            "Instala con: uv add pulearn",
            ImportWarning,
            stacklevel=2,
        )

    return experimentos
