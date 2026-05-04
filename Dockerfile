# ============================================================
# VoltimaxChat AI Service — Production Dockerfile
# Multi-stage: Node (dashboard build) → Python (runtime)
# ============================================================

# ── Stage 1: Build React Dashboard ──────────────────────────
FROM node:22-slim AS dashboard-builder
WORKDIR /build
COPY dashboard-react/package*.json ./
RUN npm ci --production=false
COPY dashboard-react/ ./
RUN npm run build

# ── Stage 2: Python Runtime ─────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY app/ app/
COPY scripts/ scripts/
COPY static/ static/
COPY docs/ docs/

# Dashboard build from stage 1
COPY --from=dashboard-builder /dashboard-build/ dashboard-build/

# Create directories
RUN mkdir -p knowledge_files static/forms

# Non-root user for security
RUN useradd -m -r appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
