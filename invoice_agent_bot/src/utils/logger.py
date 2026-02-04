"""
Logging Utility Module

Configures structured logging for the application with both
console and file output support.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import structlog

from src.core.config import get_settings


def configure_logging() -> None:
    """
    Configure structured logging for the application.
    
    Sets up both console and file handlers based on configuration.
    """
    settings = get_settings()
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper()),
    )
    
    # Configure structlog
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    # Add console renderer if enabled
    if settings.enable_console_logging:
        processors.append(structlog.dev.ConsoleRenderer())
    
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Add file handler if enabled
    if settings.enable_file_logging:
        log_file = settings.log_dir / "bot.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, settings.log_level.upper()))
        
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        BoundLogger: Configured logger instance
    """
    return structlog.get_logger(name)


# Configure on module import
configure_logging()
