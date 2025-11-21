# Multi-stage build for Streamlit AI Agent UI
FROM python:3.12-slim as builder

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Set work directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./
COPY uv.lock ./

# Install Python dependencies using uv
RUN uv --version && uv sync --frozen

# Production stage
FROM python:3.12-slim as production

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_ENABLE_CORS=false \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=true \
    UV_CACHE_DIR=/app/cache/uv \
    UV_INDEX_URL=https://pypi.org/simple \
    A2A_HOST=0.0.0.0 \
    A2A_PORT=9000

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Install uv in production stage
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set work directory
WORKDIR /app

# Copy uv and Python dependencies from builder stage
COPY --from=builder /root/.local/bin/uv /root/.local/bin/uv
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY streamlit_agent_ui.py ./
COPY agents/ ./agents/
COPY devops_agents/ ./devops_agents/
COPY supervisor_with_aws_agent.py ./
COPY start_services.sh ./
COPY *.md ./

# Create necessary directories and set permissions
RUN mkdir -p /app/logs /app/data /app/cache /app/cache/uv /app/sessions /home/appuser/.cache/uv && \
    chmod +x /app/start_services.sh && \
    chown -R appuser:appuser /app /home/appuser

# Switch to non-root user
USER appuser

# Expose ports
# 8501: Streamlit frontend
# 9000: Backend A2A server
EXPOSE 8501 9000

# Health check - check both services
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health && curl -f http://localhost:9000/card || exit 1

# Run both services using startup script
CMD ["/app/start_services.sh"]
