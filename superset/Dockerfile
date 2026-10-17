FROM apache/superset:5.0.0
USER root
RUN /app/.venv/bin/pip install --no-cache-dir sqlalchemy-trino
USER superset
