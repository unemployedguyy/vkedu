FROM apache/superset:5.0.0
USER root
RUN uv pip install --no-cache-dir sqlalchemy-trino
COPY bronze_check.py /app/bronze_check.py
USER superset
