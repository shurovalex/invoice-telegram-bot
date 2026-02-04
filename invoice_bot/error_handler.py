#!/usr/bin/env python3
"""
Error handling module for the Invoice Bot.
Ensures users always receive helpful feedback even when errors occur.
"""

import logging
import traceback
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Handle errors gracefully and provide user-friendly feedback."""
    
    def __init__(self, admin_chat_id: Optional[str] = None):
        self.admin_chat_id = admin_chat_id
    
    async def handle_validation_error(
        self, 
        update: Update, 
        field_name: str,
        custom_message: Optional[str] = None
    ) -> None:
        """
        Handle validation errors for user input.
        
        Args:
            update: The update object
            field_name: Name of the field that failed validation
            custom_message: Optional custom error message
        """
        if custom_message:
            message = f"❌ {custom_message}"
        else:
            message = f"❌ Invalid {field_name}. Please check your input and try again."
        
        await update.message.reply_text(message)
        logger.warning(f"Validation error for field '{field_name}' from user {update.effective_user.id}")
    
    async def handle_file_error(
        self,
        update: Update,
        error_type: str = "general",
        custom_message: Optional[str] = None
    ) -> None:
        """
        Handle file-related errors.
        
        Args:
            update: The update object
            error_type: Type of file error ('too_large', 'unsupported', 'corrupted', 'general')
            custom_message: Optional custom error message
        """
        messages = {
            "too_large": "❌ The file is too large. Please upload a file smaller than 20MB.",
            "unsupported": "❌ Unsupported file type. Please upload PDF, DOCX, or image files (JPG, PNG).",
            "corrupted": "❌ The file appears to be corrupted. Please try uploading again or use a different file.",
            "download_failed": "❌ Failed to download the file. Please try uploading again.",
            "general": "❌ An error occurred while processing your file. Please try again.",
        }
        
        message = custom_message or messages.get(error_type, messages["general"])
        await update.message.reply_text(message)
        
        logger.error(f"File error ({error_type}) for user {update.effective_user.id}")
    
    async def handle_processing_error(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        exception: Exception,
        operation: str = "processing"
    ) -> None:
        """
        Handle processing errors and notify admin if configured.
        
        Args:
            update: The update object
            context: The context object
            exception: The exception that occurred
            operation: Description of the operation that failed
        """
        user = update.effective_user
        error_details = traceback.format_exc()
        
        # Log the error
        logger.error(
            f"Processing error during {operation} for user {user.id} ({user.username}): {exception}\n{error_details}"
        )
        
        # Notify user
        await update.message.reply_text(
            "❌ An error occurred while processing your request. Please try again or type /cancel to start over."
        )
        
        # Notify admin if configured
        if self.admin_chat_id:
            try:
                await context.bot.send_message(
                    chat_id=self.admin_chat_id,
                    text=f"🚨 *Error Alert*\n\n"
                         f"User: {user.id} (@{user.username or 'N/A'})\n"
                         f"Operation: {operation}\n"
                         f"Error: {str(exception)[:200]}",
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"Failed to notify admin: {e}")
    
    async def handle_conversation_error(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        exception: Exception
    ) -> int:
        """
        Handle errors in conversation handlers.
        
        Args:
            update: The update object
            context: The context object
            exception: The exception that occurred
            
        Returns:
            ConversationHandler.END to end the conversation
        """
        user = update.effective_user if update.effective_user else None
        error_details = traceback.format_exc()
        
        logger.error(
            f"Conversation error for user {user.id if user else 'unknown'}: {exception}\n{error_details}"
        )
        
        # Try to notify user
        try:
            if update.effective_message:
                await update.effective_message.reply_text(
                    "❌ An unexpected error occurred. Your session has been reset. "
                    "Please type /start to begin again."
                )
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")
        
        # Clear user data
        context.user_data.clear()
        
        # Notify admin if configured
        if self.admin_chat_id and user:
            try:
                await context.bot.send_message(
                    chat_id=self.admin_chat_id,
                    text=f"🚨 *Conversation Error*\n\n"
                         f"User: {user.id} (@{user.username or 'N/A'})\n"
                         f"Error: {str(exception)[:200]}",
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"Failed to notify admin: {e}")
        
        # Import here to avoid circular dependency
        from telegram.ext import ConversationHandler
        return ConversationHandler.END
    
    async def handle_timeout_error(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """
        Handle conversation timeout.
        
        Args:
            update: The update object
            context: The context object
            
        Returns:
            ConversationHandler.END to end the conversation
        """
        await update.message.reply_text(
            "⏱️ Your session has expired due to inactivity. Please type /start to begin again."
        )
        
        context.user_data.clear()
        
        from telegram.ext import ConversationHandler
        return ConversationHandler.END
    
    async def handle_network_error(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        exception: Exception
    ) -> None:
        """
        Handle network-related errors.
        
        Args:
            update: The update object
            context: The context object
            exception: The network exception
        """
        logger.error(f"Network error: {exception}")
        
        await update.message.reply_text(
            "🌐 A network error occurred. Please check your connection and try again."
        )
    
    async def handle_rate_limit(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handle rate limiting from Telegram API.
        
        Args:
            update: The update object
            context: The context object
        """
        await update.message.reply_text(
            "⏳ Please wait a moment before sending another message."
        )
        
        logger.warning(f"Rate limit hit for user {update.effective_user.id}")


class UserFeedback:
    """Helper class for providing consistent user feedback."""
    
    @staticmethod
    async def send_processing_message(update: Update, text: str = "Processing...") -> None:
        """Send a processing message to the user."""
        await update.message.reply_text(f"⏳ {text}")
    
    @staticmethod
    async def send_success_message(update: Update, text: str = "Success!") -> None:
        """Send a success message to the user."""
        await update.message.reply_text(f"✅ {text}")
    
    @staticmethod
    async def send_error_message(update: Update, text: str = "An error occurred.") -> None:
        """Send an error message to the user."""
        await update.message.reply_text(f"❌ {text}")
    
    @staticmethod
    async def send_info_message(update: Update, text: str) -> None:
        """Send an informational message to the user."""
        await update.message.reply_text(f"ℹ️ {text}")
    
    @staticmethod
    async def send_warning_message(update: Update, text: str) -> None:
        """Send a warning message to the user."""
        await update.message.reply_text(f"⚠️ {text}")
    
    @staticmethod
    async def edit_to_success(message, text: str = "Success!") -> None:
        """Edit a message to show success."""
        await message.edit_text(f"✅ {text}")
    
    @staticmethod
    async def edit_to_error(message, text: str = "An error occurred.") -> None:
        """Edit a message to show error."""
        await message.edit_text(f"❌ {text}")


# Global error handler for the application
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Global error handler for the application.
    This should be registered with application.add_error_handler().
    
    Args:
        update: The update that caused the error
        context: The context object
    """
    logger.error(f"Update {update} caused error: {context.error}")
    
    # Get traceback
    error_traceback = traceback.format_exc()
    logger.error(f"Traceback: {error_traceback}")
    
    # Try to notify user
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ An unexpected error occurred. Please try again or type /start to restart."
            )
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")
