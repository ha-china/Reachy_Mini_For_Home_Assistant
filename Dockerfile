# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy the application files (for display only)
COPY . .

# Expose the web port
EXPOSE 7860

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run simple HTTP server to display the index.html
CMD ["python", "-m", "http.server", "7860"]