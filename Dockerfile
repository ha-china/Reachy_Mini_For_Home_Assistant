# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for static file serving
RUN apt-get update && apt-get install -y \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install simple HTTP server
RUN pip install --no-cache-dir fastapi uvicorn

# Copy the application files (for display only)
COPY . .

# Expose the web port
EXPOSE 7860

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run simple web server to display the index.html
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]