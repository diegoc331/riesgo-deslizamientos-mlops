export interface PredictRequest {
  hybas_id: number;
  precip_acum_14d: number;
  precip_acum_7d: number;
  precip_acum_3d: number;
  precip_max_diario_14d: number;
  precip_dias_lluvia_14d: number;
  SUB_AREA: number;
  UP_AREA: number;
  DIST_MAIN: number;
  ORDER: number;
  soil_moisture_14d?: number | null;
  semana_sin: number;
  semana_cos: number;
  mes_sin: number;
  mes_cos: number;
}

export interface PredictResponse {
  hybas_id: number;
  probabilidad_deslizamiento: number;
  nivel_riesgo: 'Bajo' | 'Medio' | 'Alto';
  timestamp: string;
}

export interface BatchPredictResponse {
  semana: string;
  n_cuencas: number;
  resultados: PredictResponse[];
  alto_riesgo: number[];
}

export interface HealthResponse {
  status: string;
  modelo_cargado: boolean;
  modelo_nombre: string | null;
  modelo_version: string | null;
  timestamp: string;
}

export interface MetadataResponse {
  modelo_nombre: string;
  modelo_version: string;
  departamento: string;
  periodo_entrenamiento: string;
  features: string[];
  n_features: number;
  granularidad: string;
  umbral_staging_auc: number;
  umbral_staging_precision: number;
  descripcion: string;
}

export interface ImpactoData {
  HYBAS_ID: number;
  SUB_AREA: number;
  n_eventos: number;
  fallecidos: number;
  heridos: number;
  personas: number;
  viviendas_destruidas: number;
  viviendas_averiadas: number;
  costo_m_cop: number;
  poblacion_estimada: number;
  indice_riesgo: number;
}

export type NivelRiesgo = 'Bajo' | 'Medio' | 'Alto' | 'Sin datos';
