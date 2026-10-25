ARG PYTHON_VERSION=3.12-slim

FROM python:3.12-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 curl ca-certificates git \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -e .

FROM base AS semgrep-stage
RUN python -m venv /opt/semgrep \
 && /opt/semgrep/bin/pip install --no-cache-dir semgrep==1.179.0

FROM golang:1.27-bookworm AS osv-stage
RUN go install github.com/google/osv-scanner/v2/cmd/osv-scanner@v2.6.0

FROM base AS final
COPY --from=semgrep-stage /opt/semgrep /opt/semgrep
COPY --from=osv-stage /go/bin/osv-scanner /usr/local/bin/osv-scanner
RUN ln -s /opt/semgrep/bin/semgrep /usr/local/bin/semgrep
COPY app ./app
COPY spikes ./spikes
COPY alembic ./alembic
COPY alembic.ini ./
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
