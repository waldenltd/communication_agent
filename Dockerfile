# Communication Agent Dockerfile
# Multi-stage build for smaller production image

FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production image
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash agent

# Copy Python packages from builder
COPY --from=builder /root/.local /home/agent/.local

# Copy application code
COPY --chown=agent:agent . .

# Switch to non-root user
USER agent

# Add local pip packages to PATH
ENV PATH=/home/agent/.local/bin:$PATH

# Environment variables (can be overridden at runtime)
ENV AGENT_MODE=legacy
ENV HEALTH_PORT=8080
ENV PYTHONUNBUFFERED=1

# Health check using wget (smaller than curl)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:${HEALTH_PORT}/health || exit 1

# Expose health port
EXPOSE 8080

# Run the application
CMD ["python", "main.py"]
