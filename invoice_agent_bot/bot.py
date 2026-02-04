#!/usr/bin/env python3
"""
Invoice Agent Bot - Main Entry Point

A conversational AI-powered Telegram bot for creating professional invoices.
Supports document processing (PDF, images, DOCX) and natural conversation flow.

Usage:
    python bot.py

Environment Variables:
    TELEGRAM_BOT_TOKEN - Required. Get from @BotFather
    OPENAI_API_KEY - Required for AI features
    GEMINI_API_KEY - Optional fallback AI provider
"""

import asyncio
import signal
import sys
from contextlib import asynccontextmanager
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

from src.core.config import get_settings
from src.core.state import (
    initialize_conversations,
    shutdown_conversations,
    get_conversation_manager,
)
from src.services.ai_client import initialize_ai, shutdown_ai
from src.services.document_processor import get_document_processor
from src.services.invoice_generator import get_invoice_generator
from src.utils.storage import initialize_storage, shutdown_storage
from src.utils.logger import get_logger, configure_logging
from src.bot.handlers import (
    start_command,
    help_command,
    cancel_command,
    new_command,
    status_command,
    document_handler,
    text_message_handler,
    button_callback,
    error_handler,
)

# Configure logging
configure_logging()
logger = get_logger(__name__)

# Global application instance
_application: Optional[Application] = None
_shutdown_event: Optional[asyncio.Event] = None


async def initialize_services() -> bool:
    """
    Initialize all required services.
    
    Returns:
        bool: True if all services initialized successfully
    """
    settings = get_settings()
    logger.info("Initializing services...")
    
    try:
        # Initialize storage
        await initialize_storage()
        logger.info("✅ Storage initialized")
        
        # Initialize AI manager
        ai_initialized = await initialize_ai()
        if ai_initialized:
            logger.info("✅ AI services initialized")
        else:
            logger.warning("⚠️ AI services not available - bot will run in limited mode")
        
        # Initialize conversation manager
        await initialize_conversations()
        logger.info("✅ Conversation manager initialized")
        
        # Initialize document processor (lazy - no async init needed)
        get_document_processor()
        logger.info("✅ Document processor ready")
        
        # Initialize invoice generator (lazy - no async init needed)
        get_invoice_generator()
        logger.info("✅ Invoice generator ready")
        
        logger.info("All services initialized successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Service initialization failed: {e}")
        return False


async def shutdown_services() -> None:
    """Shutdown all services gracefully."""
    logger.info("Shutting down services...")
    
    try:
        await shutdown_conversations()
        logger.info("✅ Conversation manager shutdown")
    except Exception as e:
        logger.error(f"Error shutting down conversations: {e}")
    
    try:
        await shutdown_ai()
        logger.info("✅ AI services shutdown")
    except Exception as e:
        logger.error(f"Error shutting down AI: {e}")
    
    try:
        await shutdown_storage()
        logger.info("✅ Storage shutdown")
    except Exception as e:
        logger.error(f"Error shutting down storage: {e}")
    
    logger.info("All services shutdown complete")


def setup_handlers(application: Application) -> None:
    """
    Set up all bot handlers.
    
    Args:
        application: The Telegram application instance
    """
    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("new", new_command))
    application.add_handler(CommandHandler("status", status_command))
    
    # Callback query handler (for buttons)
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Document handler
    application.add_handler(
        MessageHandler(filters.Document.ALL, document_handler)
    )
    
    # Photo handler (for image uploads)
    application.add_handler(
        MessageHandler(filters.PHOTO, document_handler)
    )
    
    # Text message handler (for conversation flow)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler)
    )
    
    # Error handler
    application.add_error_handler(error_handler)
    
    logger.info("Bot handlers registered")


async def health_check() -> dict:
    """
    Perform health check on all services.
    
    Returns:
        dict: Health status of each service
    """
    from src.utils.storage import get_storage
    
    health = {
        "status": "healthy",
        "services": {},
    }
    
    # Check storage
    try:
        storage = await get_storage()
        storage_health = await storage.health_check()
        health["services"]["storage"] = storage_health
    except Exception as e:
        health["services"]["storage"] = {"status": "unhealthy", "error": str(e)}
        health["status"] = "degraded"
    
    # Check conversation manager
    try:
        manager = get_conversation_manager()
        stats = await manager.get_stats()
        health["services"]["conversations"] = {"status": "healthy", "stats": stats}
    except Exception as e:
        health["services"]["conversations"] = {"status": "unhealthy", "error": str(e)}
    
    return health


async def run_bot() -> None:
    """
    Main bot execution loop.
    
    Initializes services, sets up handlers, and runs the bot
    until shutdown signal is received.
    """
    global _application, _shutdown_event
    
    settings = get_settings()
    
    # Validate configuration
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set! Please configure your .env file.")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("Invoice Agent Bot Starting...")
    logger.info(f"Debug mode: {settings.debug_mode}")
    logger.info(f"Test mode: {settings.test_mode}")
    logger.info("=" * 60)
    
    # Initialize services
    if not await initialize_services():
        logger.error("Failed to initialize services. Exiting.")
        sys.exit(1)
    
    # Create application
    _application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .build()
    )
    
    # Set up handlers
    setup_handlers(_application)
    
    # Set up shutdown event
    _shutdown_event = asyncio.Event()
    
    # Define signal handlers
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, initiating shutdown...")
        _shutdown_event.set()
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start the bot
    await _application.initialize()
    await _application.start()
    await _application.updater.start_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )
    
    logger.info("🚀 Bot is running! Press Ctrl+C to stop.")
    
    # Wait for shutdown signal
    try:
        await _shutdown_event.wait()
    except asyncio.CancelledError:
        logger.info("Bot task cancelled")
    
    # Shutdown gracefully
    logger.info("Shutting down bot...")
    
    if _application.updater:
        await _application.updater.stop()
    
    await _application.stop()
    await _application.shutdown()
    
    await shutdown_services()
    
    logger.info("👋 Bot stopped. Goodbye!")


def main() -> None:
    """
    Entry point for the bot.
    
    Sets up the async event loop and runs the bot.
    """
    try:
        # Run the async main function
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
