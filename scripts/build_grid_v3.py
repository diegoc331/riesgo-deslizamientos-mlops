"""
Construye el grid semana × cuenca (dataset v3) y lo guarda como parquet.
Replica las celdas del Pilar 1 del notebook 03_pipeline_v3_cuencas.

Salida: data/processed/grid_cuencas_v3.parquet

Uso:
    uv run python scripts/build_grid_v3.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Resolver raíz del proyecto
_cwd = Path(__file__).resolve().parent
for _p in [_cwd, *_cwd.parents]:
    if (_p / "pyproject.toml").exists():
        ROOT = _p
        break
else:
    ROOT = _cwd.parent

sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from experiment.config import load_config
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


def _step(n: int, title: str) -> None:
    print(f"\n{'='*60}")
    print(f"PASO {n}: {title}")
    print(f"{'='*60}", flush=True)


def main() -> None:
    t0 = time.time()
    cfg = load_config(project_root=ROOT)
    print(f"Config cargada — periodo {cfg.periodo.anio_inicio}-{cfg.periodo.anio_fin}")

    # ------------------------------------------------------------------
    # PASO 1 — Capas espaciales (HydroBASINS + centroides municipales)
    # ------------------------------------------------------------------
    _step(1, "Capas espaciales")
    gdf_cuencas = download_hydrobasins(nivel=cfg.espacial.hydrobasins_nivel)
    gdf_mpios   = download_municipio_centroids()
    print(f"Cuencas: {len(gdf_cuencas)} | Municipios: {len(gdf_mpios)}")

    # ------------------------------------------------------------------
    # PASO 2 — CHIRPS diario → semanal
    # ------------------------------------------------------------------
    _step(2, "CHIRPS precipitacion diaria (puede tardar 30-60 min en primer uso)")
    df_chirps_daily   = load_chirps(cfg.periodo.anio_inicio, cfg.periodo.anio_fin)
    df_chirps_semanal = aggregate_weekly_chirps(df_chirps_daily)

    # ------------------------------------------------------------------
    # PASO 3 — Eventos UNGRD: filtrar deslizamientos en Antioquia
    # ------------------------------------------------------------------
    _step(3, "Eventos UNGRD — filtro deslizamientos Antioquia")
    df_ungrd = load_ungrd()

    pattern = "|".join(cfg.eventos.landslide_keywords)
    mask = (
        (df_ungrd["departamento"].str.upper() == "ANTIOQUIA") &
        (df_ungrd["evento"].str.lower().str.contains(pattern, na=False))
    )
    df_ant = df_ungrd[mask].copy()
    df_ant["fecha"] = pd.to_datetime(df_ant["fecha"], errors="coerce")
    df_ant = df_ant.dropna(subset=["fecha"])
    df_ant = df_ant[
        (df_ant["fecha"].dt.year >= cfg.periodo.anio_inicio) &
        (df_ant["fecha"].dt.year <= cfg.periodo.anio_fin)
    ]
    print(f"Eventos deslizamiento Antioquia {cfg.periodo.anio_inicio}-{cfg.periodo.anio_fin}: {len(df_ant)}")

    # ------------------------------------------------------------------
    # PASO 4 — Geocodificar y asignar a cuencas
    # ------------------------------------------------------------------
    _step(4, "Geocodificacion y asignacion a cuencas")
    gdf_eventos  = get_ungrd_with_coords(df_ant, gdf_mpios)
    gdf_asignado = assign_events_to_cuencas(gdf_eventos, gdf_cuencas)
    print(f"Eventos asignados a cuencas: {len(gdf_asignado)}")
    print(f"Cuencas con al menos 1 evento: {gdf_asignado['HYBAS_ID'].nunique()} / {len(gdf_cuencas)}")

    # ------------------------------------------------------------------
    # PASO 5 — Grid completo semana × cuenca
    # ------------------------------------------------------------------
    _step(5, "Grid semana x cuenca")
    df_grid = build_event_grid(
        gdf_asignado,
        gdf_cuencas,
        anio_inicio=cfg.periodo.anio_inicio,
        anio_fin=cfg.periodo.anio_fin,
    )

    # ------------------------------------------------------------------
    # PASO 6 — Pseudo-ausencias defensibles (usa CHIRPS real)
    # ------------------------------------------------------------------
    _step(6, "Pseudo-ausencias con CHIRPS")
    df_precip_pa = df_chirps_semanal[["anio_semana", "precip_acum_14d"]]
    df_grid_pa = generate_pseudo_absences(
        df_grid,
        df_precip_pa,
        gdf_cuencas,
        precip_percentil=cfg.espacial.pseudo_absence.precip_percentil,
        area_percentil=cfg.espacial.pseudo_absence.area_percentil,
        strict_mode=True,
    )

    # ------------------------------------------------------------------
    # PASO 7 — Features estáticas + estacionalidad + CHIRPS
    # ------------------------------------------------------------------
    _step(7, "Features: estáticas + estacionalidad + CHIRPS")

    # Estáticas de HydroSHEDS
    static_cols = [c for c in ["HYBAS_ID", "SUB_AREA", "UP_AREA", "DIST_MAIN", "ORDER"]
                   if c in gdf_cuencas.columns]
    df_static = pd.DataFrame(gdf_cuencas[static_cols])
    df_model  = df_grid_pa.merge(df_static, on="HYBAS_ID", how="left")

    # Estacionalidad cíclica
    df_model["semana_num"] = df_model["anio_semana"].apply(lambda p: p.week)
    df_model["mes_num"]    = df_model["anio_semana"].apply(lambda p: p.start_time.month)
    df_model["semana_sin"] = np.sin(2 * np.pi * df_model["semana_num"] / 52)
    df_model["semana_cos"] = np.cos(2 * np.pi * df_model["semana_num"] / 52)
    df_model["mes_sin"]    = np.sin(2 * np.pi * df_model["mes_num"] / 12)
    df_model["mes_cos"]    = np.cos(2 * np.pi * df_model["mes_num"] / 12)

    # Features CHIRPS
    FEATURES_CHIRPS = [
        "precip_acum_14d", "precip_max_diario_14d",
        "precip_dias_lluvia_14d", "precip_acum_7d", "precip_acum_3d",
    ]
    df_model = df_model.merge(
        df_chirps_semanal[["anio_semana"] + FEATURES_CHIRPS],
        on="anio_semana",
        how="left",
    )

    # Limpiar columnas auxiliares y ordenar por tiempo
    df_model = df_model.drop(columns=["semana_num", "mes_num"], errors="ignore")
    df_model = df_model.sort_values("anio_semana").reset_index(drop=True)

    # ------------------------------------------------------------------
    # PASO 8 — Guardar grid con pseudo-ausencias (para entrenamiento)
    # ------------------------------------------------------------------
    _step(8, "Guardar grid de entrenamiento (pseudo-ausencias)")

    # Period[W] no es serializable en parquet — convertir a string
    df_model["anio_semana"] = df_model["anio_semana"].astype(str)

    out_path = ROOT / "data" / "processed" / "grid_cuencas_v3.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_model.to_parquet(out_path, index=False)

    n_pos = df_model["deslizamiento"].sum()
    print(f"Grid entrenamiento guardado: {out_path}")
    print(f"  Shape: {df_model.shape} | Positivos: {n_pos:,} ({100*n_pos/len(df_model):.2f}%)")

    # ------------------------------------------------------------------
    # PASO 9 — Grid completo (todas las cuencas x semanas, sin filtro PA)
    #          Usado para evaluacion honesta post-entrenamiento.
    # ------------------------------------------------------------------
    _step(9, "Guardar grid completo para evaluacion (sin pseudo-ausencias)")

    df_full = df_grid.copy()

    # Mismas features estaticas
    df_full = df_full.merge(df_static, on="HYBAS_ID", how="left")

    # Estacionalidad ciclica
    df_full["semana_num"] = df_full["anio_semana"].apply(lambda p: p.week)
    df_full["mes_num"]    = df_full["anio_semana"].apply(lambda p: p.start_time.month)
    df_full["semana_sin"] = np.sin(2 * np.pi * df_full["semana_num"] / 52)
    df_full["semana_cos"] = np.cos(2 * np.pi * df_full["semana_num"] / 52)
    df_full["mes_sin"]    = np.sin(2 * np.pi * df_full["mes_num"] / 12)
    df_full["mes_cos"]    = np.cos(2 * np.pi * df_full["mes_num"] / 12)

    # Features CHIRPS
    df_full = df_full.merge(
        df_chirps_semanal[["anio_semana"] + FEATURES_CHIRPS],
        on="anio_semana",
        how="left",
    )
    df_full = df_full.drop(columns=["semana_num", "mes_num"], errors="ignore")
    df_full = df_full.sort_values("anio_semana").reset_index(drop=True)
    df_full["anio_semana"] = df_full["anio_semana"].astype(str)

    out_full = ROOT / "data" / "processed" / "grid_completo_v3.parquet"
    df_full.to_parquet(out_full, index=False)

    elapsed = (time.time() - t0) / 60
    n_pos_full = df_full["deslizamiento"].sum()
    print(f"Grid completo guardado: {out_full}")
    print(f"  Shape: {df_full.shape} | Positivos: {n_pos_full:,} ({100*n_pos_full/len(df_full):.2f}%)")
    print(f"\n{'='*60}")
    print(f"AMBOS GRIDS GUARDADOS")
    print(f"  Entrenamiento (PA) : {out_path.name} — {df_model.shape}")
    print(f"  Evaluacion (full)  : {out_full.name} — {df_full.shape}")
    print(f"  Tiempo total       : {elapsed:.1f} min")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
