# Quick Start - Invoice Bot Deployment

## 🚀 Deploy in 5 Minutes

This is the fastest path to deploy your Invoice Collection Bot.

---

## Recommended: Railway.app (Primary)

### Step 1: Prepare (2 minutes)

```bash
# 1. Ensure files are ready
ls -la
# Should show: bot.py, webhook_server.py, requirements.txt, Dockerfile

# 2. Commit to GitHub
git add .
git commit -m "Ready for deployment"
git push origin main
```

### Step 2: Deploy (3 minutes)

1. Go to [railway.app](https://railway.app) → Sign up with GitHub
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your repository
4. Railway auto-detects Dockerfile and deploys

### Step 3: Configure (1 minute)

1. In Railway Dashboard → Your Project → **Variables**
2. Add:
   - `BOT_TOKEN` = your token from @BotFather
   - `WEBHOOK_URL` = your Railway app URL (shown in dashboard)
3. Railway redeploys automatically

### Step 4: Test (30 seconds)

```bash
# Set webhook
curl https://your-app.up.railway.app/set-webhook

# Test bot in Telegram
# Send: /start
```

✅ **Done!** Your bot is live.

---

## Alternative: Render.com (Free Tier)

Use this if you need a **free tier** to start.

### Step 1: Add render.yaml

Create `render.yaml` in your repo:

```yaml
services:
  - type: web
    name: invoice-bot
    runtime: docker
    plan: free
    envVars:
      - key: BOT_TOKEN
        sync: false
      - key: WEBHOOK_PATH
        value: /webhook
```

### Step 2: Deploy

1. Go to [render.com](https://render.com) → Sign up
2. Click **"New +"** → **"Blueprint"**
3. Connect GitHub repo
4. Click **"Apply"**

### Step 3: Set Token

1. Dashboard → Your Service → **Environment**
2. Add `BOT_TOKEN`
3. Save (auto-redeploys)

### Step 4: Keep Alive (Free Tier)

Free tier sleeps after 15 min. Use UptimeRobot to keep it awake:

1. Go to [uptimerobot.com](https://uptimerobot.com)
2. Add monitor for your Render URL
3. Set interval to 5 minutes

✅ **Done!** Your bot stays awake for free.

---

## Environment Variables

| Variable | Required | Example |
|----------|----------|---------|
| `BOT_TOKEN` | ✅ Yes | `123456:ABCdef...` |
| `WEBHOOK_URL` | ✅ Yes | `https://your-app.com` |
| `WEBHOOK_PATH` | ❌ No | `/webhook` (default) |
| `LOG_LEVEL` | ❌ No | `INFO` (default) |

---

## Testing Your Bot

```bash
# 1. Health check
curl https://your-app.com/

# 2. Webhook info
curl https://your-app.com/webhook-info

# 3. Set webhook (if needed)
curl https://your-app.com/set-webhook

# 4. Test in Telegram
# Open your bot, send /start
```

---

## Common Issues

| Issue | Fix |
|-------|-----|
| Bot not responding | Check `BOT_TOKEN`, visit `/set-webhook` |
| Build fails | Check Dockerfile, requirements.txt |
| Free tier sleeps | Use UptimeRobot ping |
| Memory errors | Reduce Gunicorn workers to 1 |

---

## Costs

| Platform | Free Tier | Production Cost |
|----------|-----------|-----------------|
| **Railway** | $500 credits | $5-15/month |
| **Render** | Yes (sleeps) | $7-20/month |
| **Fly.io** | Yes (generous) | $0-10/month |

---

## Next Steps

- 📖 Read `deployment_guide_railway.md` for detailed Railway setup
- 📖 Read `deployment_guide_render.md` for detailed Render setup
- 📖 Read `webhook_setup.md` for webhook configuration
- 📖 Read `monitoring_logging.md` for monitoring setup

---

## Need Help?

1. Check logs: `railway logs` or Render Dashboard → Logs
2. Verify webhook: `/webhook-info` endpoint
3. Test locally: `python bot.py` (uses polling)
