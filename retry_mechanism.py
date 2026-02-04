"""
================================================================================
RETRY MECHANISM WITH EXPONENTIAL BACKOFF
================================================================================
Production-grade retry decorator with jitter, circuit breaker integration,
and comprehensive logging

Features:
- Exponential backoff with configurable base and max delays
- Jitter to prevent thundering herd problems
- Circuit breaker integration
- Comprehensive statistics tracking
- Support for both sync and async functions
- Configurable retry policies for different scenarios
"""

import asyncio
import functools
import random
import time
import logging
from typing import Callable, TypeVar, Optional, List, Type, Any, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import traceback

# Setup logging
logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_max: float = 0.5
    retryable_exceptions: List[Type[Exception]] = field(default_factory=list)
    non_retryable_exceptions: List[Type[Exception]] = field(default_factory=list)
    on_retry: Optional[Callable] = None
    on_failure: Optional[Callable] = None
    on_success: Optional[Callable] = None
    timeout: Optional[float] = None
    circuit_breaker: Optional[Any] = None  # CircuitBreaker type (avoid circular import)


@dataclass
class RetryStats:
    """Statistics for retry operations"""
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    total_wait_time: float = 0.0
    last_attempt: Optional[datetime] = None
    consecutive_failures: int = 0
    
    def to_dict(self) -> dict:
        return {
            "attempts": self.attempts,
            "successes": self.successes,
            "failures": self.failures,
            "total_wait_time": self.total_wait_time,
            "consecutive_failures": self.consecutive_failures,
        }


