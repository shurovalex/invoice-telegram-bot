# Webhook Setup Guide for Telegram Bot

## Overview

This guide covers webhook configuration for the Invoice Collection Bot on various deployment platforms.

---

## How Telegram Webhooks Work

```
┌─────────────┐     HTTPS POST      ┌─────────────────┐
│   Telegram  │ ──────────────────> │  Your Server    │
│   Servers   │    (webhook)        │  (Railway/etc)  │
│             │ <────────────────── │                 │
└─────────────┘     Response        └─────────────────┘
```

1. User sends message to your bot
2. Telegram servers POST to your webhook URL
3. Your server processes the update
4. Your server responds with HTTP 200

---

## Webhook Requirements

| Requirement | Details |
|-------------|---------|
| **HTTPS** | Required - Telegram only accepts HTTPS webhooks |
| **Valid Certificate** | Must be from trusted CA (Let's Encrypt OK) |
| **Port** | 443, 80, 88, or 8443 |
| **Response Time** | Must respond within 60 seconds |
| **IP Address** | Must be publicly accessible |

---

## Webhook Endpoints

Your bot provides these webhook management endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/webhook` | POST | Receives Telegram updates |
| `/set-webhook` | GET | Sets webhook with Telegram |
| `/delete-webhook` | GET | Removes webhook (use polling) |
| `/webhook-info` | GET | Shows current webhook status |

---

## Platform-Specific Setup

### Railway.app

#### 1. Get Your App URL

After deployment, Railway assigns a URL:
```
https://your-project-name.up.railway.app
```

Find it in: Dashboard → Your Service → Settings → Public Domain

#### 2. Set Environment Variables

```
BOT_TOKEN=your_bot_token
WEBHOOK_URL=https://your-project.up.railway.app
WEBHOOK_PATH=/webhook
```

#### 3. Webhook Auto-Configuration

The bot automatically sets the webhook on startup via `init_webhook()` in `webhook_server.py`.

#### 4. Manual Webhook Setup (if needed)

```bash
# Set webhook
curl https://your-app.up.railway.app/set-webhook

# Expected response:
# {"status": "ok", "message": "Webhook set to https://.../webhook"}
```

#### 5. Verify Webhook

```bash
curl https://your-app.up.railway.app/webhook-info
```

Expected response:
```json
{
  "status": "ok",
  "webhook_info": {
    "url": "https://your-app.up.railway.app/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0,
    "ip_address": "...",
    "last_error_date": null,
    "last_error_message": null,
    "max_connections": 40,
    "allowed_updates": null
  }
}
```

---

### Render.com

#### 1. Get Your App URL

```
https://your-service-name.onrender.com
```

#### 2. Set Environment Variables

In Render Dashboard → Your Service → Environment:
```
BOT_TOKEN=your_bot_token
WEBHOOK_URL=https://your-service.onrender.com
WEBHOOK_PATH=/webhook
```

#### 3. Important: Prevent Sleeping (Free Tier)

Free tier web services sleep after 15 minutes of inactivity. For a bot, this causes delays.

**Solutions:**

**Option A: Upgrade to Starter ($7/month)**
- Always-on, no sleeping

**Option B: Use Cron Job to Keep Alive**

Create `keep_alive.py`:
```python
import requests
import os

url = os.getenv("WEBHOOK_URL")
if url:
    try:
        requests.get(f"{url}/", timeout=10)
        print("Keep-alive ping sent")
    except Exception as e:
        print(f"Keep-alive failed: {e}")
```

Add to Render as a Cron Job (every 10 minutes):
```
*/10 * * * * python keep_alive.py
```

**Option C: Use UptimeRobot**
- Free monitoring service
- Pings your endpoint every 5 minutes
- Keeps service awake

---

### Fly.io

#### 1. Deploy and Get URL

```bash
fly deploy
fly status
```

Your URL will be:
```
https://your-app-name.fly.dev
```

#### 2. Set Secrets

```bash
fly secrets set BOT_TOKEN=your_bot_token
fly secrets set WEBHOOK_URL=https://your-app-name.fly.dev
```

#### 3. Verify Webhook

```bash
fly logs
```

---

## Webhook vs Polling Comparison

| Feature | Webhook | Polling |
|---------|---------|---------|
| **Latency** | Instant | 1-30 seconds delay |
| **Resource Usage** | Low (event-driven) | High (constant requests) |
| **Server Required** | Yes (HTTPS endpoint) | No (can run locally) |
| **Complexity** | Higher (SSL, deployment) | Lower (just run script) |
| **Scalability** | Excellent | Limited |
| **Cost** | Hosting required | Can be free (local) |

**Recommendation:** Use webhooks for production, polling for development.

---

## Switching to Polling (Development)

If you need to run locally or avoid webhooks:

### 1. Delete Webhook

```bash
curl https://your-app.up.railway.app/delete-webhook
```

### 2. Modify bot.py for Polling

```python
# bot.py - change main() function

def main():
    """Run the bot with polling (for development)."""
    bot = InvoiceBot()
    application = bot.get_application()
    
    # Delete any existing webhook
    application.bot.delete_webhook()
    
    # Run with polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)
```

### 3. Run Locally

```bash
python bot.py
```

---

## Webhook Security

### 1. IP Whitelisting (Optional)

Telegram webhook requests come from these IP ranges:
- `149.154.160.0/20`
- `91.108.4.0/22`

You can filter requests by IP for added security.

### 2. Secret Token

Set a secret token to verify requests:

```python
# In webhook_server.py
application.bot.set_webhook(
    url=webhook_url,
    secret_token="your-secret-token"
)

# Verify in webhook handler
if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != expected_token:
    return jsonify({"status": "unauthorized"}), 401
```

---

## Troubleshooting

### Issue: Webhook not receiving updates

**Checklist:**

1. **Verify webhook is set:**
```bash
curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo
```

2. **Check URL is correct:**
```bash
# Should match your deployed app URL
echo $WEBHOOK_URL
```

3. **Test endpoint manually:**
```bash
curl -X POST https://your-app.com/webhook \
  -H "Content-Type: application/json" \
  -d '{"update_id": 123, "message": {"message_id": 1}}'
```

4. **Check server logs:**
```bash
# Railway
railway logs

# Render
# View in dashboard or use Render CLI

# Fly.io
fly logs
```

### Issue: Certificate errors

**Solution:** Ensure your platform provides valid SSL certificates. All recommended platforms (Railway, Render, Fly.io) handle this automatically.

### Issue: Timeout errors

**Causes:**
- Document processing takes too long
- Server overloaded

**Solutions:**
- Increase Gunicorn timeout: `--timeout 180`
- Process documents asynchronously
- Use background workers (Celery + Redis)

### Issue: "Webhook was set by another process"

**Solution:**
```bash
# Delete and re-set webhook
curl https://your-app.com/delete-webhook
curl https://your-app.com/set-webhook
```

---

## Webhook Best Practices

1. **Always use HTTPS** - Telegram requires it
2. **Respond quickly** - Process updates asynchronously if needed
3. **Handle errors gracefully** - Don't crash on bad updates
4. **Monitor webhook status** - Check `/webhook-info` regularly
5. **Set max_connections** - Limit concurrent connections (default: 40)
6. **Use secret tokens** - Verify request authenticity
7. **Log everything** - For debugging and monitoring

---

## Quick Reference

```bash
# Set webhook manually
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-app.com/webhook"}'

# Get webhook info
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"

# Delete webhook
curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook"

# Test bot
curl "https://api.telegram.org/bot<TOKEN>/getMe"
```

---

## Resources

- [Telegram Bot API - Webhooks](https://core.telegram.org/bots/api#setwebhook)
- [python-telegram-bot Webhooks](https://docs.python-telegram-bot.org/en/stable/telegram.ext.application.html)
- [Railway Webhook Guide](https://docs.railway.app/deploy/webhooks)
