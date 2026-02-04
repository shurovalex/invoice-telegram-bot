# Render.com Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying the Invoice Collection Bot on Render.com - a great alternative with a free tier.

**Estimated Time:** 15-20 minutes  
**Estimated Cost:** $0-20/month (free tier available)

---

## Why Choose Render?

| Feature | Benefit |
|---------|---------|
| **Free Tier** | Perfect for testing and small projects |
| **Simple Deployment** | Git-based, minimal configuration |
| **Automatic HTTPS** | SSL certificates included |
| **PostgreSQL** | Free tier database (90 days) |
| **Good Documentation** | Clear guides and examples |

---

## Prerequisites

1. **GitHub/GitLab Account** - For code repository
2. **Render Account** - Sign up at [render.com](https://render.com)
3. **Telegram Bot Token** - From @BotFather
4. **VS Code with Claude Code** - Your development environment

---

## Step 1: Prepare Your Repository

### 1.1 Required Files

Ensure these files are in your repository:

```
invoice_bot/
├── bot.py                 # Main bot code
├── webhook_server.py      # Flask webhook server
├── config.py             # Configuration
├── requirements.txt      # Python dependencies
├── Dockerfile            # Container definition
├── render.yaml           # Render configuration
└── .env.example          # Environment template
```

### 1.2 Create render.yaml

Create `render.yaml` for Blueprint deployment:

```yaml
# Render Blueprint Configuration
services:
  # Web Service for the Bot
  - type: web
    name: invoice-bot
    runtime: docker
    plan: free  # Change to 'starter' for always-on
    dockerfilePath: ./Dockerfile
    envVars:
      - key: BOT_TOKEN
        sync: false  # Set in dashboard
      - key: WEBHOOK_URL
        sync: false  # Set after first deploy
      - key: WEBHOOK_PATH
        value: /webhook
      - key: PORT
        value: 10000  # Render default
      - key: LOG_LEVEL
        value: INFO
      - key: PYTHON_VERSION
        value: 3.11.0
    healthCheckPath: /
    autoDeploy: true

  # PostgreSQL Database (optional)
  - type: pserv
    name: invoice-bot-db
    runtime: docker
    plan: free  # 90-day free trial
    dockerfilePath: ./Dockerfile.db  # Optional custom DB setup
    disk:
      name: data
      mountPath: /var/lib/postgresql/data
      sizeGB: 1
```

**Alternative: Simple render.yaml (without database)**

```yaml
services:
  - type: web
    name: invoice-bot
    runtime: docker
    plan: free
    dockerfilePath: ./Dockerfile
    envVars:
      - key: BOT_TOKEN
        sync: false
      - key: WEBHOOK_URL
        sync: false
      - key: WEBHOOK_PATH
        value: /webhook
      - key: LOG_LEVEL
        value: INFO
    healthCheckPath: /
```

---

## Step 2: Create Render-Specific Dockerfile

Render works well with the standard Dockerfile, but here's a Render-optimized version:

```dockerfile
# Render-optimized Dockerfile
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create temp directory
RUN mkdir -p /tmp/invoice_bot && chmod 777 /tmp/invoice_bot

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port (Render sets PORT env var)
EXPOSE 10000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:10000/')" || exit 1

# Start command
CMD gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 webhook_server:app
```

**Note:** On Render free tier, use `--workers 1` to save memory.

---

## Step 3: Deploy to Render

### Option A: Deploy via Blueprint (Recommended)

1. **Push code to GitHub**:
```bash
git add .
git commit -m "Add Render configuration"
git push origin main
```

2. **In Render Dashboard**:
   - Click "New +" → "Blueprint"
   - Connect your GitHub repository
   - Render reads `render.yaml` and creates services
   - Click "Apply"

3. **Set Environment Variables**:
   - Go to your web service → Environment
   - Add `BOT_TOKEN` (from @BotFather)
   - Save changes

4. **Deploy**:
   - Render automatically deploys
   - Wait for build to complete

### Option B: Manual Web Service Creation

1. **In Render Dashboard**:
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Configure:
     - **Name**: `invoice-bot`
     - **Runtime**: Docker
     - **Plan**: Free (or Starter for always-on)
   - Click "Create Web Service"

2. **Set Environment Variables**:
   - Service → Environment
   - Add:
     - `BOT_TOKEN` = your_bot_token
     - `WEBHOOK_PATH` = /webhook
     - `LOG_LEVEL` = INFO

3. **Deploy**:
   - Render builds and deploys automatically

---

## Step 4: Configure Webhook URL

### 4.1 Get Your Render URL

After deployment, find your URL:
- Format: `https://invoice-bot-xxx.onrender.com`
- Location: Dashboard → Your Service → URL

### 4.2 Update Environment Variables

1. Go to Service → Environment
2. Add: `WEBHOOK_URL` = `https://your-service.onrender.com`
3. Save (triggers redeploy)

### 4.3 Set Webhook

After redeploy completes:

```bash
# Set webhook
curl https://your-service.onrender.com/set-webhook

# Verify
curl https://your-service.onrender.com/webhook-info
```

---

## Step 5: Add PostgreSQL Database (Optional)

### 5.1 Create Database

1. Dashboard → New → PostgreSQL
2. Name: `invoice-bot-db`
3. Plan: Free (or paid for persistence)
4. Click "Create Database"

### 5.2 Connect Database

Render automatically adds `DATABASE_URL` to your web service environment.

### 5.3 Update Code

Ensure your `config.py` uses `DATABASE_URL`:

```python
DATABASE_URL = os.getenv("DATABASE_URL")
```

---

## Step 6: Free Tier Limitations & Solutions

### 6.1 Web Service Sleeping (Free Tier)

**Problem:** Free web services sleep after 15 minutes of inactivity.

**Impact:** First request after sleep has ~30s delay (cold start).

**Solutions:**

#### Option 1: Upgrade to Starter ($7/month)
- Always-on, no sleeping
- Best for production

#### Option 2: Keep-Alive Ping (Free)

Use an external service to ping your bot:

**UptimeRobot (Free):**
1. Sign up at [uptimerobot.com](https://uptimerobot.com)
2. Add monitor:
   - Type: HTTP(s)
   - URL: `https://your-service.onrender.com/`
   - Interval: 5 minutes
3. This keeps your service awake

**Cron-Job.org (Free):**
1. Sign up at [cron-job.org](https://cron-job.org)
2. Create job:
   - URL: `https://your-service.onrender.com/`
   - Schedule: Every 5 minutes

#### Option 3: Self-Keep-Alive (Not Recommended)

Add to your code (not recommended for free tier - wastes resources):

```python
# keep_alive.py
import requests
import threading
import time
import os

def ping_self():
    """Ping self to prevent sleeping."""
    while True:
        try:
            url = os.getenv("WEBHOOK_URL")
            if url:
                requests.get(f"{url}/", timeout=10)
        except:
            pass
        time.sleep(600)  # Every 10 minutes

# Start in background
threading.Thread(target=ping_self, daemon=True).start()
```

### 6.2 PostgreSQL 90-Day Limit (Free Tier)

**Problem:** Free PostgreSQL expires after 90 days.

**Solutions:**

#### Option 1: Upgrade Database ($7-15/month)
- Keeps data permanently
- Backups included

#### Option 2: Export/Import Before Expiry

```bash
# Before expiry, export data
pg_dump $DATABASE_URL > backup.sql

# Create new free database
# Import data
psql $NEW_DATABASE_URL < backup.sql
```

#### Option 3: Use External Database

Use Railway PostgreSQL or Supabase (free tier):

```bash
# Supabase free PostgreSQL
# Sign up at supabase.com
# Get connection string
# Set as DATABASE_URL in Render
```

---

## Step 7: Monitoring & Logs

### 7.1 View Logs

**In Dashboard:**
- Service → Logs tab

**Using Render CLI:**
```bash
# Install CLI
npm install -g @render/cli

# Login
render login

# View logs
render logs --service your-service-name

# Follow logs
render logs --service your-service-name --follow
```

### 7.2 Health Checks

Render automatically uses your health check endpoint (`/`).

Monitor health:
```bash
curl https://your-service.onrender.com/
```

### 7.3 Set Up Alerts

Use external monitoring (UptimeRobot, Pingdom) for alerts.

---

## Step 8: Custom Domain (Optional)

1. **In Dashboard**:
   - Service → Settings → Custom Domain
   - Add your domain: `bot.yourdomain.com`

2. **Configure DNS**:
   - Add CNAME record pointing to Render URL
   - Wait for SSL certificate provisioning

3. **Update Webhook URL**:
   - Change `WEBHOOK_URL` to your custom domain
   - Visit `/set-webhook` to update

---

## Troubleshooting

### Issue: Build fails

**Check:**
```bash
# Test locally
docker build -t invoice-bot .
```

**Common fixes:**
- Ensure `requirements.txt` has no syntax errors
- Check Dockerfile syntax
- Verify all files are committed to Git

### Issue: Service won't start

**Check logs:**
```
Dashboard → Service → Logs
```

**Common issues:**
- Missing `BOT_TOKEN`
- Port not binding to `$PORT`
- Import errors in code

### Issue: Webhook not working

**Checklist:**
1. Verify `WEBHOOK_URL` is set correctly
2. Check webhook info: `/webhook-info`
3. Ensure HTTPS is working
4. Check Telegram bot token is valid

### Issue: Out of memory (Free Tier)

**Solutions:**
- Reduce Gunicorn workers to 1
- Optimize code memory usage
- Upgrade to Starter plan (512MB RAM)

---

## Pricing Summary

| Plan | Cost | Features |
|------|------|----------|
| **Free** | $0 | Web service sleeps, 90-day PostgreSQL |
| **Starter** | $7/mo | Always-on, 512MB RAM |
| **Standard** | $25/mo | 2GB RAM, more resources |
| **PostgreSQL** | $7-15/mo | Persistent database |

**Typical Production Setup:**
- Starter Web Service: $7/month
- Starter PostgreSQL: $7/month
- **Total: $14/month**

---

## Migration from Free to Paid

1. **Upgrade Web Service**:
   - Dashboard → Service → Settings → Plan
   - Select "Starter"
   - Immediate upgrade, no downtime

2. **Upgrade Database** (if needed):
   - Dashboard → PostgreSQL → Settings
   - Select paid plan
   - Follow migration instructions

---

## Comparison: Render vs Railway

| Feature | Render | Railway |
|---------|--------|---------|
| **Free Tier** | ✅ Yes (with limits) | ❌ No (but $500 trial) |
| **Always-On Free** | ❌ No | N/A |
| **Ease of Use** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Pricing** | $7-20/mo | $5-15/mo |
| **Database** | 90-day free | Included |
| **Best For** | Testing, budget | Production, simplicity |

---

## Quick Reference

```bash
# Render CLI commands
render login                    # Login
render services                 # List services
render logs --service name      # View logs
render env --service name       # List env vars
render deploy --service name    # Manual deploy

# Useful curl commands
curl https://your-app.onrender.com/
curl https://your-app.onrender.com/set-webhook
curl https://your-app.onrender.com/webhook-info
```

---

## Next Steps

1. ✅ Deploy to Render
2. ✅ Test bot with `/start`
3. ✅ Set up keep-alive (free tier) or upgrade
4. ✅ Configure monitoring
5. ✅ Add database (optional)
6. ✅ Set up custom domain (optional)

---

## Resources

- [Render Documentation](https://render.com/docs)
- [Render Blueprint Spec](https://render.com/docs/blueprint-spec)
- [Render Pricing](https://render.com/pricing)
- [UptimeRobot](https://uptimerobot.com) - Free keep-alive service
