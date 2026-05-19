# Imagen de producción para la API de predicción de deslizamientos
FROM python:3.11-slim

# Usuario no-root por seguridad
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Instalar uv (gestor de paquetes)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copiar dependencias primero (aprovecha caché de Docker)
COPY pyproject.toml .
COPY uv.lock* .

# Instalar dependencias en el entorno del sistema (sin venv)
RUN uv pip install --system --no-cache -e .

# Copiar código fuente y configuración
COPY src/ src/
COPY configs/ configs/

# Crear directorio de logs (escribible por appuser)
RUN mkdir -p logs data/processed && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Variables de entorno por defecto
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')"

CMD ["uvicorn", "experiment.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
