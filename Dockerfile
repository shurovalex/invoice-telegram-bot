# Invoice Collection Bot - Production Dockerfile
# Optimized for Railway, Render, Fly.io, and other container platforms

FROM python:3.11-slim

# =============================================================================
# ENVIRONMENT CONFIGURATION
# =============================================================================
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONFAULTHANDLER=1 \
    # Application settings
    APP_HOME=/app \
    TEMP_DIR=/tmp/invoice_bot \
    PORT=8080

# =============================================================================
# SYSTEM DEPENDENCIES
# =============================================================================
# Install Tesseract OCR, PDF tools, and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Tesseract OCR and language data
    tesseract-ocr \
    tesseract-ocr-eng \
    # PDF processing (poppler-utils provides pdftotext, pdfinfo, etc.)
    poppler-utils \
    # Image processing
    libmagic1 \
    # Build dependencies for Python packages
    gcc \
    g++ \
    libc6-dev \
    libffi-dev \
    libpq-dev \
    # Utilities
    curl \
    ca-certificates \
    # Cleanup to reduce image size
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Verify Tesseract installation
RUN tesseract --version && echo "Tesseract installed successfully"

# =============================================================================
# APPLICATION SETUP
# =============================================================================
# Create application directory
WORKDIR ${APP_HOME}

# Create temp directory with proper permissions
RUN mkdir -p ${TEMP_DIR} && chmod 777 ${TEMP_DIR}

# =============================================================================
# PYTHON DEPENDENCIES
# =============================================================================
# Copy requirements first for better Docker layer caching
COPY invoice_bot/requirements.txt .

# Upgrade pip and install dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    # Verify key installations
    python -c "import telegram; print(f'python-telegram-bot: {telegram.__version__}')" && \
    python -c "import flask; print(f'Flask: {flask.__version__}')" && \
    python -c "import pytesseract; print(f'pytesseract: {pytesseract.get_tesseract_version()}')"

# =============================================================================
# APPLICATION CODE
# =============================================================================
# Copy all application files
COPY . .

# List copied files for debugging
RUN echo "=== Application Files ===" && ls -la ${APP_HOME}

# =============================================================================
# SECURITY: CREATE NON-ROOT USER
# =============================================================================
# Create app user for running the application (security best practice)
RUN groupadd -r appgroup && \
    useradd -r -g appgroup -u 1000 -d ${APP_HOME} appuser && \
    chown -R appuser:appgroup ${APP_HOME} ${TEMP_DIR}

# Switch to non-root user
USER appuser

# =============================================================================
# HEALTH CHECK
# =============================================================================
# Health check to verify application is running
# Railway, Render, and other platforms use this for auto-restart
HEALTHCHECK --interval=30s \
            --timeout=10s \
            --start-period=60s \
            --retries=3 \
    CMD python -c "
import sys
import urllib.request
try:
    port = __import__('os').environ.get('PORT', '8080')
    with urllib.request.urlopen(f'http://localhost:{port}/', timeout=5) as resp:
        if resp.status == 200:
            sys.exit(0)
except Exception as e:
    print(f'Health check failed: {e}')
    sys.exit(1)
" || exit 1

# =============================================================================
# EXPOSE PORT
# =============================================================================
# Note: Railway, Render, etc. set the PORT environment variable
# We expose as documentation, but the platform may override
EXPOSE ${PORT}

# =============================================================================
# STARTUP COMMAND
# =============================================================================
# Use exec form to ensure proper signal handling
# Gunicorn configuration optimized for Telegram bot webhooks:
# - workers: 2 (handle concurrent requests)
# - threads: 4 (handle I/O-bound operations)
# - timeout: 120s (allow time for document processing)
# - access-logfile: - (stdout for Railway/Render logs)
# - error-logfile: - (stderr for Railway/Render logs)
CMD exec gunicorn \
    --bind 0.0.0.0:${PORT} \
    --workers 2 \
    --threads 4 \
    --worker-class gthread \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    --enable-stdio-inheritance \
    invoice_bot.webhook_server:app
