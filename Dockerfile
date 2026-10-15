# syntax=docker/dockerfile:1.7

# Genera la lista de instalación desde el lockfile de Poetry
FROM python:3.11-slim AS dependencies

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install poetry==2.4.1 poetry-plugin-export==1.10.0
WORKDIR /app
COPY pyproject.toml poetry.lock /app/
RUN poetry export --only main --format requirements.txt --without-hashes --output /requirements.txt

# La imagen final solo contiene las dependencias de ejecución
FROM python:3.11-slim

# Evita que Python escriba archivos .pyc en el disco
ENV PYTHONDONTWRITEBYTECODE=1
# Evita que Python guarde en el búfer los flujos de salida (útil para ver logs en tiempo real)
ENV PYTHONUNBUFFERED=1

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Instala las versiones resueltas por Poetry sin incluir Poetry en runtime
COPY --from=dependencies /requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

# Copia el resto del código del proyecto al contenedor
COPY . /app/