class RetryContext:
    """Context manager for tracking retry state"""
    
    def __init__(self, config: RetryConfig, operation_name: str = "operation"):
        self.config = config
        self.operation_name = operation_name
        self.stats = RetryStats()
        self.errors: List[Exception] = []
        self.start_time: Optional[datetime] = None
        
    def __enter__(self):
        self.start_time = datetime.now()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            self.errors.append(exc_val)
        return False
    
    def record_attempt(self):
        self.stats.attempts += 1
        self.stats.last_attempt = datetime.now()
    
    def record_success(self):
        self.stats.successes += 1
        self.stats.consecutive_failures = 0
        
    def record_failure(self, error: Exception):
        self.stats.failures += 1
        self.stats.consecutive_failures += 1
        self.errors.append(error)
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and jitter"""
        # Exponential backoff: base_delay * (exponential_base ^ attempt)
        delay = self.config.base_delay * (self.config.exponential_base ** attempt)
        delay = min(delay, self.config.max_delay)
        
        # Add jitter to prevent thundering herd
        if self.config.jitter:
            jitter_amount = delay * self.config.jitter_max * random.uniform(-1, 1)
            delay = max(0, delay + jitter_amount)
        
        return delay
    
    def should_retry(self, error: Exception, attempt: int) -> bool:
        """Determine if we should retry based on error and attempt count"""
        if attempt >= self.config.max_retries:
            return False
        
        # Check non-retryable exceptions first
        if self.config.non_retryable_exceptions:
            if isinstance(error, tuple(self.config.non_retryable_exceptions)):
                return False
        
        # Check if specific retryable exceptions are defined
        if self.config.retryable_exceptions:
            return isinstance(error, tuple(self.config.retryable_exceptions))
        
        # Default: retry on most exceptions
        return True
    
    def get_summary(self) -> dict:
        """Get summary of retry operation"""
        duration = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        return {
            "operation": self.operation_name,
            "duration_seconds": duration,
            "stats": self.stats.to_dict(),
            "error_count": len(self.errors),
            "error_types": list(set(type(e).__name__ for e in self.errors)),
        }


def retry(**retry_kwargs):
    """
    Retry decorator with exponential backoff for synchronous functions
    
    Usage:
        @retry(max_retries=5, base_delay=2.0)
        def my_function():
            pass
    """
    config = RetryConfig(**retry_kwargs)
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            operation_name = f"{func.__module__}.{func.__name__}"
            
            with RetryContext(config, operation_name) as ctx:
                for attempt in range(config.max_retries + 1):
                    ctx.record_attempt()
                    
                    try:
                        # Check circuit breaker
                        if config.circuit_breaker and not config.circuit_breaker.can_execute():
                            raise CircuitBreakerOpenError(
                                f"Circuit breaker is OPEN for {operation_name}"
                            )
                        
                        result = func(*args, **kwargs)
                        
                        ctx.record_success()
                        
                        if config.on_success:
                            config.on_success(ctx.stats)
                            
                        if config.circuit_breaker:
                            config.circuit_breaker.record_success()
                            
                        return result
                        
                    except Exception as e:
                        ctx.record_failure(e)
                        
                        if config.circuit_breaker:
                            config.circuit_breaker.record_failure()
                        
                        # Check if we should retry
                        if not ctx.should_retry(e, attempt):
                            logger.error(f"Non-retryable error in {operation_name}: {e}")
                            if config.on_failure:
                                config.on_failure(e, ctx.stats)
                            raise
                        
                        # Calculate and apply delay
                        delay = ctx.calculate_delay(attempt)
                        ctx.stats.total_wait_time += delay
                        
                        logger.warning(
                            f"Attempt {attempt + 1}/{config.max_retries + 1} failed for "
                            f"{operation_name}: {e}. Retrying in {delay:.2f}s..."
                        )
                        
                        if config.on_retry:
                            config.on_retry(e, attempt + 1, delay, ctx.stats)
                        
                        time.sleep(delay)
                
                # All retries exhausted
                final_error = ctx.errors[-1] if ctx.errors else Exception("All retries failed")
                logger.error(f"All {config.max_retries + 1} attempts failed for {operation_name}")
                
                if config.on_failure:
                    config.on_failure(final_error, ctx.stats)
                
                raise final_error
                
        return wrapper
    return decorator


def async_retry(**retry_kwargs):
    """
    Retry decorator with exponential backoff for async functions
    
    Usage:
        @async_retry(max_retries=5, base_delay=2.0)
        async def my_async_function():
            pass
    """
    config = RetryConfig(**retry_kwargs)
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            operation_name = f"{func.__module__}.{func.__name__}"
            
            ctx = RetryContext(config, operation_name)
            
            for attempt in range(config.max_retries + 1):
                ctx.record_attempt()
                
                try:
                    # Check circuit breaker
                    if config.circuit_breaker and not config.circuit_breaker.can_execute():
                        raise CircuitBreakerOpenError(
                            f"Circuit breaker is OPEN for {operation_name}"
                        )
                    
                    # Apply timeout if configured
                    if config.timeout:
                        result = await asyncio.wait_for(
                            func(*args, **kwargs), 
                            timeout=config.timeout
                        )
                    else:
                        result = await func(*args, **kwargs)
                    
                    ctx.record_success()
                    
                    if config.on_success:
                        config.on_success(ctx.stats)
                        
                    if config.circuit_breaker:
                        config.circuit_breaker.record_success()
                        
                    return result
                    
                except asyncio.TimeoutError as e:
                    ctx.record_failure(e)
                    
                    if not ctx.should_retry(e, attempt):
                        logger.error(f"Timeout not retryable for {operation_name}")
                        raise
                    
                    delay = ctx.calculate_delay(attempt)
                    logger.warning(f"Timeout on attempt {attempt + 1}, retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    ctx.record_failure(e)
                    
                    if config.circuit_breaker:
                        config.circuit_breaker.record_failure()
                    
                    # Check if we should retry
                    if not ctx.should_retry(e, attempt):
                        logger.error(f"Non-retryable error in {operation_name}: {e}")
                        if config.on_failure:
                            config.on_failure(e, ctx.stats)
                        raise
                    
                    # Calculate and apply delay
                    delay = ctx.calculate_delay(attempt)
                    ctx.stats.total_wait_time += delay
                    
                    logger.warning(
                        f"Attempt {attempt + 1}/{config.max_retries + 1} failed for "
                        f"{operation_name}: {e}. Retrying in {delay:.2f}s..."
                    )
                    
                    if config.on_retry:
                        config.on_retry(e, attempt + 1, delay, ctx.stats)
                    
                    await asyncio.sleep(delay)
            
            # All retries exhausted
            final_error = ctx.errors[-1] if ctx.errors else Exception("All retries failed")
            logger.error(f"All {config.max_retries + 1} attempts failed for {operation_name}")
            
            if config.on_failure:
                config.on_failure(final_error, ctx.stats)
            
            raise final_error
            
        return wrapper
    return decorator


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass


# Convenience configurations for common scenarios
class RetryPolicies:
    """Pre-configured retry policies for different scenarios"""
    
    @staticmethod
    def ai_model_policy() -> dict:
        """Policy for AI model API calls"""
        return {
            "max_retries": 5,
            "base_delay": 1.0,
            "max_delay": 30.0,
            "exponential_base": 2.0,
            "jitter": True,
        }
    
    @staticmethod
    def database_policy() -> dict:
        """Policy for database operations"""
        return {
            "max_retries": 5,
            "base_delay": 0.5,
            "max_delay": 20.0,
            "exponential_base": 1.5,
            "jitter": True,
        }
    
    @staticmethod
    def network_policy() -> dict:
        """Policy for network operations"""
        return {
            "max_retries": 5,
            "base_delay": 1.0,
            "max_delay": 60.0,
            "exponential_base": 2.0,
            "jitter": True,
        }
    
    @staticmethod
    def file_download_policy() -> dict:
        """Policy for file downloads"""
        return {
            "max_retries": 3,
            "base_delay": 2.0,
            "max_delay": 30.0,
            "exponential_base": 2.0,
            "jitter": True,
        }
    
    @staticmethod
    def webhook_policy() -> dict:
        """Policy for webhook calls"""
        return {
            "max_retries": 3,
            "base_delay": 5.0,
            "max_delay": 60.0,
            "exponential_base": 2.0,
            "jitter": True,
        }
