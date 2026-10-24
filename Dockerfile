ARG PYTHON_VERSION=3.12-slim

FROM python:3.12-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -e .

FROM base AS semgrep-stage
RUN pip install --no-cache-dir semgrep==1.179.0 2>/dev/null || true
RUN curl -fsSL https://github.com/semgrep/semgrep/releases/download/v1.179.0/semgrep-linux-x86_64 -o /usr/local/bin/semgrep 2>/dev/null || true; chmod +x /usr/local/bin/semgrep 2>/dev/null || true

FROM aquasec/trivy:0.66.0 AS trivy-stage

FROM golang:1.22-bookworm AS osv-stage
RUN go install github.com/google/osv-scanner/cmd/osv-scanner@v2.6.0 2>/dev/null || true

FROM base AS final
COPY --from=semgrep-stage /usr/local/bin/semgrep /usr/local/bin/semgrep 2>/dev/null || true
COPY --from=osv-stage /go/bin/osv-scanner /usr/local/bin/osv-scanner 2>/dev/null || true
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
