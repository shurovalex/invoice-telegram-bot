"""
================================================================================
ERROR CLASSIFICATION SYSTEM
================================================================================
Classifies errors as retryable vs non-retryable for intelligent recovery decisions

This module provides intelligent error classification that determines:
- Whether an error is retryable
- The appropriate retry strategy (max retries, delays)
- The fallback strategy to use
- User-friendly error messages
- Log levels for monitoring
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, Dict, Any, Callable
import traceback
import json


class ErrorSeverity(Enum):
    """Severity levels for error classification"""
    CRITICAL = auto()      # System-wide failure, immediate attention needed
    HIGH = auto()          # Component failure, affects user experience
    MEDIUM = auto()        # Degraded functionality, can continue
    LOW = auto()           # Minor issue, logged for monitoring
    TRANSIENT = auto()     # Temporary issue, likely to resolve


class ErrorCategory(Enum):
    """Categories of errors for targeted recovery strategies"""
    AI_MODEL = "ai_model"
    DOCUMENT_PROCESSING = "document_processing"
    DATABASE = "database"
    NETWORK = "network"
    WEBHOOK = "webhook"
    MEMORY = "memory"
    USER_INPUT = "user_input"
    FILE_DOWNLOAD = "file_download"
    THIRD_PARTY = "third_party"
    UNKNOWN = "unknown"


@dataclass
class ClassifiedError:
    """Structured error information for recovery decisions"""
    original_error: Exception
    category: ErrorCategory
    severity: ErrorSeverity
    is_retryable: bool
    max_retries: int
    retry_delay_base: float  # Base delay in seconds
    fallback_strategy: str
    user_message: str
    log_level: str
    context: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "severity": self.severity.name,
            "is_retryable": self.is_retryable,
            "max_retries": self.max_retries,
            "error_type": type(self.original_error).__name__,
            "error_message": str(self.original_error),
            "fallback_strategy": self.fallback_strategy,
            "user_message": self.user_message,
        }


class ErrorClassifier:
    """
    Intelligent error classifier that determines recovery strategy
    based on error type, message patterns, and context
    """
    
    # Error patterns for classification
    RETRYABLE_PATTERNS = {
        "rate_limit": ["rate limit", "too many requests", "429", "throttled"],
        "timeout": ["timeout", "timed out", "connection timeout", "read timeout"],
        "transient": ["temporary", "transient", "unavailable", "try again", "503", "502", "504"],
        "network": ["connection error", "network error", "dns", "unreachable", "reset by peer"],
        "service_down": ["service unavailable", "maintenance", "overloaded"],
    }
    
    NON_RETRYABLE_PATTERNS = {
        "auth": ["unauthorized", "forbidden", "401", "403", "authentication", "invalid key"],
        "not_found": ["not found", "404", "does not exist", "missing"],
        "validation": ["invalid", "bad request", "validation", "malformed", "400"],
        "quota": ["quota exceeded", "limit exceeded", "insufficient", "out of credits"],
        "corrupted": ["corrupt", "invalid format", "cannot parse", "unsupported"],
    }
    
    def __init__(self):
        self._custom_classifiers: Dict[type, Callable] = {}
    
    def classify(self, error: Exception, context: Optional[Dict] = None) -> ClassifiedError:
        """
        Classify an error and determine recovery strategy
        
        Args:
            error: The exception to classify
            context: Additional context about the error
            
        Returns:
            ClassifiedError with recovery strategy
        """
        context = context or {}
        error_msg = str(error).lower()
        error_type = type(error).__name__
        
        # Check for custom classifier first
        if type(error) in self._custom_classifiers:
            return self._custom_classifiers[type(error)](error, context)
        
        # Determine category
        category = self._determine_category(error, error_msg)
        
        # Check if retryable
        is_retryable, severity, max_retries, delay_base = self._analyze_retryability(
            error, error_msg, error_type, category
        )
        
        # Determine fallback strategy
        fallback_strategy = self._get_fallback_strategy(category, is_retryable)
        
        # Generate user-friendly message
        user_message = self._generate_user_message(category, severity, is_retryable)
        
        # Determine log level
        log_level = self._get_log_level(severity)
        
        return ClassifiedError(
            original_error=error,
            category=category,
            severity=severity,
            is_retryable=is_retryable,
            max_retries=max_retries,
            retry_delay_base=delay_base,
            fallback_strategy=fallback_strategy,
            user_message=user_message,
            log_level=log_level,
            context=context
        )
    
    def _determine_category(self, error: Exception, error_msg: str) -> ErrorCategory:
        """Determine error category based on error type and message"""
        error_type = type(error).__name__.lower()
        
        # Map error types to categories
        if any(x in error_type or x in error_msg for x in ["openai", "anthropic", "ai", "llm", "model"]):
            return ErrorCategory.AI_MODEL
        elif any(x in error_type or x in error_msg for x in ["ocr", "document", "pdf", "image"]):
            return ErrorCategory.DOCUMENT_PROCESSING
        elif any(x in error_type or x in error_msg for x in ["database", "db", "sql", "mongo", "redis"]):
            return ErrorCategory.DATABASE
        elif any(x in error_type or x in error_msg for x in ["network", "connection", "http", "url", "ssl"]):
            return ErrorCategory.NETWORK
        elif any(x in error_type or x in error_msg for x in ["webhook", "callback"]):
            return ErrorCategory.WEBHOOK
        elif any(x in error_type or x in error_msg for x in ["memory", "state", "session"]):
            return ErrorCategory.MEMORY
        elif any(x in error_type or x in error_msg for x in ["user", "input", "command"]):
            return ErrorCategory.USER_INPUT
        elif any(x in error_type or x in error_msg for x in ["download", "file", "telegram"]):
            return ErrorCategory.FILE_DOWNLOAD
        elif any(x in error_type or x in error_msg for x in ["cloudconvert", "google", "sheets", "api"]):
            return ErrorCategory.THIRD_PARTY
        
        return ErrorCategory.UNKNOWN
    
    def _analyze_retryability(self, error: Exception, error_msg: str, 
                              error_type: str, category: ErrorCategory) -> tuple:
        """Analyze if error is retryable and determine retry parameters"""
        
        # Check non-retryable patterns first (higher priority)
        for pattern_list in self.NON_RETRYABLE_PATTERNS.values():
            if any(p in error_msg or p in error_type.lower() for p in pattern_list):
                return False, ErrorSeverity.HIGH, 0, 0.0
        
        # Check retryable patterns
        for pattern_type, pattern_list in self.RETRYABLE_PATTERNS.items():
            if any(p in error_msg or p in error_type.lower() for p in pattern_list):
                if pattern_type == "rate_limit":
                    return True, ErrorSeverity.MEDIUM, 5, 2.0  # Longer delays for rate limits
                elif pattern_type == "timeout":
                    return True, ErrorSeverity.MEDIUM, 3, 1.0
                elif pattern_type == "service_down":
                    return True, ErrorSeverity.HIGH, 10, 5.0
                else:
                    return True, ErrorSeverity.TRANSIENT, 3, 0.5
        
        # Category-specific defaults
        category_defaults = {
            ErrorCategory.AI_MODEL: (True, ErrorSeverity.HIGH, 3, 1.0),
            ErrorCategory.DOCUMENT_PROCESSING: (False, ErrorSeverity.HIGH, 0, 0.0),
            ErrorCategory.DATABASE: (True, ErrorSeverity.CRITICAL, 5, 1.0),
            ErrorCategory.NETWORK: (True, ErrorSeverity.MEDIUM, 5, 1.0),
            ErrorCategory.WEBHOOK: (True, ErrorSeverity.LOW, 3, 2.0),
            ErrorCategory.MEMORY: (False, ErrorSeverity.CRITICAL, 0, 0.0),
            ErrorCategory.USER_INPUT: (False, ErrorSeverity.LOW, 0, 0.0),
            ErrorCategory.FILE_DOWNLOAD: (True, ErrorSeverity.MEDIUM, 3, 1.0),
            ErrorCategory.THIRD_PARTY: (True, ErrorSeverity.MEDIUM, 3, 1.0),
            ErrorCategory.UNKNOWN: (True, ErrorSeverity.MEDIUM, 2, 1.0),
        }
        
        return category_defaults.get(category, (True, ErrorSeverity.MEDIUM, 2, 1.0))
    
    def _get_fallback_strategy(self, category: ErrorCategory, is_retryable: bool) -> str:
        """Determine appropriate fallback strategy"""
        strategies = {
            ErrorCategory.AI_MODEL: "fallback_model" if is_retryable else "static_response",
            ErrorCategory.DOCUMENT_PROCESSING: "manual_extraction" if is_retryable else "request_new_file",
            ErrorCategory.DATABASE: "local_cache" if is_retryable else "in_memory_state",
            ErrorCategory.NETWORK: "queue_for_retry" if is_retryable else "degraded_mode",
            ErrorCategory.WEBHOOK: "queue_for_retry" if is_retryable else "log_and_continue",
            ErrorCategory.MEMORY: "reconstruct_state" if is_retryable else "start_fresh",
            ErrorCategory.USER_INPUT: "clarify_request",
            ErrorCategory.FILE_DOWNLOAD: "retry_download" if is_retryable else "request_again",
            ErrorCategory.THIRD_PARTY: "alternative_service" if is_retryable else "skip_operation",
            ErrorCategory.UNKNOWN: "generic_retry" if is_retryable else "graceful_degradation",
        }
        return strategies.get(category, "graceful_degradation")
    
    def _generate_user_message(self, category: ErrorCategory, severity: ErrorSeverity, 
                               is_retryable: bool) -> str:
        """Generate user-friendly error message"""
        if is_retryable:
            messages = {
                ErrorCategory.AI_MODEL: "I'm experiencing a brief delay. Let me try again...",
                ErrorCategory.DATABASE: "Just a moment, reconnecting to my systems...",
                ErrorCategory.NETWORK: "Connection hiccup! Retrying...",
                ErrorCategory.FILE_DOWNLOAD: "Having trouble accessing your file. Trying again...",
                ErrorCategory.THIRD_PARTY: "Connecting to external service...",
            }
        else:
            messages = {
                ErrorCategory.AI_MODEL: "I'm having trouble processing that. Could you rephrase?",
                ErrorCategory.DOCUMENT_PROCESSING: "I couldn't read that document. Could you try a clearer image or PDF?",
                ErrorCategory.DATABASE: "I'm having trouble saving your data. Your current session is safe.",
                ErrorCategory.USER_INPUT: "I'm not sure I understood. Could you clarify what you need?",
                ErrorCategory.FILE_DOWNLOAD: "I couldn't download your file. Please try uploading it again.",
                ErrorCategory.THIRD_PARTY: "An external service is temporarily unavailable. I'll continue with what I can do.",
            }
        
        default_msg = "I'm working on it. One moment please..." if is_retryable else \
                      "I encountered an issue, but I'm still here to help!"
        return messages.get(category, default_msg)
    
    def _get_log_level(self, severity: ErrorSeverity) -> str:
        """Map severity to log level"""
        mapping = {
            ErrorSeverity.CRITICAL: "CRITICAL",
            ErrorSeverity.HIGH: "ERROR",
            ErrorSeverity.MEDIUM: "WARNING",
            ErrorSeverity.LOW: "INFO",
            ErrorSeverity.TRANSIENT: "DEBUG",
        }
        return mapping.get(severity, "WARNING")
    
    def register_custom_classifier(self, error_type: type, classifier: Callable):
        """Register a custom classifier for specific error types"""
        self._custom_classifiers[error_type] = classifier


# Global error classifier instance
error_classifier = ErrorClassifier()
