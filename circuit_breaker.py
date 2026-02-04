"""
================================================================================
CIRCUIT BREAKER IMPLEMENTATION
================================================================================
Prevents cascade failures by temporarily blocking calls to failing services

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Failure threshold reached, requests blocked
- HALF_OPEN: Testing if service has recovered

Features:
- Thread-safe implementation
- Configurable failure thresholds and recovery timeouts
- Automatic state transitions
- Statistics tracking
- Manual control options
"""

import asyncio
import threading
import time
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, List, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = auto()      # Normal operation, requests pass through
    OPEN = auto()        # Failure threshold reached, requests blocked
    HALF_OPEN = auto()   # Testing if service has recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5           # Failures before opening
    recovery_timeout: float = 30.0       # Seconds before half-open
    half_open_max_calls: int = 3         # Test calls in half-open state
    success_threshold: int = 2           # Successes needed to close
    name: str = "default"
    on_state_change: Optional[Callable] = None
    on_open: Optional[Callable] = None
    on_close: Optional[Callable] = None


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker"""
    state_changes: int = 0
    failures: int = 0
    successes: int = 0
    rejected: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_changes": self.state_changes,
            "failures": self.failures,
            "successes": self.successes,
            "rejected": self.rejected,
            "consecutive_successes": self.consecutive_successes,
            "consecutive_failures": self.consecutive_failures,
        }


class CircuitBreaker:
    """
    Thread-safe circuit breaker implementation
    
    Usage:
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5))
        
        if cb.can_execute():
            try:
                result = call_external_service()
                cb.record_success()
            except Exception as e:
                cb.record_failure()
                raise
        else:
            # Circuit is open, use fallback
            result = fallback()
    """
    
    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._stats = CircuitBreakerStats()
        self._half_open_calls = 0
        self._lock = threading.RLock()
        self._opened_at: Optional[float] = None
        
    @property
    def state(self) -> CircuitState:
        """Get current state"""
        with self._lock:
            return self._state
    
    @property
    def stats(self) -> CircuitBreakerStats:
        """Get statistics"""
        with self._lock:
            return self._stats
    
    def can_execute(self) -> bool:
        """
        Check if a call should be allowed through
        Handles state transitions automatically
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            
            elif self._state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if self._opened_at and (time.time() - self._opened_at) >= self.config.recovery_timeout:
                    logger.info(f"Circuit {self.config.name}: Transitioning to HALF_OPEN")
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    self._stats.consecutive_successes = 0
                    self._notify_state_change(CircuitState.HALF_OPEN)
                    return True
                else:
                    self._stats.rejected += 1
                    return False
            
            elif self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.config.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                else:
                    self._stats.rejected += 1
                    return False
            
            return False
    
    def record_success(self):
        """Record a successful call"""
        with self._lock:
            self._stats.successes += 1
            self._stats.consecutive_successes += 1
            self._stats.consecutive_failures = 0
            self._stats.last_success_time = datetime.now()
            
            if self._state == CircuitState.HALF_OPEN:
                if self._stats.consecutive_successes >= self.config.success_threshold:
                    logger.info(f"Circuit {self.config.name}: Transitioning to CLOSED")
                    self._state = CircuitState.CLOSED
                    self._stats.closed_at = datetime.now()
                    self._stats.state_changes += 1
                    self._opened_at = None
                    self._notify_state_change(CircuitState.CLOSED)
                    if self.config.on_close:
                        self.config.on_close()
    
    def record_failure(self):
        """Record a failed call"""
        with self._lock:
            self._stats.failures += 1
            self._stats.consecutive_failures += 1
            self._stats.consecutive_successes = 0
            self._stats.last_failure_time = datetime.now()
            
            if self._state == CircuitState.CLOSED:
                if self._stats.consecutive_failures >= self.config.failure_threshold:
                    logger.warning(f"Circuit {self.config.name}: Transitioning to OPEN")
                    self._state = CircuitState.OPEN
                    self._opened_at = time.time()
                    self._stats.opened_at = datetime.now()
                    self._stats.state_changes += 1
                    self._notify_state_change(CircuitState.OPEN)
                    if self.config.on_open:
                        self.config.on_open()
            
            elif self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open goes back to open
                logger.warning(f"Circuit {self.config.name}: Failure in HALF_OPEN, returning to OPEN")
                self._state = CircuitState.OPEN
                self._opened_at = time.time()
                self._stats.opened_at = datetime.now()
                self._stats.state_changes += 1
                self._notify_state_change(CircuitState.OPEN)
                if self.config.on_open:
                    self.config.on_open()
    
    def _notify_state_change(self, new_state: CircuitState):
        """Notify state change callback"""
        if self.config.on_state_change:
            try:
                self.config.on_state_change(self._state, new_state, self._stats)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")
    
    def force_open(self):
        """Manually open the circuit"""
        with self._lock:
            if self._state != CircuitState.OPEN:
                logger.warning(f"Circuit {self.config.name}: Manually opened")
                self._state = CircuitState.OPEN
                self._opened_at = time.time()
                self._stats.opened_at = datetime.now()
                self._stats.state_changes += 1
                if self.config.on_open:
                    self.config.on_open()
    
    def force_close(self):
        """Manually close the circuit"""
        with self._lock:
            if self._state != CircuitState.CLOSED:
                logger.info(f"Circuit {self.config.name}: Manually closed")
                self._state = CircuitState.CLOSED
                self._stats.closed_at = datetime.now()
                self._stats.state_changes += 1
                self._opened_at = None
                self._stats.consecutive_failures = 0
                if self.config.on_close:
                    self.config.on_close()
    
    def get_status(self) -> Dict[str, Any]:
        """Get full status of circuit breaker"""
        with self._lock:
            return {
                "name": self.config.name,
                "state": self._state.name,
                "stats": self._stats.to_dict(),
                "config": {
                    "failure_threshold": self.config.failure_threshold,
                    "recovery_timeout": self.config.recovery_timeout,
                    "half_open_max_calls": self.config.half_open_max_calls,
                    "success_threshold": self.config.success_threshold,
                },
                "opened_at": self._opened_at,
                "half_open_calls": self._half_open_calls,
            }


