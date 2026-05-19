"""
Carga y validación de configuración de experimentos.

Uso típico (en notebook o script):
    from experiment.config import load_config

    cfg = load_config()
    print(cfg.geo.departamento)            # "antioquia"
    print(cfg.target.class_weight)         # "balanced"
    print(cfg.all_features)               # lista completa según fuentes activas
    mlflow.log_params(cfg.as_mlflow_params())

Cambios v2.0.0:
    - TargetConfig simplificado: de multiclase a binario
    - Eliminados ClaseConfig, ClasesConfig, umbral_medio, umbral_alto
    - Agregados class_weight y descriptores de clase positiva/negativa
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, model_validator


# ---------------------------------------------------------------------------
# Modelos Pydantic — uno por sección del YAML
# ---------------------------------------------------------------------------


class GeoConfig(BaseModel):
    departamento: str

    @model_validator(mode="after")
    def normalize(self) -> "GeoConfig":
        self.departamento = self.departamento.strip().lower()
        return self


class PeriodoConfig(BaseModel):
    anio_inicio: int
    anio_fin: int

    @model_validator(mode="after")
    def check_range(self) -> "PeriodoConfig":
        if self.anio_inicio > self.anio_fin:
            raise ValueError(
                f"anio_inicio ({self.anio_inicio}) debe ser <= anio_fin ({self.anio_fin})"
            )
        return self


class VentanasConfig(BaseModel):
    precipitacion_dias: int = 14
    prediccion_dias: int = 7
    granularidad: str = "semanal"


class PseudoAbsenceConfig(BaseModel):
    precip_percentil: float = 0.25
    area_percentil: float = 0.25


class EspacialConfig(BaseModel):
    granularidad: str = "cuenca"
    hydrobasins_nivel: int = 5
    pseudo_absence: PseudoAbsenceConfig = PseudoAbsenceConfig()


class IdeamSourceConfig(BaseModel):
    dataset_id: str
    descripcion: str = ""
    limit_por_mes: int = 5_000


class UngrdSourceConfig(BaseModel):
    dataset_id: str
    descripcion: str = ""
    max_records: int = 30_000


class SiataSourceConfig(BaseModel):
    csv_path: str
    activo: bool = False
    descripcion: str = ""


class BboxConfig(BaseModel):
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float


class ChirpsSourceConfig(BaseModel):
    activo: bool = True
    descripcion: str = ""
    base_url: str = (
        "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/tifs/p05"
    )
    bbox: BboxConfig


class Era5BboxConfig(BaseModel):
    north: float
    west: float
    south: float
    east: float

    def as_list(self) -> list[float]:
        return [self.north, self.west, self.south, self.east]


class Era5SourceConfig(BaseModel):
    activo: bool = True
    descripcion: str = ""
    variables: list[str] = ["volumetric_soil_water_layer_2"]
    bbox: Era5BboxConfig


class FuentesConfig(BaseModel):
    ideam: IdeamSourceConfig
    ungrd: UngrdSourceConfig
    siata: SiataSourceConfig
    chirps: ChirpsSourceConfig
    era5: Era5SourceConfig


class EventosConfig(BaseModel):
    hidro_keywords: list[str]
    landslide_keywords: list[str]


class TargetConfig(BaseModel):
    """
    Configuración del target binario.

    - 0: no ocurrió ningún deslizamiento ese mes
    - 1: ocurrió al menos uno

    class_weight="balanced" delega el manejo del desbalance de clases
    a sklearn, que calcula los pesos proporcionalmente a la frecuencia
    inversa de cada clase en los datos de entrenamiento.
    """

    nombre: str = "deslizamiento"
    tipo: str = "binario"
    clase_positiva: int = 1
    clase_positiva_desc: str = ""
    clase_negativa: int = 0
    clase_negativa_desc: str = ""
    class_weight: str = "balanced"


class FeaturesConfig(BaseModel):
    base: list[str]
    hidrobasins: list[str] = []
    era5: list[str] = []
    seasonality: list[str]
    siata: list[str]
    required_for_model: list[str]


class CalidadConfig(BaseModel):
    cobertura_sensor_percentil: int = 25
    precip_min_mm: float = 0.0
    precip_max_mm: float = 500.0


class MLflowConfig(BaseModel):
    experiment_name: str
    db_path: str
    run_tags: dict[str, str] = {}


class DatosConfig(BaseModel):
    dataset_procesado: str


class PrefectConfig(BaseModel):
    work_pool: str = "local-process"
    flow_name: str = "antioquia-deslizamientos-training"
    schedule_cron: str = "0 6 * * 1"
    retries: int = 2
    retry_delay_seconds: int = 300


class LogisticRegressionConfig(BaseModel):
    C: float = 1.0
    solver: str = "lbfgs"


class RandomForestConfig(BaseModel):
    n_estimators: int = 100
    max_depth: int = 6
    min_samples_leaf: int = 1


class BaggingPuConfig(BaseModel):
    n_estimators: int = 15
    estimator_max_depth: int = 6


class ModelosConfig(BaseModel):
    logistic_regression: LogisticRegressionConfig = LogisticRegressionConfig()
    random_forest: RandomForestConfig = RandomForestConfig()
    bagging_pu: BaggingPuConfig = BaggingPuConfig()


# ---------------------------------------------------------------------------
# Modelo raíz
# ---------------------------------------------------------------------------


class ExperimentConfig(BaseModel):
    """Configuración completa del experimento, cargada desde YAML."""

    geo: GeoConfig
    periodo: PeriodoConfig
    fuentes: FuentesConfig
    datos: DatosConfig
    eventos: EventosConfig
    espacial: EspacialConfig = EspacialConfig()
    ventanas: VentanasConfig
    target: TargetConfig
    features: FeaturesConfig
    calidad: CalidadConfig
    mlflow: MLflowConfig
    prefect: PrefectConfig = PrefectConfig()
    modelos: ModelosConfig = ModelosConfig()

    _project_root: Optional[Path] = None

    # ------------------------------------------------------------------
    # Propiedades derivadas
    # ------------------------------------------------------------------

    @property
    def dataset_path(self) -> Path:
        return self.processed_dir / self.datos.dataset_procesado

    @property
    def project_root(self) -> Path:
        if self._project_root is None:
            raise RuntimeError("project_root no fue inyectado. Usa load_config().")
        return self._project_root

    @property
    def all_features(self) -> list[str]:
        """Lista completa de features activas según configuración de fuentes."""
        feats = (
            self.features.base + self.features.hidrobasins + self.features.seasonality
        )
        if self.fuentes.era5.activo:
            feats += self.features.era5
        if self.fuentes.siata.activo:
            feats += self.features.siata
        return feats

    @property
    def mlflow_tracking_uri(self) -> str:
        return f"sqlite:///{self.project_root / self.mlflow.db_path}"

    @property
    def siata_csv_path(self) -> Path:
        return self.project_root / self.fuentes.siata.csv_path

    @property
    def processed_dir(self) -> Path:
        return self.project_root / "data" / "processed"

    @property
    def raw_dir(self) -> Path:
        return self.project_root / "data" / "raw"

    # ------------------------------------------------------------------
    # Helpers para MLflow
    # ------------------------------------------------------------------

    def as_mlflow_params(self) -> dict[str, str]:
        """
        Devuelve un dict plano listo para mlflow.log_params().
        MLflow no acepta valores anidados ni listas — todo se convierte a str.
        """
        return {
            "geo.departamento": self.geo.departamento,
            "periodo.anio_inicio": str(self.periodo.anio_inicio),
            "periodo.anio_fin": str(self.periodo.anio_fin),
            "fuentes.ideam.dataset_id": self.fuentes.ideam.dataset_id,
            "fuentes.ungrd.dataset_id": self.fuentes.ungrd.dataset_id,
            "fuentes.siata.activo": str(self.fuentes.siata.activo),
            "fuentes.chirps.activo": str(self.fuentes.chirps.activo),
            "fuentes.era5.activo": str(self.fuentes.era5.activo),
            "target.tipo": self.target.tipo,
            "target.nombre": self.target.nombre,
            "target.class_weight": self.target.class_weight,
            "features.n_total": str(len(self.all_features)),
            "eventos.n_landslide_kw": str(len(self.eventos.landslide_keywords)),
            "ventanas.precipitacion_dias": str(self.ventanas.precipitacion_dias),
            "ventanas.prediccion_dias": str(self.ventanas.prediccion_dias),
            "ventanas.granularidad": self.ventanas.granularidad,
        }


# ---------------------------------------------------------------------------
# Función de carga pública
# ---------------------------------------------------------------------------


def _find_project_root(start: Path) -> Path:
    """Sube desde `start` hasta encontrar pyproject.toml."""
    for p in [start, *start.parents]:
        if (p / "pyproject.toml").exists():
            return p
    return start.parent


def load_config(
    config_path: Optional[str | Path] = None,
    project_root: Optional[Path] = None,
) -> ExperimentConfig:
    """
    Carga la configuración desde un archivo YAML y la valida con Pydantic.

    Parameters
    ----------
    config_path : str | Path | None
        Ruta al YAML. Si es None, busca por convención:
        {project_root}/configs/antioquia_deslizamientos.yaml
    project_root : Path | None
        Raíz del proyecto. Si es None, se resuelve subiendo desde el CWD
        hasta encontrar pyproject.toml.

    Returns
    -------
    ExperimentConfig
        Objeto tipado con todas las secciones del YAML y propiedades derivadas.

    Raises
    ------
    FileNotFoundError
        Si el archivo YAML no existe.
    pydantic.ValidationError
        Si el YAML tiene valores inválidos.
    """
    if project_root is None:
        project_root = _find_project_root(Path.cwd())

    if config_path is None:
        config_path = project_root / "configs" / "antioquia_deslizamientos.yaml"

    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Archivo de configuración no encontrado: {config_path}\n"
            f"Project root detectado: {project_root}"
        )

    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    cfg = ExperimentConfig(**raw)
    object.__setattr__(cfg, "_project_root", project_root)
    return cfg
