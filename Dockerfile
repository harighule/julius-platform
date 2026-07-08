# Stage 1: Build the React/Vite frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

# Copy frontend package list and lock
COPY frontend/package*.json ./
RUN npm ci

# Copy the rest of the frontend source
COPY frontend/ ./

# Build the frontend (outputs to /app/frontend/dist)
RUN npm run build

# Stage 2: Set up the Python backend
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies (libc-dev needed for C extensions like netifaces)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libc-dev && rm -rf /var/lib/apt/lists/*

# Copy backend requirements, swap netifaces for the maintained fork, and install
COPY requirements.txt .
RUN sed -i 's/^netifaces.*/netifaces-plus>=0.12.3/' requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# Copy the entire workspace (including backend code)
COPY . .

# Copy the frontend build output from the first stage
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Expose the API and UI port
EXPOSE 8000

# Set environment variables for production
ENV JULIUS_HOST=0.0.0.0
ENV JULIUS_PORT=8000
ENV JULIUS_DEBUG=0
ENV ADMIN_IPS=*

# Start the FastAPI application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
