# Comparateur de scénarios — image autonome, sans aucun accès réseau à l'exécution.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SCENARIO_DATA_DIR=/data \
    SCENARIO_HOST=0.0.0.0 \
    SCENARIO_PORT=8080

WORKDIR /opt/scenario
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app

RUN mkdir -p /data && chmod 777 /data
VOLUME /data
EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=4)" || exit 1

CMD ["python", "-m", "app.main"]
