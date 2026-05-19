"""
Prefect flow de ETL: descarga, procesa, valida y guarda el grid semana x cuenca.

Exporta:
  data_pipeline  — ETL completo; retorna (path_grid_pa, path_grid_completo)
  full_pipeline  — ETL + entrenamiento en secuencia (punto de entrada para scheduling)
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

import numpy as np
import pandas as pd
from prefect import flow, task, get_run_logger

from experiment.config import ExperimentConfig, load_config
from experiment.download import load_chirps, load_ungrd
from experiment.process import aggregate_weekly_chirps
from experiment.spatial import (
    assign_events_to_cuencas,
    build_event_grid,
    download_hydrobasins,
    download_municipio_centroids,
    generate_pseudo_absences,
    get_ungrd_with_coords,
)

_FEATURES_CHIRPS = [
    "precip_acum_14d",
    "precip_max_diario_14d",
    "precip_dias_lluvia_14d",
    "precip_acum_7d",
    "precip_acum_3d",
]
_STATIC_COLS = ["HYBAS_ID", "SUB_AREA", "UP_AREA", "DIST_MAIN", "ORDER"]


# ---------------------------------------------------------------------------
# Tasks individuales
# ---------------------------------------------------------------------------


@task(name="cargar-capas-espaciales", retries=2, retry_delay_seconds=30)
def task_cargar_espacial(cfg: ExperimentConfig):
    logger = get_run_logger()
    gdf_cuencas = download_hydrobasins(nivel=cfg.espacial.hydrobasins_nivel)
    gdf_mpios = download_municipio_centroids()
    logger.info(
        f"Capas espaciales: {len(gdf_cuencas)} cuencas | {len(gdf_mpios)} municipios"
    )
    return gdf_cuencas, gdf_mpios


@task(name="cargar-chirps", retries=3, retry_delay_seconds=60)
def task_cargar_chirps(cfg: ExperimentConfig):
    logger = get_run_logger()
    df_daily = load_chirps(cfg.periodo.anio_inicio, cfg.periodo.anio_fin)
    df_semanal = aggregate_weekly_chirps(df_daily)
    logger.info(f"CHIRPS: {len(df_daily):,} dias -> {len(df_semanal)} semanas semanal")
    return df_semanal


@task(name="cargar-ungrd")
def task_cargar_ungrd(cfg: ExperimentConfig):
    logger = get_run_logger()
    df_ungrd = load_ungrd()

    pattern = "|".join(cfg.eventos.landslide_keywords)
    mask = (df_ungrd["departamento"].str.upper() == "ANTIOQUIA") & (
        df_ungrd["evento"].str.lower().str.contains(pattern, na=False)
    )
    df_ant = df_ungrd[mask].copy()
    df_ant["fecha"] = pd.to_datetime(df_ant["fecha"], errors="coerce")
    df_ant = df_ant.dropna(subset=["fecha"])
    df_ant = df_ant[
        (df_ant["fecha"].dt.year >= cfg.periodo.anio_inicio)
        & (df_ant["fecha"].dt.year <= cfg.periodo.anio_fin)
    ]
    logger.info(
        f"UNGRD deslizamientos Antioquia "
        f"{cfg.periodo.anio_inicio}-{cfg.periodo.anio_fin}: {len(df_ant)}"
    )
    return df_ant


@task(name="geocodificar-eventos")
def task_geocodificar_eventos(df_eventos, gdf_mpios):
    logger = get_run_logger()
    gdf = get_ungrd_with_coords(df_eventos, gdf_mpios)
    logger.info(f"Eventos geocodificados: {len(gdf)}")
    return gdf


@task(name="asignar-cuencas")
def task_asignar_cuencas(gdf_eventos, gdf_cuencas):
    logger = get_run_logger()
    gdf = assign_events_to_cuencas(gdf_eventos, gdf_cuencas)
    logger.info(f"Eventos asignados a cuencas: {len(gdf)}")
    return gdf


@task(name="construir-grid")
def task_construir_grid(
    gdf_asignado, gdf_cuencas, df_chirps_semanal, cfg: ExperimentConfig
):
    logger = get_run_logger()

    df_grid_full = build_event_grid(
        gdf_asignado,
        gdf_cuencas,
        anio_inicio=cfg.periodo.anio_inicio,
        anio_fin=cfg.periodo.anio_fin,
    )
    logger.info(
        f"Grid completo: {len(df_grid_full):,} instancias | "
        f"pos={df_grid_full['deslizamiento'].sum()}"
    )

    df_precip_pa = df_chirps_semanal[["anio_semana", "precip_acum_14d"]]
    df_grid_pa = generate_pseudo_absences(
        df_grid_full,
        df_precip_pa,
        gdf_cuencas,
        precip_percentil=cfg.espacial.pseudo_absence.precip_percentil,
        area_percentil=cfg.espacial.pseudo_absence.area_percentil,
        strict_mode=True,
    )
    logger.info(
        f"Grid PA: {len(df_grid_pa):,} instancias | "
        f"pos={df_grid_pa['deslizamiento'].sum()}"
    )
    return df_grid_full, df_grid_pa


@task(name="validar-calidad-datos")
def task_validar_calidad(df_grid_pa: pd.DataFrame, cfg: ExperimentConfig) -> bool:
    logger = get_run_logger()
    errores = []

    n_pos = int(df_grid_pa["deslizamiento"].sum())
    if n_pos < 50:
        errores.append(f"Solo {n_pos} positivos — insuficiente para CV de 4 folds")

    semanas_esperadas = (cfg.periodo.anio_fin - cfg.periodo.anio_inicio + 1) * 52
    cobertura = df_grid_pa["anio_semana"].nunique() / semanas_esperadas
    if cobertura < 0.80:
        errores.append(f"Cobertura temporal {cobertura:.1%} < 80% minimo requerido")

    valores_invalidos = set(df_grid_pa["deslizamiento"].unique()) - {0, 1}
    if valores_invalidos:
        errores.append(f"Target con valores invalidos: {valores_invalidos}")

    if errores:
        msg = "Data quality gate fallido:\n" + "\n".join(f"  - {e}" for e in errores)
        logger.error(msg)
        raise ValueError(msg)

    logger.info(f"Data quality gate: OK  pos={n_pos} | cobertura={cobertura:.1%}")
    return True


@task(name="guardar-datasets")
def task_guardar_datasets(
    df_grid_full,
    df_grid_pa,
    gdf_cuencas,
    df_chirps_semanal,
    cfg: ExperimentConfig,
) -> tuple[str, str]:
    logger = get_run_logger()

    static_cols = [c for c in _STATIC_COLS if c in gdf_cuencas.columns]
    df_static = pd.DataFrame(gdf_cuencas[static_cols])

    def _enriquecer(df):
        df = df.merge(df_static, on="HYBAS_ID", how="left")
        df["semana_num"] = df["anio_semana"].apply(lambda p: p.week)
        df["mes_num"] = df["anio_semana"].apply(lambda p: p.start_time.month)
        df["semana_sin"] = np.sin(2 * np.pi * df["semana_num"] / 52)
        df["semana_cos"] = np.cos(2 * np.pi * df["semana_num"] / 52)
        df["mes_sin"] = np.sin(2 * np.pi * df["mes_num"] / 12)
        df["mes_cos"] = np.cos(2 * np.pi * df["mes_num"] / 12)
        df = df.merge(
            df_chirps_semanal[["anio_semana"] + _FEATURES_CHIRPS],
            on="anio_semana",
            how="left",
        )
        df = df.drop(columns=["semana_num", "mes_num"], errors="ignore")
        df = df.sort_values("anio_semana").reset_index(drop=True)
        df["anio_semana"] = df["anio_semana"].astype(str)
        return df

    # Validar features CHIRPS no completamente nulas post-merge
    df_pa_enriquecido = _enriquecer(df_grid_pa)
    df_full_enriquecido = _enriquecer(df_grid_full)

    cols_nulas = [c for c in _FEATURES_CHIRPS if df_pa_enriquecido[c].isnull().all()]
    if cols_nulas:
        raise ValueError(
            f"Features CHIRPS completamente nulas tras merge: {cols_nulas}"
        )

    out_dir = _PROJECT_ROOT / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    path_pa = out_dir / "grid_cuencas_v3.parquet"
    path_full = out_dir / "grid_completo_v3.parquet"

    df_pa_enriquecido.to_parquet(path_pa, index=False)
    df_full_enriquecido.to_parquet(path_full, index=False)

    n_pos_pa = int(df_pa_enriquecido["deslizamiento"].sum())
    n_pos_full = int(df_full_enriquecido["deslizamiento"].sum())
    logger.info(
        f"Grid PA   guardado: {path_pa.name}   shape={df_pa_enriquecido.shape} pos={n_pos_pa}"
    )
    logger.info(
        f"Grid full guardado: {path_full.name} shape={df_full_enriquecido.shape} pos={n_pos_full}"
    )
    return str(path_pa), str(path_full)


# ---------------------------------------------------------------------------
# Flow principal
# ---------------------------------------------------------------------------


@flow(name="antioquia-data-pipeline", log_prints=True)
def data_pipeline(config_path: str | None = None) -> tuple[str, str]:
    """
    ETL completo: descarga datos, construye grid semana x cuenca, valida y guarda.

    Returns
    -------
    (path_grid_pa, path_grid_completo) — rutas a los dos parquets generados
    """
    cfg = load_config(config_path, project_root=_PROJECT_ROOT)

    gdf_cuencas, gdf_mpios = task_cargar_espacial(cfg)
    df_chirps_semanal = task_cargar_chirps(cfg)
    df_eventos_raw = task_cargar_ungrd(cfg)
    gdf_eventos = task_geocodificar_eventos(df_eventos_raw, gdf_mpios)
    gdf_asignado = task_asignar_cuencas(gdf_eventos, gdf_cuencas)
    df_grid_full, df_grid_pa = task_construir_grid(
        gdf_asignado, gdf_cuencas, df_chirps_semanal, cfg
    )
    task_validar_calidad(df_grid_pa, cfg)
    path_pa, path_full = task_guardar_datasets(
        df_grid_full, df_grid_pa, gdf_cuencas, df_chirps_semanal, cfg
    )
    return path_pa, path_full


# ---------------------------------------------------------------------------
# Pipeline completo: ETL → Entrenamiento
# ---------------------------------------------------------------------------


@flow(name="antioquia-full-pipeline", log_prints=True)
def full_pipeline(
    config_path: str | None = None,
    umbral_auc: float = 0.60,
    umbral_precision: float = 0.006,
) -> dict:
    """
    Pipeline completo: ETL seguido de entrenamiento en secuencia.

    Ejecuta data_pipeline como subflow para obtener los grids actualizados,
    luego pasa las rutas resultantes a training_pipeline.

    Parameters
    ----------
    config_path       : ruta al YAML de configuracion (None = auto-detectar)
    umbral_auc        : AUC minimo sobre grid completo para Staging
    umbral_precision  : Precision minima sobre grid completo para Staging

    Returns
    -------
    dict con el resultado del mejor modelo (mismo formato que training_pipeline)
    """
    from training_flow import (
        training_pipeline,
    )  # import local para evitar ciclo al nivel de módulo

    path_pa, path_full = data_pipeline(config_path=config_path)

    return training_pipeline(
        grid_pa_path=path_pa,
        grid_full_path=path_full,
        config_path=config_path,
        umbral_auc=umbral_auc,
        umbral_precision=umbral_precision,
    )
