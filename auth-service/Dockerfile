# FROM python:3.12-slim

# WORKDIR /app

# # Install system deps
# RUN apt-get update && apt-get install -y build-essential 
# # && rm -rf /var/lib/apt/lists/*

# # Copy requirements first (cache optimization)
# COPY requirements.txt .

# RUN pip install --no-cache-dir -r requirements.txt

# # Copy app (including start.sh)
# COPY . .

# # Make startup script executable
# RUN chmod +x start.sh

# EXPOSE 8000

# CMD ["./start.sh"]

# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Install system deps — cached across builds, only re-downloads if
# build-essential itself needs updating, not on every requirements.txt change
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y build-essential

# Copy requirements first (cache optimization — this layer only
# invalidates when requirements.txt actually changes)
COPY requirements.txt .

# --no-cache-dir removed: it conflicts with the cache mount below by
# telling pip not to persist anything to cache in the first place
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Copy app (including start.sh)
COPY . .

# Make startup script executable
RUN chmod +x start.sh

EXPOSE 8000

CMD ["./start.sh"]