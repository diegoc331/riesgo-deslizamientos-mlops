"""
Esquemas Pydantic para la API de predicción de deslizamientos.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """Features de una cuenca para una semana dada."""

    hybas_id: int = Field(
        ..., description="Identificador de la cuenca HydroSHEDS nivel 10"
    )

    # Precipitación CHIRPS (rolling con shift(1) — sin leakage)
    precip_acum_14d: float = Field(
        ..., ge=0, description="Precipitación acumulada 14 días (mm)"
    )
    precip_acum_7d: float = Field(
        ..., ge=0, description="Precipitación acumulada 7 días (mm)"
    )
    precip_acum_3d: float = Field(
        ..., ge=0, description="Precipitación acumulada 3 días (mm)"
    )
    precip_max_diario_14d: float = Field(
        ..., ge=0, description="Máximo diario en ventana 14d (mm/día)"
    )
    precip_dias_lluvia_14d: float = Field(
        ..., ge=0, description="Días con precipitación > 0 en ventana 14d"
    )

    # Atributos estáticos HydroSHEDS
    SUB_AREA: float = Field(..., gt=0, description="Área sub-cuenca (km²)")
    UP_AREA: float = Field(
        ..., gt=0, description="Área drenaje acumulada aguas arriba (km²)"
    )
    DIST_MAIN: float = Field(..., ge=0, description="Distancia al cauce principal (km)")
    ORDER: int = Field(..., ge=1, description="Orden de Strahler del cauce")

    # Humedad de suelo ERA5-Land swvl2 (puede ser NaN si no disponible)
    soil_moisture_14d: Optional[float] = Field(
        None, description="Humedad suelo media 14d (m³/m³)"
    )

    # Estacionalidad (calculada externamente con número de semana/mes)
    semana_sin: float = Field(..., ge=-1, le=1, description="sin(2π × semana_iso / 52)")
    semana_cos: float = Field(..., ge=-1, le=1, description="cos(2π × semana_iso / 52)")
    mes_sin: float = Field(..., ge=-1, le=1, description="sin(2π × mes / 12)")
    mes_cos: float = Field(..., ge=-1, le=1, description="cos(2π × mes / 12)")

    model_config = {
        "json_schema_extra": {
            "example": {
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
                "mes_cos": 0.50,
            }
        }
    }


class PredictResponse(BaseModel):
    hybas_id: int
    probabilidad_deslizamiento: float = Field(..., ge=0, le=1)
    nivel_riesgo: str = Field(..., description="'Bajo' | 'Medio' | 'Alto'")
    timestamp: datetime


class BatchPredictRequest(BaseModel):
    cuencas: list[PredictRequest] = Field(..., min_length=1, max_length=549)


class BatchPredictResponse(BaseModel):
    semana: str = Field(
        ..., description="Semana ISO que se está prediciendo (YYYY-Www)"
    )
    n_cuencas: int
    resultados: list[PredictResponse]
    alto_riesgo: list[int] = Field(..., description="HYBAS_IDs con nivel Alto")


class HealthResponse(BaseModel):
    status: str
    modelo_cargado: bool
    modelo_nombre: Optional[str] = None
    modelo_version: Optional[str] = None
    timestamp: datetime


class MetadataResponse(BaseModel):
    modelo_nombre: str
    modelo_version: str
    departamento: str
    periodo_entrenamiento: str
    features: list[str]
    n_features: int
    granularidad: str
    umbral_staging_auc: float
    umbral_staging_precision: float
    descripcion: str
