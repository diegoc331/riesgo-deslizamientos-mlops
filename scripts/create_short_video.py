"""
create_short_video.py
Video de lanzamiento de VigilantIA (40s, 1080x1920).
App de alerta temprana de deslizamientos — Antioquia, Colombia.
Tagline: "Predice. Protege. Previene."

Uso:
    uv run python scripts/create_short_video.py
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
from moviepy import ImageClip, concatenate_videoclips, vfx
from PIL import Image, ImageDraw, ImageFont

# ── Paleta VigilantIA ─────────────────────────────────────────────────────────
W, H = 1080, 1920
BG = (8, 12, 22)
BG2 = (11, 18, 34)
ACCENT = (14, 165, 160)
ACCENT2 = (45, 212, 191)
TEXT = (241, 245, 249)
MUTED = (148, 163, 184)
CARD = (14, 24, 44)
CARD2 = (18, 30, 54)
RED = (239, 68, 68)
AMBER = (245, 158, 11)
GREEN = (34, 197, 94)
FPS = 30

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_MP4 = OUTPUT_DIR / "deslizamientos_short.mp4"

APP_NAME = "VigilantIA"
TAGLINE = "Predice. Protege. Previene."


# ── Fuentes ───────────────────────────────────────────────────────────────────


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "calibrib.ttf" if bold else "calibri.ttf"
    try:
        return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
    except OSError:
        return ImageFont.load_default()


# ── Primitivas ────────────────────────────────────────────────────────────────


def _canvas(bg: tuple = BG) -> tuple[Image.Image, ImageDraw.Draw]:
    img = Image.new("RGB", (W, H), bg)
    return img, ImageDraw.Draw(img)


def _tw(draw: ImageDraw.Draw, text: str, font) -> int:
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0]


def _th(draw: ImageDraw.Draw, text: str, font) -> int:
    b = draw.textbbox((0, 0), text, font=font)
    return b[3] - b[1]


def _cx(draw: ImageDraw.Draw, text: str, y: int, font, color: tuple = TEXT) -> int:
    x = max(60, (W - _tw(draw, text, font)) // 2)
    draw.text((x, y), text, fill=color, font=font)
    return y + _th(draw, text, font)


def _gradient(top: tuple, bot: tuple) -> Image.Image:
    img = Image.new("RGB", (W, H))
    for y in range(H):
        t = y / H
        img.paste(
            (
                int(top[0] + (bot[0] - top[0]) * t),
                int(top[1] + (bot[1] - top[1]) * t),
                int(top[2] + (bot[2] - top[2]) * t),
            ),
            (0, y, W, y + 1),
        )
    return img


def _glow(
    img: Image.Image,
    cx: int,
    cy: int,
    color: tuple,
    steps=((500, 12), (360, 24), (220, 44), (120, 72)),
) -> Image.Image:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for r, a in steps:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*color, a))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def _phone_frame(
    draw: ImageDraw.Draw,
    x: int,
    y: int,
    pw: int,
    ph: int,
    screen_color: tuple = (10, 18, 32),
) -> tuple:
    """Dibuja marco de telefono, devuelve (sx,sy,sw,sh) del area de pantalla."""
    border = 14
    notch_w = 200
    # Cuerpo del telefono
    draw.rounded_rectangle([x, y, x + pw, y + ph], radius=60, fill=(22, 32, 54))
    draw.rounded_rectangle([x, y, x + pw, y + ph], radius=60, outline=ACCENT, width=3)
    # Pantalla
    sx, sy = x + border, y + border
    sw, sh = pw - 2 * border, ph - 2 * border
    draw.rounded_rectangle([sx, sy, sx + sw, sy + sh], radius=48, fill=screen_color)
    # Notch
    nx = sx + (sw - notch_w) // 2
    draw.rounded_rectangle(
        [nx, sy, nx + notch_w, sy + 36], radius=18, fill=(22, 32, 54)
    )
    # Boton home (circulo en la parte de abajo)
    hx = sx + sw // 2
    hy = y + ph - border - 22
    draw.ellipse([hx - 22, hy - 22, hx + 22, hy + 22], fill=(30, 44, 72))
    return sx, sy, sw, sh


def _cuencas_map(
    draw: ImageDraw.Draw,
    x0: int,
    y0: int,
    cols: int,
    rows: int,
    cell: int,
    seed: int = 42,
) -> None:
    """Grilla estilizada de cuencas con colores de riesgo."""
    random.seed(seed)
    palette = [(GREEN, 0.52), (AMBER, 0.31), (RED, 0.17)]
    for row in range(rows):
        for col in range(cols):
            # Mascara aproximada de Antioquia
            if col == 0 and row < 5:
                continue
            if col <= 1 and row > cols - 3:
                continue
            if col >= cols - 2 and row < 4:
                continue
            r = random.random()
            cum = 0.0
            for color, prob in palette:
                cum += prob
                if r < cum:
                    cx = x0 + col * (cell + 2)
                    cy = y0 + row * (cell + 2)
                    draw.rounded_rectangle(
                        [cx, cy, cx + cell, cy + cell], radius=5, fill=color
                    )
                    break


def _logo(draw: ImageDraw.Draw, cx: int, cy: int, size: int = 120) -> None:
    """Dibuja el icono de VigilantIA: escudo + ojo + onda."""
    # Escudo
    s = size
    pts = [
        (cx, cy - s),
        (cx + s * 0.75, cy - s * 0.5),
        (cx + s * 0.75, cy + s * 0.2),
        (cx, cy + s),
        (cx - s * 0.75, cy + s * 0.2),
        (cx - s * 0.75, cy - s * 0.5),
    ]
    pts = [(int(x), int(y)) for x, y in pts]
    draw.polygon(pts, fill=ACCENT)
    # Interior del escudo (mas oscuro)
    inner = [(int(cx + (x - cx) * 0.7), int(cy + (y - cy) * 0.7)) for x, y in pts]
    draw.polygon(inner, fill=(8, 40, 38))
    # Ojo en el centro
    ew = int(s * 0.55)
    eh = int(s * 0.32)
    draw.ellipse([cx - ew, cy - eh, cx + ew, cy + eh], fill=ACCENT2)
    draw.ellipse(
        [
            cx - int(ew * 0.45),
            cy - int(eh * 0.45),
            cx + int(ew * 0.45),
            cy + int(eh * 0.45),
        ],
        fill=(8, 40, 38),
    )
    draw.ellipse(
        [
            cx - int(ew * 0.22),
            cy - int(eh * 0.22),
            cx + int(ew * 0.22),
            cy + int(eh * 0.22),
        ],
        fill=TEXT,
    )


# ── Slides ────────────────────────────────────────────────────────────────────


def _slide_logo() -> Image.Image:
    """4s — Reveal del logo y nombre de la app."""
    img = _gradient((6, 10, 20), (10, 20, 36))
    img = _glow(
        img, W // 2, H // 2 - 100, ACCENT, ((480, 10), (340, 20), (210, 38), (110, 62))
    )
    draw = ImageDraw.Draw(img)

    # Borde superior teal
    draw.rectangle([0, 0, W, 10], fill=ACCENT)

    # Logo
    _logo(draw, W // 2, H // 2 - 200, size=100)

    f_name = _font(120, bold=True)
    f_ia = _font(120, bold=True)
    f_tag = _font(38)
    f_sub = _font(26)

    # Nombre partido en "Vigilant" + "IA" con color diferente
    text_v = "Vigilant"
    text_i = "IA"
    w_v = _tw(draw, text_v, f_name)
    w_i = _tw(draw, text_i, f_ia)
    total_w = w_v + w_i
    start_x = (W - total_w) // 2
    y_name = H // 2 - 30

    draw.text((start_x, y_name), text_v, fill=TEXT, font=f_name)
    draw.text((start_x + w_v, y_name), text_i, fill=ACCENT, font=f_ia)

    y = y_name + _th(draw, APP_NAME, f_name) + 18

    # Linea separadora
    draw.line([(W // 2 - 260, y), (W // 2 + 260, y)], fill=ACCENT, width=2)
    y += 24

    y = _cx(draw, TAGLINE, y, f_tag, MUTED)
    y += 22
    _cx(draw, "Antioquia, Colombia", y, f_sub, (71, 85, 105))

    # Borde inferior
    draw.rectangle([0, H - 10, W, H], fill=ACCENT)
    return img


def _slide_problema() -> Image.Image:
    """4s — Estadisticas del problema."""
    img = _gradient((10, 14, 26), (14, 20, 38))
    img = _glow(img, W // 2, 700, RED, ((360, 10), (240, 20), (140, 35)))
    draw = ImageDraw.Draw(img)

    f_h = _font(60, bold=True)
    f_xl = _font(104, bold=True)
    f_md = _font(34)
    f_sm = _font(26)
    f_xs = _font(22)

    y = 120
    y = _cx(draw, "El problema es urgente.", y, f_h, TEXT) + 50

    # Stat 1
    draw.rounded_rectangle([60, y, W - 60, y + 260], radius=22, fill=CARD)
    draw.rounded_rectangle([60, y, W - 60, y + 8], radius=4, fill=RED)
    _cx(draw, "945", y + 18, f_xl, RED)
    _cx(draw, "deslizamientos en Antioquia", y + 148, f_md, TEXT)
    _cx(draw, "2019 – 2022  (UNGRD)", y + 200, f_xs, MUTED)
    y += 288

    # Stat 2
    draw.rounded_rectangle([60, y, W - 60, y + 240], radius=22, fill=CARD)
    draw.rounded_rectangle([60, y, W - 60, y + 8], radius=4, fill=AMBER)
    _cx(draw, "$210 MM COP", y + 18, _font(80, bold=True), AMBER)
    _cx(draw, "en perdidas economicas", y + 130, f_md, TEXT)
    _cx(draw, "INVIAS / DNP 2023", y + 180, f_xs, MUTED)
    y += 268

    _cx(draw, "Sin una sola alerta previa.", y, f_h, (200, 70, 70))

    return img


def _slide_pivot() -> Image.Image:
    """3s — Giro: VigilantIA lo cambia."""
    img = Image.new("RGB", (W, H), (5, 14, 18))
    img = _glow(
        img,
        W // 2,
        H // 2,
        ACCENT,
        ((600, 10), (420, 22), (280, 40), (160, 65), (80, 90)),
    )
    draw = ImageDraw.Draw(img)

    _logo(draw, W // 2, H // 2 - 250, size=88)

    f_xl = _font(96, bold=True)
    f_lg = _font(54, bold=True)
    f_md = _font(36)

    y = H // 2 - 60
    y = _cx(draw, APP_NAME, y, f_xl, ACCENT) + 16
    y = _cx(draw, "lo vio venir.", y, f_lg, TEXT) + 40
    _cx(draw, "7 dias antes.", y, f_md, MUTED)

    return img


def _slide_app_mapa() -> Image.Image:
    """5s — App en accion: mapa de cuencas con riesgo en tiempo real."""
    img = _gradient((8, 12, 22), (10, 18, 32))
    draw = ImageDraw.Draw(img)

    f_h = _font(50, bold=True)
    f_md = _font(28, bold=True)
    f_sm = _font(22)
    f_xs = _font(18)

    # Header
    y = 70
    y = _cx(draw, "Mapa de Riesgo en Vivo", y, f_h, TEXT) + 8
    y = _cx(draw, "549 cuencas de Antioquia", y, f_md, ACCENT) + 30

    # Mockup del telefono
    ph_w, ph_h = 680, 980
    ph_x = (W - ph_w) // 2
    ph_y = y

    sx, sy, sw, sh = _phone_frame(
        draw, ph_x, ph_y, ph_w, ph_h, screen_color=(8, 16, 28)
    )

    # App header dentro del telefono
    screen_draw = draw
    app_bar_y = sy + 44
    screen_draw.rounded_rectangle(
        [sx, app_bar_y, sx + sw, app_bar_y + 70], radius=0, fill=(10, 22, 40)
    )

    # Logo pequeño en app header
    _logo(screen_draw, sx + 46, app_bar_y + 36, size=22)
    screen_draw.text(
        (sx + 80, app_bar_y + 18), "VigilantIA", fill=TEXT, font=_font(28, bold=True)
    )

    # Notificacion activa en app bar
    notif_x = sx + sw - 170
    screen_draw.rounded_rectangle(
        [notif_x, app_bar_y + 16, notif_x + 148, app_bar_y + 54], radius=20, fill=RED
    )
    screen_draw.text(
        (notif_x + 18, app_bar_y + 22),
        "2 ALERTAS",
        fill=TEXT,
        font=_font(20, bold=True),
    )

    # Mapa de cuencas
    map_y = app_bar_y + 80
    map_h = sh - 80 - 60  # espacio para nav bar
    cell_size = 26
    cols_m = sw // (cell_size + 2)
    rows_m = map_h // (cell_size + 2)
    _cuencas_map(screen_draw, sx + 8, map_y, cols_m, rows_m, cell_size, seed=7)

    # Overlay de alerta en el mapa
    alert_y = map_y + map_h - 120
    screen_draw.rounded_rectangle(
        [sx + 12, alert_y, sx + sw - 12, alert_y + 100], radius=14, fill=(30, 10, 10)
    )
    screen_draw.rounded_rectangle(
        [sx + 12, alert_y, sx + sw - 12, alert_y + 6], radius=3, fill=RED
    )
    screen_draw.text(
        (sx + 28, alert_y + 12), "RIESGO ALTO", fill=RED, font=_font(24, bold=True)
    )
    screen_draw.text(
        (sx + 28, alert_y + 50), "Cuenca 4100561480 · Norte", fill=MUTED, font=_font(20)
    )
    screen_draw.text(
        (sx + sw - 110, alert_y + 30), "Ver >", fill=ACCENT, font=_font(22, bold=True)
    )

    # Nav bar
    nav_y = sy + sh - 62
    screen_draw.rounded_rectangle(
        [sx, nav_y, sx + sw, sy + sh], radius=0, fill=(10, 22, 40)
    )
    nav_items = [
        ("Mapa", True),
        ("Alertas", False),
        ("Zonas", False),
        ("Config", False),
    ]
    nw = sw // len(nav_items)
    for i, (label, active) in enumerate(nav_items):
        nx = sx + i * nw + nw // 2
        color = ACCENT if active else MUTED
        screen_draw.text(
            (nx - _tw(screen_draw, label, _font(18)) // 2, nav_y + 16),
            label,
            fill=color,
            font=_font(18),
        )

    y = ph_y + ph_h + 28

    # Leyenda
    ley_items = [("Bajo", GREEN), ("Medio", AMBER), ("Alto", RED)]
    lx = 100
    for label, color in ley_items:
        draw.rounded_rectangle([lx, y, lx + 26, y + 26], radius=5, fill=color)
        draw.text((lx + 34, y + 2), label, fill=MUTED, font=f_xs)
        lx += 180
    y += 40
    _cx(draw, "Actualizacion semanal automatica", y, f_sm, (71, 85, 105))

    return img


def _slide_notificacion() -> Image.Image:
    """4s — Notificacion push: alerta 7 dias antes."""
    img = _gradient((8, 12, 22), (12, 18, 32))
    draw = ImageDraw.Draw(img)

    f_h = _font(54, bold=True)
    f_md = _font(30)
    f_sm = _font(24)

    y = 100
    y = _cx(draw, "Alertas antes del evento.", y, f_h, TEXT) + 50

    # Mockup de notificacion push (iPhone / Android style)
    notif_w = W - 80
    notif_x = 40

    # Fondo blur del wallpaper
    draw.rounded_rectangle(
        [notif_x - 4, y - 4, notif_x + notif_w + 4, y + 340],
        radius=30,
        fill=(20, 30, 50),
    )

    # Notificacion card
    draw.rounded_rectangle(
        [notif_x, y, notif_x + notif_w, y + 320], radius=26, fill=(16, 26, 46)
    )
    draw.rounded_rectangle([notif_x, y, notif_x + notif_w, y + 8], radius=4, fill=RED)

    # App icon en la notif
    _logo(draw, notif_x + 52, y + 66, size=36)
    draw.text((notif_x + 100, y + 22), APP_NAME, fill=TEXT, font=_font(26, bold=True))
    draw.text((notif_x + 100, y + 58), "hace unos segundos", fill=MUTED, font=_font(20))

    draw.text(
        (notif_x + 36, y + 108),
        "Alerta de Riesgo Alto",
        fill=RED,
        font=_font(34, bold=True),
    )
    draw.text(
        (notif_x + 36, y + 162),
        "Cuenca Norte Antioquia  (4100561480)",
        fill=TEXT,
        font=_font(26),
    )
    draw.text(
        (notif_x + 36, y + 206),
        "Probabilidad 82%  ·  Horizonte: 7 dias",
        fill=MUTED,
        font=_font(24),
    )

    # Botones de accion
    btn_y = y + 256
    btn_w = (notif_w - 48) // 2
    draw.rounded_rectangle(
        [notif_x + 16, btn_y, notif_x + 16 + btn_w, btn_y + 48],
        radius=10,
        fill=(10, 30, 30),
    )
    _cx_in = notif_x + 16 + btn_w // 2
    draw.text(
        (_cx_in - _tw(draw, "Ver mapa", _font(22, bold=True)) // 2, btn_y + 12),
        "Ver mapa",
        fill=ACCENT,
        font=_font(22, bold=True),
    )

    draw.rounded_rectangle(
        [notif_x + 32 + btn_w, btn_y, notif_x + 32 + btn_w * 2, btn_y + 48],
        radius=10,
        fill=RED,
    )
    cx2 = notif_x + 32 + btn_w + btn_w // 2
    draw.text(
        (cx2 - _tw(draw, "Activar alerta", _font(22, bold=True)) // 2, btn_y + 12),
        "Activar alerta",
        fill=TEXT,
        font=_font(22, bold=True),
    )

    y += 340 + 40

    # Punto de venta debajo
    draw.rounded_rectangle([60, y, W - 60, y + 180], radius=20, fill=CARD)
    draw.rounded_rectangle([60, y, W - 60, y + 7], radius=4, fill=ACCENT)
    _cx(draw, "7 dias de anticipacion", y + 18, _font(48, bold=True), ACCENT)
    _cx(draw, "para pre-posicionar recursos", y + 82, f_md, TEXT)
    _cx(draw, "y salvar vidas.", y + 122, f_md, MUTED)

    return img


def _slide_usuarios() -> Image.Image:
    """4s — Quienes usan VigilantIA. Usuarios finales institucionales."""
    img = _gradient((8, 12, 22), (10, 18, 32))
    draw = ImageDraw.Draw(img)

    f_h = _font(54, bold=True)
    f_md = _font(32, bold=True)
    f_sm = _font(24)
    f_xs = _font(20)

    y = 90
    y = _cx(draw, "Disenado para", y, f_h, TEXT) + 8
    y = _cx(draw, "quienes protegen comunidades.", y, _font(38, bold=True), ACCENT) + 40

    users = [
        (
            ACCENT,
            "UNGRD",
            "Gestion nacional del riesgo",
            "Monitoreo 549 cuencas en tiempo real",
        ),
        (
            GREEN,
            "DAGRD / DAPARD",
            "Defensa civil departamental",
            "Alertas por zona de responsabilidad",
        ),
        (
            AMBER,
            "Alcaldias",
            "Gobiernos municipales",
            "Suscripcion a cuencas del municipio",
        ),
        (
            (129, 140, 248),
            "Desarrolladores",
            "Integracion via API REST",
            "POST /predict  <  100 ms",
        ),
    ]

    mx = 56
    cw = W - 2 * mx
    uh = 196
    gap = 18

    for color, title, sub1, sub2 in users:
        draw.rounded_rectangle([mx, y, mx + cw, y + uh], radius=18, fill=CARD)
        draw.rounded_rectangle([mx, y, mx + 9, y + uh], radius=4, fill=color)

        # Circulo de color
        draw.ellipse(
            [mx + 28, y + uh // 2 - 34, mx + 96, y + uh // 2 + 34], fill=(*color, 30)
        )
        draw.ellipse([mx + 46, y + uh // 2 - 18, mx + 80, y + uh // 2 + 18], fill=color)

        draw.text((mx + 110, y + 28), title, fill=TEXT, font=f_md)
        draw.text((mx + 110, y + 80), sub1, fill=MUTED, font=f_sm)
        draw.text((mx + 110, y + 116), sub2, fill=(71, 85, 105), font=f_xs)

        y += uh + gap

    return img


def _slide_cta() -> Image.Image:
    """8s — CTA: descarga / accede a VigilantIA."""
    img = Image.new("RGB", (W, H), (5, 12, 20))
    img = _glow(
        img,
        W // 2,
        H // 2 - 80,
        ACCENT,
        ((580, 10), (400, 20), (260, 38), (150, 62), (80, 85)),
    )
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, W, 10], fill=ACCENT)
    draw.rectangle([0, H - 10, W, H], fill=ACCENT)

    f_xl = _font(96, bold=True)
    f_lg = _font(58, bold=True)
    f_md = _font(32)
    f_sm = _font(26)
    f_xs = _font(22)

    # Logo grande
    _logo(draw, W // 2, 320, size=110)

    # Nombre
    text_v, text_i = "Vigilant", "IA"
    f_name = _font(110, bold=True)
    w_v = _tw(draw, text_v, f_name)
    w_i = _tw(draw, text_i, f_name)
    sx = (W - w_v - w_i) // 2
    y_name = 490
    draw.text((sx, y_name), text_v, fill=TEXT, font=f_name)
    draw.text((sx + w_v, y_name), text_i, fill=ACCENT, font=f_name)

    y = y_name + _th(draw, APP_NAME, f_name) + 14
    y = _cx(draw, TAGLINE, y, f_lg, MUTED) + 44

    # Divider
    draw.line([(W // 2 - 280, y), (W // 2 + 280, y)], fill=ACCENT, width=3)
    y += 34

    # Opciones de acceso
    y = _cx(draw, "Disponible para tu organizacion:", y, f_md, TEXT) + 30

    opciones = [
        ("Web App", "vigilantia.app"),
        ("API REST", "api.vigilantia.app/predict"),
        ("App Movil", "iOS  &  Android — Proximamente"),
    ]

    mx = 60
    cw = W - 2 * mx
    oh = 130
    gap = 14

    for label, detail in opciones:
        draw.rounded_rectangle([mx, y, mx + cw, y + oh], radius=16, fill=CARD)
        draw.rounded_rectangle(
            [mx, y, mx + cw, y + oh], radius=16, outline=ACCENT, width=1
        )
        draw.text((mx + 32, y + 20), label, fill=ACCENT, font=_font(30, bold=True))
        draw.text((mx + 32, y + 68), detail, fill=TEXT, font=f_sm)
        y += oh + gap

    y += 14
    draw.line([(W // 2 - 200, y), (W // 2 + 200, y)], fill=(22, 34, 56), width=2)
    y += 22
    _cx(draw, "Universidad de Medellin", y, f_xs, MUTED)
    y += 36
    _cx(draw, "Proyecto MLOps II  ·  2026", y, _font(20), (50, 64, 86))

    return img


# ── Ensamblado ────────────────────────────────────────────────────────────────


def _clip(
    img: Image.Image, duration: float, fi: float = 0.35, fo: float = 0.35
) -> ImageClip:
    clip = ImageClip(np.array(img)).with_duration(duration)
    return clip.with_effects([vfx.FadeIn(fi), vfx.FadeOut(fo)])


def create_video(output: Path = OUTPUT_MP4, fps: int = FPS) -> None:
    scenes = [
        (_slide_logo, 4.0, "Logo reveal — VigilantIA"),
        (_slide_problema, 4.0, "El problema"),
        (_slide_pivot, 3.0, "Pivot — lo vio venir"),
        (_slide_app_mapa, 5.0, "App — mapa de cuencas"),
        (_slide_notificacion, 4.0, "Notificacion push"),
        (_slide_usuarios, 4.0, "Usuarios institucionales"),
        (_slide_cta, 8.0, "CTA — accede ahora"),
    ]

    clips = []
    for fn, duration, name in scenes:
        print(f"  {name} ({duration}s)...")
        clips.append(_clip(fn(), duration))

    print("Ensamblando...")
    final = concatenate_videoclips(clips, method="compose")

    print(f"Exportando -> {output}")
    final.write_videofile(
        str(output), fps=fps, codec="libx264", audio=False, logger="bar"
    )
    total = sum(d for _, d, _ in scenes)
    print(f"\nListo: {output}  |  {total}s  |  {W}x{H}  |  {fps}fps")


if __name__ == "__main__":
    create_video()
