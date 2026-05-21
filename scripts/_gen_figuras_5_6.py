"""Script temporal para generar figuras 5 y 6."""
import sys, warnings, os
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.dates as mdates
import unicodedata

OUT = "reports/figures"

# ─── Figura 5: Cobertura temporal de sensores ─────────────────────────────
print("Generando figura 5...")

chirps = pd.read_csv("data/raw/chirps_antioquia_daily.csv", parse_dates=["fecha"])
chirps = chirps.sort_values("fecha")
chirps["anio_semana"] = chirps["fecha"].dt.to_period("W")
chirps_semanal = chirps.groupby("anio_semana").agg(
    n_dias=("precip_mm", "count"),
    precip_media=("precip_mm", "mean"),
    precip_max=("precip_mm", "max"),
).reset_index()
chirps_semanal["cobertura_pct"] = (chirps_semanal["n_dias"] / 7 * 100).clip(0, 100)
chirps_semanal["fecha_fin"] = chirps_semanal["anio_semana"].apply(lambda p: p.end_time)

print(f"  CHIRPS: {len(chirps):,} dias, {len(chirps_semanal)} semanas")
print(f"  Rango: {chirps['fecha'].min().date()} -> {chirps['fecha'].max().date()}")

def norm(s):
    return unicodedata.normalize("NFD", str(s).lower()).encode("ascii","ignore").decode().strip()

ungrd = pd.read_csv("data/raw/ungrd_emergencias.csv", low_memory=False)
mask_dpto = ungrd["departamento"].apply(norm).str.contains("antioquia", na=False)
KWORDS = ["deslizamiento","derrumbe","movimiento en masa","remocion"]
mask_ev = ungrd["evento"].apply(lambda v: any(k in norm(str(v)) for k in KWORDS))
df_ev = ungrd[mask_dpto & mask_ev].copy()
df_ev["fecha"] = pd.to_datetime(df_ev["fecha"], errors="coerce")
df_ev = df_ev.dropna(subset=["fecha"])
df_ev["anio_semana"] = df_ev["fecha"].dt.to_period("W")
ev_semanal = df_ev.groupby("anio_semana").size().reset_index(name="n_eventos")
ev_semanal["fecha_fin"] = ev_semanal["anio_semana"].apply(lambda p: p.end_time)

fig, axes = plt.subplots(3, 1, figsize=(14, 11), sharex=True)
fig.suptitle("Cobertura temporal de fuentes de datos meteorologicos\nAntioquia 2019-2022",
             fontsize=13, fontweight="bold")

x_fechas = pd.to_datetime(chirps_semanal["fecha_fin"])

# Panel 1: Precipitacion CHIRPS
ax = axes[0]
ax.bar(x_fechas, chirps_semanal["precip_media"], color="#1565C0", alpha=0.7, width=6,
       label="Precip. media semanal CHIRPS (mm/dia)")
ax_twin = ax.twinx()
ax_twin.plot(x_fechas, chirps_semanal["precip_max"], color="#F57F17", linewidth=0.8,
             alpha=0.7, label="Max diario semana")
ax.set_ylabel("Precip. media (mm/dia)", color="#1565C0", fontsize=9)
ax_twin.set_ylabel("Max diario (mm)", color="#F57F17", fontsize=9)
ax.set_title("CHIRPS v2.0 - Precipitacion diaria satelital 5.5 km (cobertura 100%)", fontsize=10, loc="left")
ax.grid(axis="y", alpha=0.3)
# Temporadas de lluvia
for year in [2019, 2020, 2021, 2022]:
    for m0, m1 in [(3, 5), (9, 11)]:
        ax.axvspan(pd.Timestamp(year, m0, 1), pd.Timestamp(year, m1, 30),
                   alpha=0.07, color="#4CAF50", zorder=0)
lines1, labels1 = ax.get_legend_handles_labels()
lines2, labels2 = ax_twin.get_legend_handles_labels()
ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8)

# Panel 2: Cobertura comparativa
ax = axes[1]
ax.fill_between(x_fechas, chirps_semanal["cobertura_pct"],
                color="#1565C0", alpha=0.6, label="CHIRPS v2.0 (~100% cobertura diaria)")
np.random.seed(42)
ideam_sim = np.abs(np.random.normal(loc=2.5, scale=1.2, size=len(x_fechas))).clip(0, 6)
ax.fill_between(x_fechas, ideam_sim, color="#E65100", alpha=0.55,
                label="IDEAM sensores (simulado ~3.4% cobertura real)")