class AsyncCircuitBreaker(CircuitBreaker):
    """Async-compatible circuit breaker"""
    
    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        super().__init__(config)
        self._async_lock = asyncio.Lock()
    
    async def can_execute_async(self) -> bool:
        """Async version of can_execute"""
        # Use thread-safe lock for state, but allow async context
        return self.can_execute()
    
    async def record_success_async(self):
        """Async version of record_success"""
        self.record_success()
    
    async def record_failure_async(self):
        """Async version of record_failure"""
        self.record_failure()


class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers
    Singleton pattern for global access
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._breakers: Dict[str, CircuitBreaker] = {}
        return cls._instance
    
    def get_or_create(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Get existing circuit breaker or create new one"""
        if name not in self._breakers:
            cfg = config or CircuitBreakerConfig(name=name)
            self._breakers[name] = CircuitBreaker(cfg)
        return self._breakers[name]
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name"""
        return self._breakers.get(name)
    
    def remove(self, name: str):
        """Remove circuit breaker"""
        if name in self._breakers:
            del self._breakers[name]
    
    def get_all_status(self) -> Dict[str, Dict]:
        """Get status of all circuit breakers"""
        return {name: cb.get_status() for name, cb in self._breakers.items()}
    
    def reset_all(self):
        """Reset all circuit breakers to closed state"""
        for cb in self._breakers.values():
            cb.force_close()


# Pre-configured circuit breakers for common services
class CircuitBreakerPresets:
    """Pre-configured circuit breaker settings"""
    
    @staticmethod
    def ai_model() -> CircuitBreakerConfig:
        """For AI model APIs (OpenAI, Anthropic, etc.)"""
        return CircuitBreakerConfig(
            name="ai_model",
            failure_threshold=3,
            recovery_timeout=30.0,
            half_open_max_calls=2,
            success_threshold=1,
        )
    
    @staticmethod
    def database() -> CircuitBreakerConfig:
        """For database connections"""
        return CircuitBreakerConfig(
            name="database",
            failure_threshold=5,
            recovery_timeout=10.0,
            half_open_max_calls=3,
            success_threshold=2,
        )
    
    @staticmethod
    def external_api() -> CircuitBreakerConfig:
        """For external APIs"""
        return CircuitBreakerConfig(
            name="external_api",
            failure_threshold=5,
            recovery_timeout=60.0,
            half_open_max_calls=2,
            success_threshold=1,
        )
    
    @staticmethod
    def file_service() -> CircuitBreakerConfig:
        """For file processing services"""
        return CircuitBreakerConfig(
            name="file_service",
            failure_threshold=3,
            recovery_timeout=20.0,
            half_open_max_calls=2,
            success_threshold=1,
        )
    
    @staticmethod
    def webhook() -> CircuitBreakerConfig:
        """For webhook endpoints"""
        return CircuitBreakerConfig(
            name="webhook",
            failure_threshold=10,
            recovery_timeout=120.0,
            half_open_max_calls=1,
            success_threshold=1,
        )


# Global registry
circuit_breaker_registry = CircuitBreakerRegistry()
