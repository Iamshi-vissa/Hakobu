# syntax=docker/dockerfile:1.7

# ---------- builder: compile the Python virtualenv ----------
FROM ubuntu:24.04 AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv python3-dev build-essential \
 && rm -rf /var/lib/apt/lists/*
# --system-site-packages exposes the distro python3-uno (needed by unoserver) to the venv.
RUN python3 -m venv --system-site-packages /opt/venv
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install -r /tmp/requirements.txt

# ---------- runtime: conversion toolchain + app ----------
FROM ubuntu:24.04 AS runtime
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH" \
    HAKOBU_DATA_DIR=/data
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-uno \
      libreoffice-writer-nogui libreoffice-calc-nogui libreoffice-impress-nogui \
      ffmpeg pandoc calibre ghostscript \
      libvips42t64 libmagic1t64 libcairo2 \
      fonts-dejavu-core fonts-liberation2 fonts-noto-cjk \
      tini \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 hakobu \
 && mkdir -p /data && chown hakobu /data
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=hakobu . .
USER hakobu
EXPOSE 8000
ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
