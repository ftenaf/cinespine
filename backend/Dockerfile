FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml ./pyproject.toml
COPY uv.lock ./uv.lock

# Install dependencies (system-wide for docker)
RUN uv sync --frozen --no-install-project --all-extras

# Copy application code
COPY backend/ ./backend/
COPY clickhouse/ ./clickhouse/
COPY data/ ./data/

# Install the project itself
RUN uv sync --frozen --all-extras

EXPOSE 8000

# Start the application
CMD ["uv", "run", "python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
