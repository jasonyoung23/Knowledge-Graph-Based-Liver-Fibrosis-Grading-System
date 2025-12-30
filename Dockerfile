# Multi-stage build for Liver Fibrosis Grading System

# Stage 1: Build frontend
FROM node:18-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy package files
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy source code
COPY frontend/ ./

# Build frontend
RUN npm run build

# Stage 2: Python backend
FROM python:3.9-slim AS backend

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy backend requirements and install Python dependencies
COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend code
COPY backend/ backend/

# Copy built frontend
COPY --from=frontend-builder /app/frontend/dist frontend/dist/

# Copy data directory
COPY data/ data/

# Copy Python scripts
COPY *.py ./

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/health')"

# Default command
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]

# Stage 3: Frontend development server
FROM node:18-alpine AS frontend-dev

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ ./

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]

# Stage 4: Complete development environment
FROM python:3.9-slim AS development

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    nodejs \
    npm \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy all files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r backend/requirements.txt

# Install frontend dependencies
WORKDIR /app/frontend
RUN npm install

# Go back to root
WORKDIR /app

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

EXPOSE 8000 3000

CMD ["echo", "Use docker-compose for development environment"]
