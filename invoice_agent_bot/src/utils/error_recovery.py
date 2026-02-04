"""
Error Recovery Utilities

Provides self-healing error handling with retry logic, exponential backoff,
and graceful degradation for resilient bot operation.
"""

import asyncio
import functools
import random
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Type, List, Dict
from datetime import datetime

from src.core.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels for recovery decisions."""
    LOW = "low"           # Can retry immediately
    MEDIUM = "medium"     # Should backoff and retry
    HIGH = "high"         # May need fallback
    CRITICAL = "critical" # Requires manual intervention


class ProcessingError(Exception):
    """Base exception for processing errors."""
    
    def __init__(
        self, 
        message: str, 
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        recoverable: bool = True,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.severity = severity
        self.recoverable = recoverable
        self.context = context or {}
        self.timestamp = datetime.utcnow()


class AIError(ProcessingError):
    """Error related to AI operations."""
    pass


class DocumentError(ProcessingError):
    """Error related to document processing."""
    pass


class ValidationError(ProcessingError):
    """Error related to data validation."""
    pass


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 2.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple = (Exception,)


def calculate_delay(
    attempt: int, 
    config: Optional[RetryConfig] = None
) -> float:
    """
    Calculate delay for retry attempt using exponential backoff.
    
    Args:
        attempt: Current attempt number (0-indexed)
        config: Retry configuration
        
    Returns:
        float: Delay in seconds
    """
    if config is None:
        settings = get_settings()
        config = RetryConfig(
            max_attempts=settings.max_retry_attempts,
            base_delay=settings.retry_delay_base,
        )
    
    # Exponential backoff
    delay = config.base_delay * (config.exponential_base ** attempt)
    
    # Cap at max delay
    delay = min(delay, config.max_delay)
    
    # Add jitter to prevent thundering herd
    if config.jitter:
        delay = delay * (0.5 + random.random() * 0.5)
    
    return delay


def retry_with_backoff(
    max_attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: float = 60.0,
    retryable_exceptions: tuple = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
    on_failure: Optional[Callable[[Exception], None]] = None,
):
    """
    Decorator for retrying async functions with exponential backoff.
    
    Args:
        max_attempts: Maximum retry attempts
        base_delay: Initial delay between retries
        max_delay: Maximum delay cap
        retryable_exceptions: Exceptions that trigger retry
        on_retry: Callback on each retry
        on_failure: Callback on final failure
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            settings = get_settings()
            attempts = max_attempts or settings.max_retry_attempts
            delay = base_delay or settings.retry_delay_base
            
            config = RetryConfig(
                max_attempts=attempts,
                base_delay=delay,
                max_delay=max_delay,
                retryable_exceptions=retryable_exceptions,
            )
            
            last_exception = None
            
            for attempt in range(attempts):
                try:
                    return await func(*args, **kwargs)
                    
                except retryable_exceptions as e:
                    last_exception = e
                    
                    if attempt < attempts - 1:
                        retry_delay = calculate_delay(attempt, config)
                        
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{attempts}): {e}. "
                            f"Retrying in {retry_delay:.2f}s..."
                        )
                        
                        if on_retry:
                            try:
                                on_retry(e, attempt + 1)
                            except Exception as callback_error:
                                logger.error(f"Retry callback failed: {callback_error}")
                        
                        await asyncio.sleep(retry_delay)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {attempts} attempts: {e}"
                        )
                        
                        if on_failure:
                            try:
                                on_failure(e)
                            except Exception as callback_error:
                                logger.error(f"Failure callback failed: {callback_error}")
                        
                        raise last_exception
            
            # Should never reach here
            raise last_exception or RuntimeError("Unexpected retry loop exit")
        
        return wrapper
    return decorator


class CircuitBreaker:
    """
    Circuit breaker pattern for preventing cascade failures.
    
    Opens after threshold failures, preventing further calls
    until a cooldown period passes.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
        half_open_max_calls: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.half_open_max_calls = half_open_max_calls
        
        self._failures = 0
        self._last_failure_time: Optional[datetime] = None
        self._state = "closed"  # closed, open, half-open
        self._half_open_calls = 0
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking calls)."""
        if self._state == "open":
            # Check if cooldown has passed
            if self._last_failure_time:
                elapsed = (datetime.utcnow() - self._last_failure_time).total_seconds()
                if elapsed >= self.cooldown_seconds:
                    self._state = "half-open"
                    self._half_open_calls = 0
                    logger.info("Circuit breaker entering half-open state")
                    return False
            return True
        return False
    
    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == "half-open":
            self._half_open_calls += 1
            if self._half_open_calls >= self.half_open_max_calls:
                self._state = "closed"
                self._failures = 0
                logger.info("Circuit breaker closed")
        else:
            self._failures = max(0, self._failures - 1)
    
    def record_failure(self) -> None:
        """Record a failed call."""
        self._failures += 1
        self._last_failure_time = datetime.utcnow()
        
        if self._state == "half-open":
            self._state = "open"
            logger.warning("Circuit breaker opened (half-open failure)")
        elif self._failures >= self.failure_threshold:
            self._state = "open"
            logger.warning(f"Circuit breaker opened ({self._failures} failures)")


