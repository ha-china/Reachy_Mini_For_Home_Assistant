# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    portaudio19-dev \
    build-essential \
    libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Install the package
RUN pip install -e .

# Expose the ESPHome API port
EXPOSE 6053

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command - can be overridden by Hugging Face Spaces
CMD ["python", "-m", "reachy_mini_ha_voice", "--name", "ReachyMini"]