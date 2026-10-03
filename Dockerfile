# Dockerfile for Voice Journal
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y     ffmpeg     libsndfile1     && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 voicejournal
USER voicejournal

# Copy requirements and install Python dependencies
COPY --chown=voicejournal:voicejournal requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY --chown=voicejournal:voicejournal . .

# Create necessary directories
RUN mkdir -p /app/logs /app/data

# Expose ports
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3     CMD curl -f http://localhost:5000/health || exit 1

# Default command (will be overridden by docker-compose)
CMD ["python", "-m", "voice_journal.daemon"]
