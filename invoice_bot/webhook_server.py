#!/usr/bin/env python3
"""
Webhook server for production deployment.
Uses Flask to receive updates from Telegram webhook.
"""

import logging
import os
from flask import Flask, request, jsonify
from telegram import Update

from invoice_bot.bot import InvoiceBot
from invoice_bot.config import Config

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# Initialize bot
config = Config()
bot = InvoiceBot()
application = bot.get_application()


@app.route("/", methods=["GET"])
def index():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "service": "Invoice Collection Bot",
        "version": "1.0.0"
    })


@app.route(config.WEBHOOK_PATH, methods=["POST"])
def webhook():
    """Handle incoming webhook updates from Telegram."""
    try:
        # Parse the update
        update = Update.de_json(request.get_json(force=True), application.bot)
        
        # Process the update
        application.process_update(update)
        
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/set-webhook", methods=["GET"])
def set_webhook():
    """Set the webhook URL with Telegram."""
    try:
        webhook_url = f"{config.WEBHOOK_URL}{config.WEBHOOK_PATH}"
        
        # Set webhook
        result = application.bot.set_webhook(url=webhook_url)
        
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
        logger.error(f"Error setting webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/delete-webhook", methods=["GET"])
def delete_webhook():
    """Delete the webhook and switch back to polling."""
    try:
        result = application.bot.delete_webhook()
        
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
        logger.error(f"Error deleting webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/webhook-info", methods=["GET"])
def webhook_info():
    """Get current webhook information."""
    try:
        info = application.bot.get_webhook_info()
        return jsonify({
            "status": "ok",
            "webhook_info": {
                "url": info.url,
                "has_custom_certificate": info.has_custom_certificate,
                "pending_update_count": info.pending_update_count,
                "ip_address": info.ip_address,
                "last_error_date": info.last_error_date,
                "last_error_message": info.last_error_message,
                "max_connections": info.max_connections,
                "allowed_updates": info.allowed_updates,
            }
        })
    except Exception as e:
        logger.error(f"Error getting webhook info: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def init_webhook():
    """Initialize the webhook on startup."""
    if config.is_webhook_mode:
        webhook_url = f"{config.WEBHOOK_URL}{config.WEBHOOK_PATH}"
        try:
            application.bot.set_webhook(url=webhook_url)
            logger.info(f"Webhook initialized: {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to initialize webhook: {e}")


if __name__ == "__main__":
    # Validate config
    config.validate()
    
    # Initialize webhook
    init_webhook()
    
    # Run Flask app
    port = int(os.environ.get("PORT", config.WEBHOOK_PORT))
    app.run(host="0.0.0.0", port=port, debug=False)
