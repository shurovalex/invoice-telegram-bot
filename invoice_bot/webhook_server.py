#!/usr/bin/env python3
"""
Webhook server for production deployment.
Uses Flask to receive updates from Telegram webhook.

SELF-HEALING ARCHITECTURE:
- Orchestrator tracks all tasks with timeouts
- Watchdog monitors for stuck operations
- Automatic recovery without human intervention
"""

import asyncio
import logging
import os
import threading
from flask import Flask, request, jsonify
from telegram import Update

from invoice_bot.bot import InvoiceBot
from invoice_bot.config import Config
from invoice_bot.orchestrator import Orchestrator
from invoice_bot.watchdog import Watchdog, HealthMonitor

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# Initialize bot and config
config = Config()
bot_instance = InvoiceBot()
application = bot_instance.get_application()

# Create a persistent event loop for async operations
_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

def run_async(coro):
    """Run async coroutine in sync context."""
    return _loop.run_until_complete(coro)


# Initialize the application
run_async(application.initialize())
run_async(application.start())

# Initialize Self-Healing Components
orchestrator = Orchestrator(application.bot)
watchdog = Watchdog(orchestrator, check_interval=5.0)
health_monitor = HealthMonitor(orchestrator, watchdog)

# Store orchestrator in app context for handlers to access
app.orchestrator = orchestrator


def start_watchdog_in_background():
    """Start the watchdog in a background thread with its own event loop."""
    def run_watchdog():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(watchdog.start())
            # Keep the watchdog running
            loop.run_until_complete(asyncio.Event().wait())
        except Exception as e:
            logger.error(f"Watchdog thread error: {e}")
        finally:
            loop.close()

    thread = threading.Thread(target=run_watchdog, daemon=True)
    thread.start()
    logger.info("Watchdog started in background thread")


# Start watchdog on module load
start_watchdog_in_background()


@app.route("/", methods=["GET"])
def index():
    """Health check endpoint with self-healing status."""
    health = health_monitor.get_full_status()
    return jsonify({
        "status": "ok" if health["healthy"] else "degraded",
        "service": "Invoice Collection Bot",
        "version": "2.0.0-self-healing",
        "self_healing": {
            "orchestrator_active": True,
            "watchdog_active": watchdog._running,
            "active_tasks": health["orchestrator"]["active_tasks"],
        }
    })


@app.route(config.WEBHOOK_PATH, methods=["POST"])
def webhook():
    """Handle incoming webhook updates from Telegram."""
    try:
        # Parse the update
        update = Update.de_json(request.get_json(force=True), application.bot)

        # Process the update asynchronously
        run_async(application.process_update(update))

        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        # Even on error, return 200 to prevent Telegram from retrying
        # The self-healing system will handle recovery
        return jsonify({"status": "error", "message": str(e)}), 200


@app.route("/set-webhook", methods=["GET"])
def set_webhook():
    """Set the webhook URL with Telegram."""
    try:
        webhook_url = f"{config.WEBHOOK_URL}{config.WEBHOOK_PATH}"

        # Set webhook asynchronously
        result = run_async(application.bot.set_webhook(url=webhook_url))

        if result:
            logger.info(f"Webhook set to: {webhook_url}")
            return jsonify({
                "status": "ok",
                "message": f"Webhook set to {webhook_url}"
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Failed to set webhook"
            }), 500

    except Exception as e:
        logger.error(f"Error setting webhook: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/delete-webhook", methods=["GET"])
def delete_webhook():
    """Delete the webhook and switch back to polling."""
    try:
        result = run_async(application.bot.delete_webhook())

        if result:
            logger.info("Webhook deleted")
            return jsonify({
                "status": "ok",
                "message": "Webhook deleted"
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Failed to delete webhook"
            }), 500

    except Exception as e:
        logger.error(f"Error deleting webhook: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/webhook-info", methods=["GET"])
def webhook_info():
    """Get current webhook information."""
    try:
        info = run_async(application.bot.get_webhook_info())
        return jsonify({
            "status": "ok",
            "webhook_info": {
                "url": info.url,
                "has_custom_certificate": info.has_custom_certificate,
                "pending_update_count": info.pending_update_count,
                "ip_address": info.ip_address,
                "last_error_date": str(info.last_error_date) if info.last_error_date else None,
                "last_error_message": info.last_error_message,
                "max_connections": info.max_connections,
                "allowed_updates": info.allowed_updates,
            }
        })
    except Exception as e:
        logger.error(f"Error getting webhook info: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    """Detailed health check endpoint for self-healing system."""
    try:
        status = health_monitor.get_full_status()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error getting health status: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/orchestrator/tasks", methods=["GET"])
def orchestrator_tasks():
    """Get all tracked tasks from orchestrator."""
    try:
        return jsonify(orchestrator.get_health_status())
    except Exception as e:
        logger.error(f"Error getting orchestrator tasks: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/watchdog/stats", methods=["GET"])
def watchdog_stats():
    """Get watchdog statistics."""
    try:
        return jsonify(watchdog.get_stats())
    except Exception as e:
        logger.error(f"Error getting watchdog stats: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    # Validate config
    config.validate()

    # Run Flask app
    port = int(os.environ.get("PORT", config.WEBHOOK_PORT))
    app.run(host="0.0.0.0", port=port, debug=False)
