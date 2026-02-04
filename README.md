# Self-Healing Error Recovery System for Conversational AI Invoice Agent

A comprehensive error recovery and self-healing system designed for a conversational AI invoice agent that **NEVER FAILS**. No matter what goes wrong internally, users always receive a response and the system recovers automatically.

## Table of Contents

- [Overview](#overview)
- [Core Principles](#core-principles)
- [Error Scenarios Covered](#error-scenarios-covered)
- [Recovery Patterns](#recovery-patterns)
- [Architecture](#architecture)
- [Components](#components)
- [Usage](#usage)
- [Configuration](#configuration)
- [Monitoring](#monitoring)

## Overview

This system provides a multi-layered defense against failures, ensuring that:

1. **Users never see crashes** - Always receive a helpful response
2. **System recovers automatically** - No manual intervention required
3. **No technical details exposed** - User-friendly error messages
4. **State is preserved** - Sessions survive crashes and restarts
5. **Operations are retried** - Failed operations automatically retry

## Core Principles

### 1. Never-Fail Design
Every component has a backup plan. If the primary method fails, we fallback to secondary, tertiary, and ultimately static responses.

### 2. Graceful Degradation
When full functionality is unavailable, the system provides simplified but useful capabilities.

### 3. Transparent Recovery
Users are informed of delays but never exposed to technical errors or system details.

### 4. State Persistence
User sessions and data are preserved across crashes, restarts, and failures.

## Error Scenarios Covered

| Scenario | Recovery Strategy |
|----------|-------------------|
| AI model API failures | Fallback to backup models, then static responses |
| Document processing failures | Retry OCR, use rule-based extraction |
| Database failures | Use local cache, queue for later retry |
| Network connectivity issues | Exponential backoff retry |
| Webhook failures | Queue to DLQ, retry in background |
| Memory/state loss | Reconstruct from persistent storage |
| Unexpected user input | Clarify request, provide help options |
| File download failures | Retry download, request re-upload |
| Third-party service failures | Use alternative services, skip non-critical operations |

## Recovery Patterns

### 1. Retry Mechanisms with Exponential Backoff

```python
from retry_mechanism import async_retry, RetryPolicies

@async_retry(**RetryPolicies.ai_model_policy())
async def call_ai_model(prompt):
    # Will retry up to 5 times with exponential backoff
    return await openai_client.chat.completions.create(...)
```

**Features:**
- Configurable max retries and delays
- Jitter to prevent thundering herd
- Circuit breaker integration
- Comprehensive statistics

### 2. Circuit Breakers

```python
from circuit_breaker import CircuitBreaker, CircuitBreakerPresets

cb = CircuitBreaker(CircuitBreakerPresets.ai_model())

if cb.can_execute():
    try:
        result = await call_api()
        cb.record_success()
    except Exception as e:
        cb.record_failure()
        raise
else:
    # Circuit is open, use fallback
    result = await fallback()
```

**States:**
- **CLOSED**: Normal operation
- **OPEN**: Blocking requests (service failing)
- **HALF_OPEN**: Testing recovery

### 3. Fallback AI Models

```python
from fallback_chain import AIFallbackChain, ModelConfig, ModelTier

chain = AIFallbackChain()
chain.add_model(ModelConfig("gpt-4", ModelTier.PRIMARY, openai_client))
chain.add_model(ModelConfig("claude-3", ModelTier.SECONDARY, anthropic_client))
chain.add_model(ModelConfig("gpt-3.5", ModelTier.TERTIARY, openai_client))

response = await chain.generate("Extract invoice data...")
# Automatically falls through tiers on failure
```

### 4. State Persistence

```python
from state_persistence import create_state_manager, SessionState

manager = create_state_manager(
    use_memory=True,
    use_file=True,
    use_redis=False
)

# Save state
state = SessionState(session_id="123", user_id="456", chat_id="789")
await manager.save_state(state)

# Load state (survives crashes)
recovered = await manager.load_state("123")
```

**Layers:**
1. Memory (fastest, volatile)
2. File (survives restarts)
3. Redis (distributed, optional)

### 5. Dead Letter Queue

```python
from dead_letter_queue import DeadLetterQueue

dlq = DeadLetterQueue(storage_path="./dlq_storage")
await dlq.initialize()
await dlq.start_processor()

# Register handler for failed operations
dlq.register_handler("save_invoice", handle_save_invoice)

# Failed operations are automatically retried
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Layer                                │
│                    (Telegram User)                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Self-Healing Agent Layer                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Message    │  │    Error     │  │     User     │         │
│  │   Handler    │  │  Classifier  │  │    Messages  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Recovery Layer                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │  Retry   │  │ Circuit  │  │   AI     │  │ Degraded │       │
│  │ Handler  │  │ Breaker  │  │ Fallback │  │   Mode   │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Persistence Layer                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                     │
│  │  Memory  │  │   File   │  │  Redis   │                     │
│  └──────────┘  └──────────┘  └──────────┘                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   External Services                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │  OpenAI  │  │Anthropic │  │ Database │  │ Webhooks │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Error Classification (`error_classification.py`)

Intelligent error classification that determines:
- Error category (AI model, database, network, etc.)
- Severity level
- Whether error is retryable
- Appropriate retry strategy
- User-friendly message

```python
from error_classification import error_classifier

classified = error_classifier.classify(error)
print(classified.is_retryable)  # True/False
print(classified.max_retries)   # Number of retries
print(classified.user_message)  # User-friendly message
```

### 2. Retry Mechanism (`retry_mechanism.py`)

Production-grade retry with:
- Exponential backoff
- Jitter
- Circuit breaker integration
- Statistics tracking

```python
from retry_mechanism import async_retry, RetryPolicies

@async_retry(max_retries=5, base_delay=1.0)
async def my_function():
    pass
```

### 3. Circuit Breaker (`circuit_breaker.py`)

Prevents cascade failures:

```python
from circuit_breaker import CircuitBreaker, CircuitBreakerPresets

cb = CircuitBreaker(CircuitBreakerPresets.ai_model())
status = cb.get_status()
```

### 4. Fallback Chain (`fallback_chain.py`)

Multi-tier AI model fallback:

```python
from fallback_chain import AIFallbackChain, ModelConfig, ModelTier

chain = AIFallbackChain()
response = await chain.generate("Extract invoice data...")
```

### 5. State Persistence (`state_persistence.py`)

Multi-layer state management:

```python
from state_persistence import create_state_manager

manager = create_state_manager()
```

### 6. Dead Letter Queue (`dead_letter_queue.py`)

Failed operation handling:

```python
from dead_letter_queue import DeadLetterQueue

dlq = DeadLetterQueue()
await dlq.start_processor()
```

### 7. User Messages (`user_messages.py`)

User-friendly error messages:

```python
from user_messages import UserMessageManager

message = UserMessageManager.get_message("ai_model_timeout")
```

### 8. Self-Healing Agent (`self_healing_agent.py`)

Main integration:

```python
from self_healing_agent import SelfHealingInvoiceAgent

agent = SelfHealingInvoiceAgent()
await agent.initialize()

response = await agent.process_message(
    user_id="123",
    chat_id="456",
    message_text="Hello!"
)
```

## Usage

### Basic Usage

```python
import asyncio
from self_healing_agent import SelfHealingInvoiceAgent

async def main():
    # Initialize agent
    agent = SelfHealingInvoiceAgent()
    await agent.initialize()
    
    # Process a message
    response = await agent.process_message(
        user_id="user123",
        chat_id="chat456",
        message_text="Upload an invoice"
    )
    
    print(response.text)
    
    # Check health
    health = await agent.get_health_status()
    print(health)

asyncio.run(main())
```

### Using Individual Components

```python
from retry_mechanism import async_retry
from circuit_breaker import CircuitBreaker, CircuitBreakerPresets
from error_classification import error_classifier

# Create circuit breaker
cb = CircuitBreaker(CircuitBreakerPresets.ai_model())

# Use with retry decorator
@async_retry(max_retries=3, circuit_breaker=cb)
async def process_with_ai(prompt):
    # Your AI processing code
    pass

# Classify errors
try:
    await process_with_ai("Extract invoice data")
except Exception as e:
    classified = error_classifier.classify(e)
    print(f"Error: {classified.user_message}")
```

## Configuration

### Retry Policies

```python
from retry_mechanism import RetryPolicies

# Pre-configured policies
ai_policy = RetryPolicies.ai_model_policy()
db_policy = RetryPolicies.database_policy()
network_policy = RetryPolicies.network_policy()
```

### Circuit Breaker Presets

```python
from circuit_breaker import CircuitBreakerPresets

# Pre-configured presets
ai_preset = CircuitBreakerPresets.ai_model()
db_preset = CircuitBreakerPresets.database()
api_preset = CircuitBreakerPresets.external_api()
```

### State Manager

```python
from state_persistence import create_state_manager

manager = create_state_manager(
    use_memory=True,      # Enable memory layer
    use_file=True,        # Enable file layer
    file_path="./states", # File storage path
    use_redis=False,      # Disable Redis
    redis_url="redis://localhost:6379"
)
```

## Monitoring

### Health Status

```python
health = await agent.get_health_status()
```

Returns:
```json
{
  "agent_initialized": true,
  "service_health": {
    "ai_models": "healthy",
    "database": "healthy",
    "file_processing": "healthy",
    "external_apis": "healthy"
  },
  "circuit_breakers": {
    "ai_model": {
      "state": "CLOSED",
      "stats": {...}
    }
  }
}
```

### Circuit Breaker Status

```python
from circuit_breaker import circuit_breaker_registry

all_status = circuit_breaker_registry.get_all_status()
```

### DLQ Statistics

```python
stats = dlq.get_stats()
```

Returns:
```json
{
  "total_enqueued": 100,
  "total_success": 85,
  "total_failed": 10,
  "total_discarded": 5,
  "current_items": 15,
  "status_breakdown": {
    "PENDING": 5,
    "RETRYING": 8,
    "FAILED": 2
  }
}
```

## Recovery Flow Diagrams

See [RECOVERY_FLOW_DIAGRAMS.md](RECOVERY_FLOW_DIAGRAMS.md) for detailed visual diagrams of all recovery flows.

## Testing

```python
import asyncio
from self_healing_agent import SelfHealingInvoiceAgent

async def test_recovery():
    agent = SelfHealingInvoiceAgent()
    await agent.initialize()
    
    # Test various scenarios
    scenarios = [
        ("Normal message", {"message_text": "Hello"}),
        ("Document upload", {"attachments": [{"file_id": "123"}]}),
    ]
    
    for name, kwargs in scenarios:
        print(f"\nTesting: {name}")
        response = await agent.process_message(
            user_id="test_user",
            chat_id="test_chat",
            **kwargs
        )
        print(f"Response: {response.text}")
        print(f"Success: {response.success}")
        print(f"Used fallback: {response.used_fallback}")

asyncio.run(test_recovery())
```

## License

MIT License - See LICENSE file for details.

## Contributing

Contributions are welcome! Please ensure:
1. All tests pass
2. Code follows the existing style
3. Documentation is updated
4. New features include tests

## Support

For questions or issues:
- Open an issue on GitHub
- Check the documentation
- Review the recovery flow diagrams