ax.axhline(100, color="#1565C0", linestyle="--", linewidth=0.8, alpha=0.5)
ax.axhline(3.4, color="#E65100", linestyle="--", linewidth=0.8, alpha=0.7,
           label="Techo real IDEAM (~3.4% area departamento)")
ax.set_ylabel("Cobertura (%)", fontsize=9)
ax.set_title("Cobertura espacial: CHIRPS (satelital) vs IDEAM (estaciones in-situ)\n"
             "La diferencia justifica el cambio de IDEAM a CHIRPS en la v3 del pipeline", fontsize=10, loc="left")
ax.set_ylim(0, 110)
ax.legend(loc="upper left", fontsize=8)
ax.grid(axis="y", alpha=0.3)
ax.text(0.99, 0.95, "CHIRPS cubre ~97 puntos grid/semana\nIDEAM: ~3.4% del area real",
        transform=ax.transAxes, fontsize=8, ha="right", va="top",
        bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

# Panel 3: Eventos UNGRD
ax = axes[2]
ax.bar(pd.to_datetime(ev_semanal["fecha_fin"]), ev_semanal["n_eventos"],
       color="#D32F2F", alpha=0.75, width=6, label="Eventos deslizamiento UNGRD por semana")
ax.set_ylabel("N eventos/semana", fontsize=9)
ax.set_title("Eventos UNGRD - Correlacion temporal con precipitacion", fontsize=10, loc="left")
ax.set_xlabel("Fecha", fontsize=10)
ax.grid(axis="y", alpha=0.3)
ax.legend(loc="upper left", fontsize=8)
max_ev = ev_semanal["n_eventos"].max()
ax.set_ylim(0, max_ev * 1.25)
ax.annotate("2022: 639 eventos\n(81 fallecidos)",
            xy=(pd.Timestamp("2022-09-15"), max_ev * 0.92),
            xytext=(pd.Timestamp("2021-06-01"), max_ev * 0.85),
            arrowprops=dict(arrowstyle="->", color="#B71C1C"),
            fontsize=8.5, color="#B71C1C")
ax.annotate("2019-2020:\n147 eventos\n(23 fallecidos)",
            xy=(pd.Timestamp("2020-06-01"), 15),
            xytext=(pd.Timestamp("2019-07-01"), max_ev * 0.4),
            arrowprops=dict(arrowstyle="->", color="#757575"),
            fontsize=8, color="#757575")

for ax_i in axes:
    ax_i.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1,4,7,10]))
    ax_i.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(ax_i.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=8)

plt.tight_layout()
plt.savefig(f"{OUT}/cobertura_temporal_sensores.png", dpi=150, bbox_inches="tight")
plt.close()
print("  OK  Figura 5 guardada")

# ─── Figura 6: BCR Waterfall ───────────────────────────────────────────────
print("Generando figura 6...")

COSTO_BASE   = 210_400  # M COP
RECALL       = 0.80
PRECISION_PA = 0.150
N_EVENTOS    = 945
COSTO_SISTEMA = 200
FACTOR_RED   = 0.40
COSTO_FA_UNIT = 5       # M COP por falsa alarma

costo_por_ev = COSTO_BASE / N_EVENTOS
tp   = round(RECALL * N_EVENTOS)
fn   = N_EVENTOS - tp
fp   = round(tp * (1 - PRECISION_PA) / PRECISION_PA)

danio_tp  = tp * costo_por_ev * (1 - FACTOR_RED)
danio_fn  = fn * costo_por_ev
danio_fa  = fp * COSTO_FA_UNIT
costo_con = danio_tp + danio_fn + danio_fa + COSTO_SISTEMA
beneficio = COSTO_BASE - costo_con
bcr       = beneficio / (COSTO_SISTEMA + danio_fa)

print(f"  BCR={bcr:.2f}x | TP={tp} FN={fn} FP={fp}")
print(f"  Beneficio: {beneficio:,.0f} M COP")

# Waterfall manual
componentes = [
    ("Costo hist.\nsin sistema",   COSTO_BASE,    "#1565C0",  0,                 "base"),
    ("(-) Dano resid.\nTP alertad.", -danio_tp,   "#66BB6A",  COSTO_BASE,        "sub"),
    ("(-) Dano total\nFN no alert.", -danio_fn,   "#EF9A9A",  COSTO_BASE-danio_tp,"sub"),
    ("(-) Falsas\nalarmas FP",       -danio_fa,   "#FFB74D",  COSTO_BASE-danio_tp-danio_fn, "sub"),
    ("(-) Operacion\nsistema",       -COSTO_SISTEMA, "#9575CD", COSTO_BASE-danio_tp-danio_fn-danio_fa, "sub"),
    ("Costo total\nCON sistema",    costo_con,     "#B71C1C",  0,                 "total"),
    ("BENEFICIO\nNETO",             beneficio,     "#2E7D32",  0,                 "benefit"),
]

