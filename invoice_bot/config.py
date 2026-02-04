#!/usr/bin/env python3
"""
Configuration module for the Invoice Bot.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """Bot configuration settings."""
    
    # Telegram Bot Token (from environment variable)
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    
    # Webhook settings (optional - for production deployment)
    WEBHOOK_URL: Optional[str] = os.getenv("WEBHOOK_URL")
    WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8443"))
    WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "/webhook")
    
    # File storage
    TEMP_DIR: str = os.getenv("TEMP_DIR", "/tmp/invoice_bot")
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "20"))
    
    # Supported file types
    SUPPORTED_MIME_TYPES = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/jpeg",
        "image/png",
        "image/jpg",
    ]
    
    SUPPORTED_EXTENSIONS = [".pdf", ".docx", ".jpg", ".jpeg", ".png"]
    
    # OCR Settings
    OCR_LANGUAGE: str = os.getenv("OCR_LANGUAGE", "eng")
    
    # Invoice generation
    INVOICE_TEMPLATE_PATH: str = os.getenv("INVOICE_TEMPLATE_PATH", "templates/invoice_template.html")
    COMPANY_LOGO_PATH: Optional[str] = os.getenv("COMPANY_LOGO_PATH")
    
    # Database (optional - for persistent storage)
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Admin notifications
    ADMIN_CHAT_ID: Optional[str] = os.getenv("ADMIN_CHAT_ID")
    
    @property
    def is_webhook_mode(self) -> bool:
        """Check if webhook mode is configured."""
        return self.WEBHOOK_URL is not None
    
    def validate(self) -> bool:
        """Validate configuration."""
        if self.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
            raise ValueError("BOT_TOKEN must be set in environment variables")
        
        # Create temp directory if it doesn't exist
        os.makedirs(self.TEMP_DIR, exist_ok=True)
        
        return True
