# Monitoring & Logging Guide

## Overview

This guide covers monitoring, logging, and alerting strategies for the Invoice Collection Bot in production.

---

## Logging Strategy

### 1. Application Logging

The bot uses Python's built-in logging with structured output:

```python
# config.py - Logging configuration
import logging
import sys

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    level=getattr(logging, LOG_LEVEL),
    handlers=[
        logging.StreamHandler(sys.stdout),  # All platforms capture stdout
    ]
)
```

### 2. Log Levels

| Level | Use Case | Example |
|-------|----------|---------|
| `DEBUG` | Development only | Variable values, function entry/exit |
| `INFO` | Normal operations | User started conversation, document processed |
| `WARNING` | Recoverable issues | Failed OCR, retrying operation |
| `ERROR` | Failures | Exception caught, service unavailable |
| `CRITICAL` | System failure | Database down, can't start bot |

### 3. Structured Logging (Optional Enhancement)

For better parsing, use JSON logging:

```python
# Add to requirements.txt: python-json-logger>=2.0.0

import logging
from pythonjsonlogger import jsonlogger

logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter(
    '%(timestamp)s %(level)s %(name)s %(message)s'
)
logHandler.setFormatter(formatter)
logging.getLogger().addHandler(logHandler)
```

---

## Platform-Specific Logging

### Railway.app

**View Logs:**
```bash
# Real-time logs
railway logs --follow

# Last 100 lines
railway logs --tail 100

# Specific deployment
railway logs --deployment <deployment-id>
```

**Dashboard:**
- Project → Deployments → Click deployment → Logs tab

**Log Retention:**
- Free trial: Limited retention
- Paid plans: Extended retention
- Export: Use CLI or API for long-term storage

### Render.com

**View Logs:**
```bash
# Using Render CLI
render logs --service your-service-name

# Follow logs
render logs --service your-service-name --follow
```

**Dashboard:**
- Service → Logs tab

**Log Retention:**
- Free tier: 7 days
- Paid plans: 30+ days

### Fly.io

**View Logs:**
```bash
# Real-time logs
fly logs

# Follow
fly logs --follow

# Last N entries
fly logs --tail 100
```

**Log Retention:**
- 7 days by default
- Can export to external service

---

## Health Monitoring

### 1. Health Check Endpoint

Your bot includes a health endpoint at `GET /`:

```json
{
  "status": "ok",
  "service": "Invoice Collection Bot",
  "version": "1.0.0",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### 2. Enhanced Health Check

Add more detailed health information:

```python
# webhook_server.py - Enhanced health check

import psutil
import time

@app.route("/health", methods=["GET"])
def health():
    """Detailed health check with system metrics."""
    return jsonify({
        "status": "ok",
        "service": "Invoice Collection Bot",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": time.time() - start_time,
        "system": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage('/').percent
        },
        "webhook": {
            "url": config.WEBHOOK_URL,
            "path": config.WEBHOOK_PATH
        }
    })
```

### 3. External Health Monitoring

**Free Options:**

| Service | Check Interval | Features |
|---------|----------------|----------|
| **UptimeRobot** | 5 minutes (free) | HTTP, keyword, port monitoring |
| **Pingdom** | 1 minute (trial) | Detailed reporting |
| **StatusCake** | 5 minutes (free) | Multiple locations |
| **Freshping** | 1 minute (free) | 50 monitors |

**Setup with UptimeRobot:**

1. Sign up at [uptimerobot.com](https://uptimerobot.com)
2. Add New Monitor
3. Monitor Type: HTTP(s)
4. Friendly Name: Invoice Bot
5. URL: `https://your-app.com/`
6. Monitoring Interval: 5 minutes
7. Alert Contacts: Email, SMS, Telegram

---

## Error Tracking

### 1. Sentry Integration (Recommended)

Sentry provides comprehensive error tracking:

```python
# requirements.txt: sentry-sdk>=1.0.0

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

# Initialize Sentry
sentry_sdk.init(
    dsn="your-sentry-dsn",
    integrations=[FlaskIntegration()],
    traces_sample_rate=0.1,  # 10% of transactions
    profiles_sample_rate=0.1,
    environment="production",
    release="1.0.0"
)
```

**Pricing:**
- Free tier: 5,000 errors/month
- Paid: From $26/month

### 2. Rollbar Alternative

```python
# requirements.txt: rollbar>=0.16.0

import rollbar
import rollbar.contrib.flask

rollbar.init(
    'your-rollbar-token',
    'production',
    root=os.path.dirname(os.path.realpath(__file__)),
    allow_logging_basic_config=False
)
```

### 3. Custom Error Notifications

Send critical errors to Telegram:

```python
# error_handler.py

async def notify_admin(error_message: str):
    """Send error notification to admin."""
    admin_chat_id = config.ADMIN_CHAT_ID
    if admin_chat_id:
        await application.bot.send_message(
            chat_id=admin_chat_id,
            text=f"🚨 *Error Alert*\n\n```{error_message}```",
            parse_mode="Markdown"
        )
```

---

## Metrics & Analytics

### 1. Bot Usage Metrics

Track key metrics:

```python
# metrics.py

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List

@dataclass
class BotMetrics:
    total_users: int = 0
    active_conversations: int = 0
    documents_processed: int = 0
    invoices_generated: int = 0
    errors_count: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_users": self.total_users,
            "active_conversations": self.active_conversations,
            "documents_processed": self.documents_processed,
            "invoices_generated": self.invoices_generated,
            "errors_count": self.errors_count
        }

# Global metrics instance
metrics = BotMetrics()
```

### 2. Metrics Endpoint

```python
# webhook_server.py

@app.route("/metrics", methods=["GET"])
def get_metrics():
    """Get bot metrics."""
    return jsonify(metrics.to_dict())
```

### 3. Database Metrics Storage

Store metrics in PostgreSQL:

```sql
-- Create metrics table
CREATE TABLE bot_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metric_name VARCHAR(100),
    metric_value INTEGER,
    metadata JSONB
);

-- Create index for time-series queries
CREATE INDEX idx_metrics_timestamp ON bot_metrics(timestamp);
```

---

## Log Aggregation

### 1. Papertrail (Easy Setup)

```bash
# Railway/Render have Papertrail integrations
# Or use syslog in your app
```

### 2. LogDNA / Mezmo

```python
# Send logs to LogDNA
import logging
from logdna import LogDNAHandler

log = logging.getLogger('logdna')
log.setLevel(logging.INFO)

options = {
    'app': 'invoice-bot',
    'env': 'production',
    'index_meta': True
}

handler = LogDNAHandler('your-ingestion-key', options)
log.addHandler(handler)
```

### 3. CloudWatch (AWS)

If using AWS:
```python
import watchtower
import logging

logging.getLogger().addHandler(watchtower.CloudWatchLogHandler())
```

---

## Alerting Rules

### 1. Critical Alerts (Immediate)

| Condition | Action |
|-----------|--------|
| Bot not responding | Send Telegram alert |
| Webhook returns 5xx | Page admin |
| Database connection fails | Send email + Telegram |
| Memory usage > 90% | Send warning |

### 2. Warning Alerts (Daily Digest)

| Condition | Action |
|-----------|--------|
| Error rate > 1% | Include in daily report |
| Response time > 5s | Log for investigation |
| Disk usage > 80% | Send warning |

### 3. Telegram Alert Bot

Create a simple alert bot:

```python
# alerts.py

import os
import asyncio
from telegram import Bot

ALERT_BOT_TOKEN = os.getenv("ALERT_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

async def send_alert(message: str, level: str = "INFO"):
    """Send alert to admin via Telegram."""
    if not ALERT_BOT_TOKEN or not ADMIN_CHAT_ID:
        return
    
    emoji = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "❌", "CRITICAL": "🚨"}
    
    bot = Bot(token=ALERT_BOT_TOKEN)
    await bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"{emoji.get(level, 'ℹ️')} *{level}*\n\n{message}",
        parse_mode="Markdown"
    )

# Usage
asyncio.run(send_alert("High error rate detected", "WARNING"))
```

---

## Monitoring Dashboard

### 1. Simple Dashboard with Flask

```python
# dashboard.py

from flask import render_template_string

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Invoice Bot Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .metric { background: #f0f0f0; padding: 20px; margin: 10px 0; border-radius: 5px; }
        .ok { color: green; }
        .warning { color: orange; }
        .error { color: red; }
    </style>
</head>
<body>
    <h1>Invoice Bot Dashboard</h1>
    <div class="metric">
        <h2>Status: <span class="{{ 'ok' if health.status == 'ok' else 'error' }}">{{ health.status }}</span></h2>
    </div>
    <div class="metric">
        <h3>Metrics</h3>
        <p>Total Users: {{ metrics.total_users }}</p>
        <p>Documents Processed: {{ metrics.documents_processed }}</p>
        <p>Invoices Generated: {{ metrics.invoices_generated }}</p>
        <p>Errors: {{ metrics.errors_count }}</p>
    </div>
</body>
</html>
"""

@app.route("/dashboard", methods=["GET"])
def dashboard():
    """Simple monitoring dashboard."""
    return render_template_string(
        DASHBOARD_TEMPLATE,
        health=health(),
        metrics=metrics
    )
```

### 2. Grafana (Advanced)

For advanced monitoring with Grafana:

1. Deploy Prometheus + Grafana
2. Export metrics in Prometheus format
3. Create dashboards

```python
# prometheus_metrics.py

from prometheus_client import Counter, Histogram, generate_latest

# Define metrics
DOCUMENTS_PROCESSED = Counter('documents_processed_total', 'Total documents processed')
INVOICES_GENERATED = Counter('invoices_generated_total', 'Total invoices generated')
REQUEST_DURATION = Histogram('request_duration_seconds', 'Request duration')

@app.route("/metrics/prometheus")
def prometheus_metrics():
    """Prometheus metrics endpoint."""
    return generate_latest()
```

---

## Backup & Recovery

### 1. Database Backups

**Railway PostgreSQL:**
- Automatic daily backups
- Point-in-time recovery
- Manual backup via dashboard

**Render PostgreSQL:**
- Daily backups (paid plans)
- Manual backups available

**Self-managed:**
```bash
# Backup script
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql
```

### 2. Configuration Backups

```bash
# Export environment variables
railway variables > env_backup.txt

# Or use platform CLI
render env export --service your-service
```

---

## Checklist

### Pre-Launch

- [ ] Logging configured with appropriate level
- [ ] Health check endpoint working
- [ ] Error tracking (Sentry) configured
- [ ] External monitoring (UptimeRobot) set up
- [ ] Admin alerts configured
- [ ] Metrics collection implemented

### Post-Launch

- [ ] Verify logs are being captured
- [ ] Test alert notifications
- [ ] Set up log retention policy
- [ ] Create runbook for common issues
- [ ] Schedule regular backup verification

---

## Quick Commands Reference

```bash
# View logs
railway logs --follow          # Railway
render logs --follow           # Render
fly logs                       # Fly.io

# Health check
curl https://your-app.com/
curl https://your-app.com/health

# Metrics
curl https://your-app.com/metrics

# Webhook info
curl https://your-app.com/webhook-info
```

---

## Resources

- [Sentry Documentation](https://docs.sentry.io/)
- [UptimeRobot](https://uptimerobot.com/)
- [Prometheus Monitoring](https://prometheus.io/)
- [Grafana Dashboards](https://grafana.com/)
