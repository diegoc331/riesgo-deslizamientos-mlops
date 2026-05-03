"""
Carga y validación de configuración de experimentos.

Uso típico (en notebook o script):
    from experiment.config import load_config

    cfg = load_config()                          # busca el YAML por convención
    cfg = load_config("configs/otro.yaml")       # ruta explícita

    print(cfg.geo.departamento)                  # "antioquia"
    print(cfg.target.umbral_alto)                # 3
    print(cfg.all_features)                      # lista completa según fuentes activas
    mlflow.log_params(cfg.as_mlflow_params())    # dict plano listo para MLflow
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Modelos Pydantic — uno por sección del YAML
# ---------------------------------------------------------------------------

class GeoConfig(BaseModel):
    departamento: str

    @model_validator(mode="after")
    def normalize(self) -> "GeoConfig":
        """Garantiza minúsculas sin espacios extra."""
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


class FuentesConfig(BaseModel):
    ideam: IdeamSourceConfig
    ungrd: UngrdSourceConfig
    siata: SiataSourceConfig


class EventosConfig(BaseModel):
    hidro_keywords: list[str]
    landslide_keywords: list[str]


class ClaseConfig(BaseModel):
    id: int
    descripcion: str
    condicion: str


class ClasesConfig(BaseModel):
    bajo: ClaseConfig
    medio: ClaseConfig
    alto: ClaseConfig


class TargetConfig(BaseModel):
    nombre: str = "riesgo"
    clases: ClasesConfig
    umbral_medio: int = Field(ge=1)
    umbral_alto: int = Field(ge=2)

    @model_validator(mode="after")
    def check_umbrales(self) -> "TargetConfig":
        if self.umbral_medio >= self.umbral_alto:
            raise ValueError(
                f"umbral_medio ({self.umbral_medio}) debe ser < umbral_alto ({self.umbral_alto})"
            )
        return self


class FeaturesConfig(BaseModel):
    base: list[str]
    lagged: list[str]
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


# ---------------------------------------------------------------------------
# Modelo raíz
# ---------------------------------------------------------------------------

class ExperimentConfig(BaseModel):
    """Configuración completa del experimento, cargada desde YAML."""

    geo: GeoConfig
    periodo: PeriodoConfig
    fuentes: FuentesConfig
    eventos: EventosConfig
    target: TargetConfig
    features: FeaturesConfig
    calidad: CalidadConfig
    mlflow: MLflowConfig

    # El project_root se inyecta en load_config(), no viene del YAML
    _project_root: Optional[Path] = None

    # ------------------------------------------------------------------
    # Propiedades derivadas (evitan lógica duplicada en notebooks)
    # ------------------------------------------------------------------

    @property
    def project_root(self) -> Path:
        if self._project_root is None:
            raise RuntimeError("project_root no fue inyectado. Usa load_config().")
        return self._project_root

    @property
    def all_features(self) -> list[str]:
        """Lista completa de features activas según configuración de fuentes."""
        feats = (
            self.features.base
            + self.features.lagged
            + self.features.seasonality
        )
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
        Devuelve un dict plano con todos los parámetros relevantes
        para registrar en mlflow.log_params().

        MLflow requiere valores str o numéricos simples, sin anidamiento.
        """
        return {
            # Alcance
            "geo.departamento":        self.geo.departamento,
            "periodo.anio_inicio":     str(self.periodo.anio_inicio),
            "periodo.anio_fin":        str(self.periodo.anio_fin),
            # Fuentes
            "fuentes.ideam.dataset_id":   self.fuentes.ideam.dataset_id,
            "fuentes.ungrd.dataset_id":   self.fuentes.ungrd.dataset_id,
            "fuentes.siata.activo":       str(self.fuentes.siata.activo),
            # Target
            "target.umbral_medio":     str(self.target.umbral_medio),
            "target.umbral_alto":      str(self.target.umbral_alto),
            # Features
            "features.n_total":        str(len(self.all_features)),
            "features.siata_activo":   str(self.fuentes.siata.activo),
            # Keywords
            "eventos.n_landslide_kw":  str(len(self.eventos.landslide_keywords)),
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
    config_path:
        Ruta al YAML. Si es None, busca por convención:
        `{project_root}/configs/antioquia_deslizamientos.yaml`
    project_root:
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
    ValidationError
        Si el YAML tiene valores inválidos (Pydantic).
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
    # Inyectar project_root (no viene del YAML, es runtime)
    object.__setattr__(cfg, "_project_root", project_root)

    return cfg