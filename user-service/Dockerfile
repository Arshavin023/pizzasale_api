FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y build-essential 
# && rm -rf /var/lib/apt/lists/*

# Copy requirements first (cache optimization)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy app (including start.sh)
COPY . .

# Make startup script executable
RUN chmod +x start.sh

EXPOSE 8000

CMD ["./start.sh"]