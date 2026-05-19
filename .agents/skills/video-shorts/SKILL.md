# video-shorts

Genera un **YouTube Short** (~60s, 1080×1920, MP4) del proyecto de predicción de deslizamientos.

## Uso rápido

```bash
uv run python scripts/create_short_video.py
# Output: output/deslizamientos_short.mp4
```

## Dependencias

Ya instaladas en el entorno (`pyproject.toml`):
- `moviepy>=2.1` — ensamblado y export H.264
- `pillow>=11.0` — renderizado de frames con Pillow
- `imageio-ffmpeg>=0.4` — codificación FFmpeg

## Estructura del video (60s)

| # | Slide | Duración | Contenido |
|---|-------|----------|-----------|
| 1 | Intro | 7s | Título, chips de tecnología, UdeM |
| 2 | Problema | 10s | 3 stat cards — 945 eventos, $210 MM COP, 100% reactivo |
| 3 | Pipeline | 11s | 4 etapas: Datos → Procesamiento → Modelado → Serving |
| 4 | Modelo | 10s | 4 métricas: AUC 0.61, PR-AUC 0.848, Recall, n_estimators |
| 5 | Dashboard | 9s | `impacto_economico_dashboard.png` embebido |
| 6 | Impacto | 7s | BCR 2.11× hero card + 4 bullet cards |
| 7 | Cierre | 6s | Stack tecnológico (6 herramientas) + footer UdeM |

## Paleta de colores (identidad visual)

```
BG     = #0b1120  (fondo oscuro)
ACCENT = #0ea5a0  (teal — borde superior, highlights)
TEXT   = #f1f5f9  (blanco)
MUTED  = #94a3b8  (gris — subtextos)
```

## Personalización

Para cambiar textos, métricas o duración de slides:
- Edita las listas `stats`, `stages`, `metrics`, `bullets` dentro de cada función `_slide_*`
- Cambia `duration` en la lista `slides` de `create_video()`

## Assets requeridos

- `data/processed/impacto_economico_dashboard.png` — dashboard económico (Fase 05)
- Si no existe, el slide 5 muestra un placeholder sin errores
