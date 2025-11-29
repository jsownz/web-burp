# Multi-stage build for smaller final image
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /build

# Install system dependencies needed for mitmproxy and other packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt


# Final stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user first
RUN useradd -m -u 1000 burp

# Copy Python packages from builder and set ownership
COPY --from=builder --chown=burp:burp /root/.local /home/burp/.local

# Copy application code
COPY --chown=burp:burp . .

# Create certificates directory with proper ownership
RUN mkdir -p /app/certs && chown burp:burp /app/certs

# Create mitmproxy config directory and config file
# RUN mkdir -p /home/burp/.mitmproxy && \
#     echo "# Mitmproxy configuration" > /home/burp/.mitmproxy/config.yaml && \
#     echo "block_global: false" >> /home/burp/.mitmproxy/config.yaml && \
#     chown -R burp:burp /home/burp/.mitmproxy

# Make sure scripts in .local are usable
ENV PATH=/home/burp/.local/bin:$PATH

# Expose Flask port
EXPOSE 5000

# Expose proxy port (for future use)
EXPOSE 8080

# Switch to non-root user
USER burp

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/health')" || exit 1

# Use gunicorn with gevent worker for WebSocket support (compatible with mitmproxy)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "gevent", "--workers", "1", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "app:create_app()"]
