# Stage 1: Build the React frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Build the backend and serve the unified app
FROM python:3.11-slim
WORKDIR /app

# Install uv for fast Python dependency management
RUN pip install --no-cache-dir uv

# Copy python package configuration
COPY pyproject.toml uv.lock ./

# Sync dependencies (system-wide for docker)
RUN uv sync --frozen --no-install-project

# Copy python app source
COPY backend/ ./backend/
COPY clickhouse/ ./clickhouse/
COPY data/ ./data/

# Copy built frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Finalize project install
RUN uv sync --frozen

EXPOSE 8000

# Start unified server
CMD ["uv", "run", "python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
