# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.13.3 AS uv-bin

FROM python:3.14-slim AS dependencies
COPY --from=uv-bin /uv /uvx /bin/
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock /app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app

COPY --from=dependencies /opt/venv /opt/venv
COPY . /app/