class ErrorRecoveryManager:
    """
    Centralized error recovery management.
    
    Tracks errors, manages circuit breakers, and provides
    recovery strategies for different error types.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._error_history: List[Dict[str, Any]] = []
        self._max_history = 100
    
    def get_circuit_breaker(self, name: str) -> CircuitBreaker:
        """Get or create a circuit breaker."""
        if name not in self._circuit_breakers:
            self._circuit_breakers[name] = CircuitBreaker()
        return self._circuit_breakers[name]
    
    def record_error(
        self, 
        error: Exception, 
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record an error in history."""
        error_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": type(error).__name__,
            "message": str(error),
            "context": context or {},
        }
        
        self._error_history.append(error_entry)
        
        # Trim history if needed
        if len(self._error_history) > self._max_history:
            self._error_history = self._error_history[-self._max_history:]
        
        logger.error(f"Error recorded: {error_entry}")
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics."""
        stats = {
            "total_errors": len(self._error_history),
            "by_type": {},
            "recent_errors": self._error_history[-10:],
        }
        
        for entry in self._error_history:
            error_type = entry["type"]
            stats["by_type"][error_type] = stats["by_type"].get(error_type, 0) + 1
        
        return stats
    
    async def execute_with_recovery(
        self,
        func: Callable,
        fallback: Optional[Callable] = None,
        circuit_breaker_name: Optional[str] = None,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with full recovery support.
        
        Args:
            func: Primary function to execute
            fallback: Optional fallback function
            circuit_breaker_name: Optional circuit breaker to use
            *args, **kwargs: Arguments for function
            
        Returns:
            Function result
            
        Raises:
            Exception: If all recovery attempts fail
        """
        # Check circuit breaker
        if circuit_breaker_name:
            cb = self.get_circuit_breaker(circuit_breaker_name)
            if cb.is_open:
                if fallback:
                    logger.info(f"Circuit open for {circuit_breaker_name}, using fallback")
                    return await fallback(*args, **kwargs)
                raise ProcessingError(
                    f"Circuit breaker open for {circuit_breaker_name}",
                    severity=ErrorSeverity.HIGH,
                    recoverable=False
                )
        
        try:
            result = await func(*args, **kwargs)
            
            if circuit_breaker_name:
                self.get_circuit_breaker(circuit_breaker_name).record_success()
            
            return result
            
        except Exception as e:
            self.record_error(e, {"function": func.__name__})
            
            if circuit_breaker_name:
                self.get_circuit_breaker(circuit_breaker_name).record_failure()
            
            # Try fallback if available
            if fallback:
                logger.info(f"Primary failed, attempting fallback: {e}")
                try:
                    return await fallback(*args, **kwargs)
                except Exception as fallback_error:
                    logger.error(f"Fallback also failed: {fallback_error}")
                    raise fallback_error
            
            raise


# Global error recovery manager
_recovery_manager: Optional[ErrorRecoveryManager] = None


def get_error_recovery() -> ErrorRecoveryManager:
    """Get the global error recovery manager."""
    global _recovery_manager
    if _recovery_manager is None:
        _recovery_manager = ErrorRecoveryManager()
    return _recovery_manager


def classify_error(error: Exception) -> ErrorSeverity:
    """
    Classify error severity based on type.
    
    Args:
        error: The exception to classify
        
    Returns:
        ErrorSeverity: Severity level
    """
    if isinstance(error, (AIError, DocumentError)):
        return ErrorSeverity.MEDIUM
    elif isinstance(error, ValidationError):
        return ErrorSeverity.LOW
    elif isinstance(error, (ConnectionError, TimeoutError)):
        return ErrorSeverity.MEDIUM
    elif isinstance(error, (PermissionError, FileNotFoundError)):
        return ErrorSeverity.HIGH
    else:
        return ErrorSeverity.MEDIUM


def is_recoverable(error: Exception) -> bool:
    """
    Determine if an error is likely recoverable.
    
    Args:
        error: The exception to check
        
    Returns:
        bool: True if error might be recoverable with retry
    """
    unrecoverable_types = (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        NotImplementedError,
    )
    
    if isinstance(error, ProcessingError):
        return error.recoverable
    
    return not isinstance(error, unrecoverable_types)