fig, ax = plt.subplots(figsize=(13, 6.5))
fig.suptitle(
    f"Analisis Beneficio-Costo (BCR = {bcr:.2f}x)\n"
    f"Escenario conservador: reduccion de danos = {int(FACTOR_RED*100)}% | "
    f"Recall = {RECALL:.2f} | {N_EVENTOS} eventos | Sistema $200M COP / 4 anos",
    fontsize=11, fontweight="bold"
)

for i, (lbl, val, color, bot, tipo) in enumerate(componentes):
    if tipo == "sub":
        h   = abs(val)
        bot_plot = bot - h
        ax.bar(i, h, bottom=bot_plot, color=color, edgecolor="white", linewidth=0.8, width=0.65)
        ax.text(i, bot_plot + h/2, f"${h:,.0f}M", ha="center", va="center",
                fontsize=8, color="white", fontweight="bold")
        ax.annotate("", xy=(i, bot), xytext=(i-0.35, bot),
                    arrowprops=dict(arrowstyle="-", color="#616161", lw=0.5))
    elif tipo == "base":
        ax.bar(i, val, bottom=0, color=color, edgecolor="white", linewidth=0.8, width=0.65)
        ax.text(i, val/2, f"${val:,.0f}M", ha="center", va="center",
                fontsize=8.5, color="white", fontweight="bold")
    else:
        ax.bar(i, val, bottom=0, color=color, edgecolor="white", linewidth=0.8, width=0.65)
        ax.text(i, val/2,
                f"${val:,.0f}M\n({'BENEFICIO' if tipo=='benefit' else 'COSTO TOTAL'})",
                ha="center", va="center", fontsize=8, color="white", fontweight="bold")

ax.axhline(COSTO_BASE, color="#1565C0", linestyle="--", linewidth=1, alpha=0.5)
ax.axhline(costo_con,   color="#B71C1C", linestyle="--", linewidth=1, alpha=0.5)

ax.set_xticks(range(len(componentes)))
ax.set_xticklabels([c[0] for c in componentes], fontsize=9)
ax.set_ylabel("M COP", fontsize=11)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
ax.set_ylim(0, COSTO_BASE * 1.18)
ax.grid(axis="y", alpha=0.3)

ax.annotate(
    f"BCR = {bcr:.2f}x\nBeneficio / Inversion\n= ${beneficio:,.0f}M / ${int(COSTO_SISTEMA+danio_fa):,}M",
    xy=(6, beneficio * 0.5), xytext=(4.3, COSTO_BASE * 0.78),
    arrowprops=dict(arrowstyle="->", color="#2E7D32"),
    fontsize=9, color="#2E7D32",
    bbox=dict(boxstyle="round,pad=0.3", facecolor="#E8F5E9", alpha=0.9, edgecolor="#2E7D32")
)

from matplotlib.patches import Patch
leg = [
    Patch(facecolor="#1565C0", label=f"Costo hist. sin sistema: ${COSTO_BASE:,}M COP"),
    Patch(facecolor="#66BB6A", label=f"Dano resid. TP ({tp} eventos alertados, red. {int(FACTOR_RED*100)}%): ${danio_tp:,.0f}M"),
    Patch(facecolor="#EF9A9A", label=f"Dano total FN ({fn} eventos NO alertados): ${danio_fn:,.0f}M"),
    Patch(facecolor="#FFB74D", label=f"Falsas alarmas ({fp} FP x $5M COP): ${danio_fa:,.0f}M"),
    Patch(facecolor="#9575CD", label=f"Operacion del sistema (4 anos): ${COSTO_SISTEMA}M"),
    Patch(facecolor="#B71C1C", label=f"Costo total CON sistema: ${costo_con:,.0f}M"),
    Patch(facecolor="#2E7D32", label=f"BENEFICIO NETO: ${beneficio:,.0f}M COP"),
]
ax.legend(handles=leg, loc="upper right", fontsize=7.5, ncol=2)

plt.tight_layout()
plt.savefig(f"{OUT}/bcr_waterfall.png", dpi=150, bbox_inches="tight")
plt.close()
print("  OK  Figura 6 guardada")
print("\nTodas las figuras generadas con exito.")
