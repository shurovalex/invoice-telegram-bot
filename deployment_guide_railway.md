# Railway.app Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying the Invoice Collection Bot on Railway.app - the recommended platform for its simplicity and developer experience.

**Estimated Time:** 15-20 minutes  
**Estimated Cost:** $5-15/month (after $500 free trial)

---

## Prerequisites

1. **GitHub Account** - For code repository
2. **Railway Account** - Sign up at [railway.app](https://railway.app)
3. **Telegram Bot Token** - From @BotFather
4. **VS Code with Claude Code** - Your development environment

---

## Step 1: Prepare Your Repository

### 1.1 Create Project Structure

Ensure your project has this structure:

```
invoice_bot/
├── bot.py                 # Main bot code
├── webhook_server.py      # Flask webhook server
├── config.py             # Configuration
├── requirements.txt      # Python dependencies
├── Dockerfile            # Container definition
├── railway.json          # Railway configuration
├── .env.example          # Environment template
└── .gitignore           # Git ignore file
```

### 1.2 Update requirements.txt

Ensure your `requirements.txt` includes:

```txt
# Core
python-telegram-bot>=20.0
flask>=2.0.0
gunicorn>=20.1.0
python-dotenv>=0.19.0

# Document Processing
PyPDF2>=3.0.0
pdfplumber>=0.9.0
pdf2image>=1.16.0
python-docx>=0.8.11
pytesseract>=0.3.10
Pillow>=9.0.0

# PDF Generation
reportlab>=3.6.0

# Database (optional - for persistence)
psycopg2-binary>=2.9.0
sqlalchemy>=1.4.0
```

### 1.3 Create .gitignore

```gitignore
# Environment
.env
.venv/
env/
venv/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Temporary files
tmp/
temp/
*.tmp
uploads/
downloads/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Railway
.railway/
```

---

## Step 2: Create Railway Configuration Files

### 2.1 Create railway.json

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile"
  },
  "deploy": {
    "startCommand": "gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 webhook_server:app",
    "healthcheckPath": "/",
    "healthcheckTimeout": 30,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### 2.2 Create nixpacks.toml (Alternative to Dockerfile)

If you prefer not to use Docker, create `nixpacks.toml`:

```toml
[phases.setup]
nixPkgs = ['python311', 'gcc', 'tesseract', 'poppler_utils']

[phases.install]
cmds = ['python -m venv --copies /opt/venv && . /opt/venv/bin/activate && pip install -r requirements.txt']

[phases.build]
cmds = ['echo "Build complete"']

[start]
cmd = 'gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 webhook_server:app'
```

---

## Step 3: Create Dockerfile

Create a production-ready Dockerfile:

```dockerfile
# Use Python 3.11 slim image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Tesseract OCR
    tesseract-ocr \
    tesseract-ocr-eng \
    # PDF processing
    poppler-utils \
    # Build dependencies
    gcc \
    g++ \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create temp directory for file processing
RUN mkdir -p /tmp/invoice_bot && chmod 777 /tmp/invoice_bot

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port (Railway sets PORT env var)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:${PORT:-8080}/')" || exit 1

# Start command (Railway provides PORT environment variable)
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 --access-logfile - --error-logfile - webhook_server:app
```

---

## Step 4: Deploy to Railway

### 4.1 Sign Up & Install CLI

1. **Sign up** at [railway.app](https://railway.app) (use GitHub login)
2. **Install Railway CLI** (optional but recommended):

```bash
# macOS/Linux
curl -fsSL https://railway.app/install.sh | sh

# Or using npm
npm install -g @railway/cli
```

### 4.2 Deploy via Web Dashboard (Easiest)

1. **Push code to GitHub**:
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/invoice_bot.git
git push -u origin main
```

2. **In Railway Dashboard**:
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository
   - Railway auto-detects Dockerfile and deploys

3. **Add Environment Variables**:
   - Go to your project → Variables tab
   - Add variables (see Section 5)

4. **Deploy**:
   - Railway automatically deploys on push
   - Or click "Deploy" in dashboard

### 4.3 Deploy via CLI (Alternative)

```bash
# Login
railway login

# Initialize project
railway init

# Add environment variables
railway variables set BOT_TOKEN="your_bot_token"
railway variables set WEBHOOK_URL="https://your-app.up.railway.app"

# Deploy
railway up

# Open in browser
railway open
```

---

## Step 5: Configure Environment Variables

### 5.1 Required Variables

In Railway Dashboard → Your Project → Variables:

| Variable | Value | Description |
|----------|-------|-------------|
| `BOT_TOKEN` | `123456789:ABCdef...` | From @BotFather |
| `WEBHOOK_URL` | `https://your-app.up.railway.app` | Your Railway app URL |
| `WEBHOOK_PATH` | `/webhook` | Webhook endpoint path |
| `PORT` | `8080` | Auto-set by Railway |

### 5.2 Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING) |
| `MAX_FILE_SIZE_MB` | `20` | Max upload size |
| `OCR_LANGUAGE` | `eng` | Tesseract OCR language |
| `DATABASE_URL` | - | PostgreSQL connection string |
| `ADMIN_CHAT_ID` | - | Admin notifications |

### 5.3 Get Your Railway App URL

After first deploy, Railway assigns a URL:
- Format: `https://your-project-name.up.railway.app`
- Find it in: Dashboard → Your Service → Settings → Public Domain

---

## Step 6: Set Up Webhook

### 6.1 Automatic Webhook Setup

The webhook is automatically set on startup via `init_webhook()` in `webhook_server.py`.

### 6.2 Manual Webhook Setup (if needed)

Visit these endpoints after deployment:

1. **Set webhook**:
```
GET https://your-app.up.railway.app/set-webhook
```

2. **Verify webhook**:
```
GET https://your-app.up.railway.app/webhook-info
```

3. **Delete webhook** (switch to polling):
```
GET https://your-app.up.railway.app/delete-webhook
```

### 6.3 Verify Bot is Working

1. Open Telegram
2. Find your bot
3. Send `/start`
4. Bot should respond with welcome message

---

## Step 7: Add PostgreSQL Database (Optional)

For persistent conversation storage:

### 7.1 Add Database in Railway

1. Dashboard → New → Database → Add PostgreSQL
2. Railway automatically adds `DATABASE_URL` to your environment

### 7.2 Update Code for Database

Update `config.py` to use database:

```python
# config.py - add database support
import os

class Config:
    # ... existing config ...
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    @property
    def has_database(self) -> bool:
        return self.DATABASE_URL is not None
```

---

## Step 8: Monitoring & Logs

### 8.1 View Logs

**In Dashboard:**
- Go to your project → Deployments → Click on deployment → Logs tab

**Via CLI:**
```bash
railway logs
```

**Real-time logs:**
```bash
railway logs --follow
```

### 8.2 Health Check Endpoint

Your bot has a health check at:
```
GET https://your-app.up.railway.app/
```

Expected response:
```json
{
  "status": "ok",
  "service": "Invoice Collection Bot",
  "version": "1.0.0"
}
```

### 8.3 Set Up Alerts (Optional)

Railway doesn't have built-in alerts, but you can:
- Use external monitoring (UptimeRobot, Pingdom)
- Check logs regularly
- Set up Telegram notifications for errors

---

## Step 9: Custom Domain (Optional)

### 9.1 Add Custom Domain

1. Dashboard → Your Service → Settings → Public Domain
2. Click "Custom Domain"
3. Enter your domain: `bot.yourdomain.com`
4. Follow DNS configuration instructions
5. Update `WEBHOOK_URL` environment variable
6. Revisit `/set-webhook` endpoint

---

## Step 10: Troubleshooting

### Common Issues

#### Issue: Bot not responding

**Check:**
```bash
# 1. Verify webhook is set
curl https://your-app.up.railway.app/webhook-info

# 2. Check logs
railway logs

# 3. Verify environment variables in dashboard
```

**Fix:**
- Re-set webhook: Visit `/set-webhook`
- Check `BOT_TOKEN` is correct
- Ensure `WEBHOOK_URL` matches your app URL

#### Issue: Document processing fails

**Check:**
```bash
# Verify Tesseract is installed
railway run tesseract --version
```

**Fix:**
- Ensure `tesseract-ocr` is in Dockerfile
- Check file size limits

#### Issue: Build fails

**Check:**
- Dockerfile syntax
- requirements.txt formatting

**Fix:**
```bash
# Test build locally
docker build -t invoice-bot .
```

#### Issue: High memory usage

**Fix:**
- Reduce Gunicorn workers in railway.json
- Add swap file (not recommended for production)
- Upgrade Railway plan

---

## Railway-Specific Tips

### 1. Deployment Triggers

Railway deploys automatically on:
- Git push to connected branch
- Manual "Deploy" click
- Environment variable changes

### 2. Rollbacks

To rollback:
1. Dashboard → Deployments
2. Find previous working deployment
3. Click "Deploy" on that version

### 3. Environment Branches

Create separate environments:
- `main` branch → Production
- `develop` branch → Staging

### 4. Cost Optimization

- Start with $500 free trial
- Monitor usage in Billing section
- Set up usage alerts
- Consider Render free tier for development

---

## Quick Reference Commands

```bash
# Deploy latest
railway up

# View logs
railway logs --follow

# Open dashboard
railway open

# SSH into container (debugging)
railway connect

# Run command in container
railway run python --version

# List variables
railway variables

# Set variable
railway variables set KEY=value
```

---

## Next Steps

1. ✅ Deploy your bot
2. ✅ Test with `/start` command
3. ✅ Try uploading a document
4. ✅ Set up monitoring
5. ✅ Configure custom domain (optional)
6. ✅ Add database for persistence (optional)

---

## Support Resources

- **Railway Docs**: https://docs.railway.app
- **Railway Discord**: https://discord.gg/railway
- **Telegram Bot API**: https://core.telegram.org/bots/api
- **python-telegram-bot**: https://docs.python-telegram-bot.org
