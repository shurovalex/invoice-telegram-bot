# RESILIENT SELF-HEALING CONVERSATIONAL AI INVOICE AGENT
## Architecture Design Document

---

## 1. HIGH-LEVEL ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         RESILIENT INVOICE AGENT ARCHITECTURE                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌─────────────┐ │
│  │   TELEGRAM   │────▶│   API GATEWAY│────▶│   MESSAGE    │────▶│   STATE     │ │
│  │    USER      │◄────│   (Webhook)  │◄────│   QUEUE      │◄────│   MANAGER   │ │
│  └──────────────┘     └──────────────┘     │   (Redis)    │     └─────────────┘ │
│                                            └──────────────┘           │         │
│                                                   │                   │         │
│                                                   ▼                   ▼         │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                    ORCHESTRATION LAYER (Celery Workers)                   │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │  │
│  │  │  CIRCUIT    │  │   RETRY     │  │  DEAD       │  │  FALLBACK       │  │  │
│  │  │  BREAKER    │  │   HANDLER   │  │  LETTER     │  │  ORCHESTRATOR   │  │  │
│  │  │  (pybreaker)│  │  (tenacity) │  │  QUEUE      │  │                 │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                    │                                             │
│         ┌──────────────────────────┼──────────────────────────┐                  │
│         ▼                          ▼                          ▼                  │
│  ┌─────────────┐           ┌─────────────┐           ┌─────────────┐            │
│  │   BOT       │           │  DOCUMENT   │           │    AI       │            │
│  │   LAYER     │           │  PROCESSING │           │   LAYER     │            │
│  │             │           │   LAYER     │           │             │            │
│  │ • Command   │           │             │           │ • Extraction│            │
│  │   Handler   │           │ • OCR       │           │ • Validation│            │
│  │ • State     │           │ • PDF Parse │           │ • Fallback  │            │
│  │   Machine   │           │ • DOCX Parse│           │   Models    │            │
│  │ • Response  │           │ • Image     │           │ • Confidence│            │
│  │   Builder   │           │   Process   │           │   Scoring   │            │
│  └─────────────┘           └─────────────┘           └─────────────┘            │
│         │                          │                          │                  │
│         └──────────────────────────┼──────────────────────────┘                  │
│                                    ▼                                             │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                         DATA & OUTPUT LAYER                               │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │  │
│  │  │  INVOICE    │  │   JSON      │  │  DOCUMENT   │  │   NOTIFICATION  │  │  │
│  │  │  DATABASE   │  │   SCHEMA    │  │  GENERATOR  │  │   SERVICE       │  │  │
│  │  │  (PostgreSQL│  │   VALIDATOR │  │  (Templates)│  │  (User Alerts)  │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. COMPONENT SEPARATION & RESPONSIBILITIES

### 2.1 BOT LAYER (Telegram Interface)
**Purpose:** User-facing interface, stateless message handling

```python
# Key Components:
class TelegramBotHandler:
    """
    NEVER contains business logic
    ONLY handles: receive message -> queue for processing -> return ack
    """
    - receive_message() -> Immediately ACK to Telegram (200ms timeout!)
    - validate_message_type() -> text | image | document | command
    - enqueue_for_processing() -> Push to Redis Queue
    - send_response() -> Format and send back to user
    - heartbeat_check() -> Health monitoring

class CommandRouter:
    """
    Routes commands to appropriate handlers
    """
    - /start -> Initialize conversation
    - /new_invoice -> Start new invoice flow
    - /status -> Check current invoice status
    - /help -> Provide assistance
    - /cancel -> Cancel current operation
```

### 2.2 STATE MANAGER (Conversation Context)
**Purpose:** Persistent conversation state across failures

```python
class ConversationStateManager:
    """
    Redis-backed state machine for each conversation
    Survives worker restarts, network failures
    """
    
    STATE_SCHEMA = {
        "conversation_id": "uuid",
        "user_id": "telegram_user_id",
        "current_state": "collecting_contractor|collecting_work|review|complete",
        "invoice_data": {
            "contractor": {...},
            "work_items": [...],
            "financials": {...}
        },
        "collected_fields": ["field1", "field2"],  # Track progress
        "pending_fields": ["field3", "field4"],    # What is needed
        "retry_count": 0,                          # For self-healing
        "last_activity": "timestamp",
        "processing_errors": [],                   # Error history
        "fallback_activated": False                # Degradation flag
    }
    
    Methods:
    - create_conversation(user_id) -> Initialize new state
    - get_state(conversation_id) -> Retrieve current state
    - update_state(conversation_id, updates) -> Atomic update with TTL
    - transition_state(conversation_id, new_state) -> State machine transition
    - acquire_lock(conversation_id) -> Prevent concurrent processing
    - release_lock(conversation_id)
```

### 2.3 DOCUMENT PROCESSING LAYER
**Purpose:** Extract data from uploaded files with multiple fallback strategies

```python
class DocumentProcessor:
    """
    Multi-strategy document processing with graceful degradation
    """
    
    PROCESSING_PIPELINES = {
        "image": [
            "primary": "google_vision_ocr",
            "fallback_1": "tesseract_ocr",
            "fallback_2": "azure_form_recognizer",
            "manual": "request_user_input"
        ],
        "pdf": [
            "primary": "pdfplumber_extract",
            "fallback_1": "pymupdf_extract",
            "fallback_2": "pdf2image_+_ocr",
            "manual": "request_user_input"
        ],
        "docx": [
            "primary": "python_docx_extract",
            "fallback_1": " mammoth_convert",
            "manual": "request_user_input"
        ]
    }
```

### 2.4 AI PROCESSING LAYER
**Purpose:** Intelligent data extraction with model fallback chain

```python
class AIProcessor:
    """
    Multi-model AI processing with circuit breakers
    """
    
    MODEL_CHAIN = [
        {"name": "openai_gpt4", "priority": 1, "circuit_breaker": True},
        {"name": "anthropic_claude", "priority": 2, "circuit_breaker": True},
        {"name": "openai_gpt35", "priority": 3, "circuit_breaker": True},
        {"name": "local_llm", "priority": 4, "circuit_breaker": False},
        {"name": "rule_based", "priority": 5, "circuit_breaker": False}
    ]
```

### 2.5 OUTPUT GENERATION LAYER
**Purpose:** Create final deliverables

```python
class OutputGenerator:
    - generate_json_output() -> Structured invoice data
    - generate_pdf_invoice() -> Formatted invoice document
    - generate_confirmation_message() -> User-friendly summary
    - store_for_review() -> Queue for manual review if needed
```

---

## 3. STATE MANAGEMENT STRATEGY

### 3.1 Conversation State Machine

```
                    ┌─────────────────┐
                    │     START       │
                    │   (/start or    │
                    │  /new_invoice)  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
         ┌─────────│  COLLECTING_    │◄─────────────────────────┐
         │         │  CONTRACTOR     │                          │
         │         │  INFO           │                          │
         │         └────────┬────────┘                          │
         │                  │                                    │
         │    ┌─────────────┼─────────────┐                     │
         │    │             │             │                     │
         │    ▼             ▼             ▼                     │
         │ ┌──────┐    ┌────────┐    ┌─────────┐               │
         │ │Text  │    │Image   │    │Document │               │
         │ │Input │    │Upload  │    │Upload   │               │
         │ └──┬───┘    └───┬────┘    └────┬────┘               │
         │    │            │              │                     │
         │    └────────────┴──────────────┘                     │
         │                   │                                   │
         │                   ▼                                   │
         │         ┌─────────────────┐                          │
         │         │  PROCESSING_    │                          │
         │         │  DOCUMENT       │                          │
         │         │  (with retries) │                          │
         │         └────────┬────────┘                          │
         │                  │                                    │
         │         ┌────────┴────────┐                         │
         │         │                 │                         │
         │         ▼                 ▼                         │
         │  ┌──────────┐     ┌──────────────┐                 │
         │  │ SUCCESS  │     │    FAILED    │─────────────────┘
         │  │          │     │  (ask again) │
         │  └────┬─────┘     └──────────────┘
         │       │
         │       ▼
         │  ┌─────────────────┐
         │  │  VALIDATING_    │
         │  │  DATA           │
         │  │  (AI + rules)   │
         │  └────────┬────────┘
         │           │
         │  ┌────────┴────────┐
         │  │                 │
         │  ▼                 ▼
         │ ┌──────┐    ┌──────────────┐
         │ │VALID │    │  INVALID     │──────────┐
         │ │      │    │  (ask user   │          │
         │ └──┬───┘    │   to fix)    │◄─────────┘
         │    │        └──────────────┘
         │    │
         │    ▼
         │ ┌─────────────────┐
         └─│  COLLECTING_    │
           │  WORK_ITEMS     │
           │  (repeatable)   │
           └────────┬────────┘
                    │
                    ▼
           ┌─────────────────┐
           │  COLLECTING_    │
           │  FINANCIALS     │
           └────────┬────────┘
                    │
                    ▼
           ┌─────────────────┐
           │  REVIEW_        │
           │  AND_CONFIRM    │
           └────────┬────────┘
                    │
           ┌────────┴────────┐
           │                 │
           ▼                 ▼
      ┌─────────┐      ┌──────────┐
      │CONFIRMED│      │  EDIT    │──────┐
      │         │      │ REQUESTED│      │
      └────┬────┘      └──────────┘      │
           │                             │
           ▼                             │
      ┌─────────────────┐                │
      │  GENERATING_    │                │
      │  OUTPUTS        │                │
      │  (JSON + PDF)   │                │
      └────────┬────────┘                │
           │                             │
           ▼                             │
      ┌─────────────────┐                │
      │    COMPLETE     │────────────────┘
      │  (send files)   │
      └─────────────────┘
```

### 3.2 State Persistence Strategy

```python
# Redis Key Structure
"invoice_bot:conversation:{conversation_id}" -> Hash with TTL 24h
"invoice_bot:user:{user_id}:active" -> Current conversation ID
"invoice_bot:lock:{conversation_id}" -> Distributed lock (5s expiry)
"invoice_bot:queue:processing" -> List of pending messages
"invoice_bot:queue:dead_letter" -> Failed messages for analysis

# Atomic State Updates
WATCH conversation_key
MULTI
HSET conversation_key field1 value1 field2 value2
EXPIRE conversation_key 86400
EXEC
```

---

## 4. DATA FLOW FOR DIFFERENT INPUT TYPES

### 4.1 Text Input Flow

```
User Text -> Telegram -> Webhook -> Message Queue -> Bot Layer
                                              │
                                              ▼
                                    ┌─────────────────┐
                                    │ Parse Intent    │
                                    │ (command vs     │
                                    │  data input)    │
                                    └────────┬────────┘
                                             │
                              ┌──────────────┼──────────────┐
                              │              │              │
                              ▼              ▼              ▼
                        ┌────────┐    ┌──────────┐    ┌──────────┐
                        │Command │    │ Field    │    │ Natural  │
                        │Handler │    │ Data     │    │ Language │
                        │        │    │ Parser   │    │ Parser   │
                        └───┬────┘    └────┬─────┘    └────┬─────┘
                            │              │               │
                            └──────────────┴───────────────┘
                                           │
                                           ▼
                              ┌─────────────────────────┐
                              │ Update Conversation State │
                              │ (mark field as collected) │
                              └─────────────┬─────────────┘
                                            │
                                            ▼
                              ┌─────────────────────────┐
                              │ Determine Next Question │
                              │ (from pending_fields)   │
                              └─────────────┬─────────────┘
                                            │
                                            ▼
                              ┌─────────────────────────┐
                              │ Send Response to User   │
                              └─────────────────────────┘
```

### 4.2 Image/PDF/DOCX Upload Flow

```
User Upload -> Telegram -> Webhook -> Download File -> Store Temp
                                                    │
                                                    ▼
                                        ┌─────────────────────┐
                                        │ Detect File Type    │
                                        │ (MIME + magic)      │
                                        └──────────┬──────────┘
                                                   │
                         ┌─────────────────────────┼─────────────────────────┐
                         │                         │                         │
                         ▼                         ▼                         ▼
               ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
               │   IMAGE         │      │   PDF           │      │   DOCX          │
               │   PROCESSOR     │      │   PROCESSOR     │      │   PROCESSOR     │
               │                 │      │                 │      │                 │
               │ 1. Preprocess   │      │ 1. Try text     │      │ 1. Extract XML  │
               │    (resize,     │      │    extraction   │      │    structure    │
               │    enhance)     │      │ 2. If image-    │      │ 2. Parse tables │
               │ 2. OCR (primary)│      │    based: OCR   │      │ 3. Extract text │
               │ 3. OCR (fallback│      │ 3. Table detect │      │                 │
               │    if low conf) │      │                 │      │                 │
               └────────┬────────┘      └────────┬────────┘      └────────┬────────┘
                        │                        │                        │
                        └────────────────────────┼────────────────────────┘
                                                 │
                                                 ▼
                                    ┌─────────────────────┐
                                    │ Extracted Raw Text  │
                                    └──────────┬──────────┘
                                               │
                                               ▼
                                    ┌─────────────────────┐
                                    │ AI Data Extraction  │
                                    │ (with model chain)  │
                                    └──────────┬──────────┘
                                               │
                              ┌────────────────┼────────────────┐
                              │                │                │
                              ▼                ▼                ▼
                    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                    │ HIGH CONF    │  │ MEDIUM CONF  │  │ LOW CONF     │
                    │ (>0.85)      │  │ (0.6-0.85)   │  │ (<0.6)       │
                    │              │  │              │  │              │
                    │ Auto-accept  │  │ Show user    │  │ Ask user to  │
                    │ & confirm    │  │ for verify   │  │ re-upload or │
                    │              │  │              │  │ enter manual │
                    └──────────────┘  └──────────────┘  └──────────────┘
```

---

## 5. NEVER-FAIL PATTERNS & SELF-HEALING MECHANISMS

### 5.1 Circuit Breaker Pattern

```python
from pybreaker import CircuitBreaker
import tenacity

# Circuit breakers prevent cascade failures
class AICircuitBreakers:
    """
    Each external service has its own circuit breaker
    When failures exceed threshold, circuit opens -> fast fail -> use fallback
    """
    
    openai_breaker = CircuitBreaker(
        fail_max=5,           # Open after 5 failures
        reset_timeout=60,     # Try again after 60 seconds
        expected_exception=Exception
    )
    
    anthropic_breaker = CircuitBreaker(
        fail_max=5,
        reset_timeout=60,
        expected_exception=Exception
    )
    
    google_vision_breaker = CircuitBreaker(
        fail_max=3,
        reset_timeout=30,
        expected_exception=Exception
    )

# Usage
@AICircuitBreakers.openai_breaker
def extract_with_gpt4(text):
    return openai_client.extract_invoice_data(text)
```

### 5.2 Retry with Exponential Backoff

```python
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, before_sleep_log
)

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type((RateLimitError, TimeoutError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=False  # Do not raise final exception - return fallback
)
def process_with_retry(func, *args, fallback_func=None, **kwargs):
    """
    Retry with exponential backoff
    If all retries fail, return fallback result instead of raising
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if fallback_func:
            logger.warning(f"Primary failed, using fallback: {e}")
            return fallback_func(*args, **kwargs)
        raise
```

### 5.3 Graceful Degradation Chain

```python
class GracefulDegradationChain:
    """
    Always return SOMETHING to the user
    Never fail completely - degrade functionality instead
    """
    
    def process_document(self, file_data, conversation_state):
        strategies = [
            # (priority, function, degradation_level)
            (1, self._full_ai_processing, "full"),
            (2, self._basic_ocr_plus_ai, "reduced"),
            (3, self._template_matching, "minimal"),
            (4, self._manual_input_request, "manual")
        ]
        
        for priority, strategy, level in strategies:
            try:
                result = strategy(file_data)
                if result.get("usable", False):
                    conversation_state["degradation_level"] = level
                    return result
            except Exception as e:
                logger.warning(f"Strategy {priority} failed: {e}")
                continue
        
        # Absolute fallback - should never reach here
        return self._absolute_fallback(conversation_state)
    
    def _manual_input_request(self, file_data):
        """Manual: Ask user to type data"""
        return {
            "usable": True,
            "message": "I could not read that document. Could you please type the details?",
            "fields_needed": self._get_required_fields()
        }
    
    def _absolute_fallback(self, conversation_state):
        """Emergency: Preserve state and notify"""
        return {
            "usable": True,
            "message": "I am having technical difficulties. Your progress is saved. Please try again in a moment.",
            "conversation_preserved": True
        }
```

### 5.4 Dead Letter Queue & Recovery

```python
class DeadLetterHandler:
    """
    Failed messages go to DLQ for analysis and retry
    """
    
    def handle_failed_message(self, message, error):
        # Store in DLQ with metadata
        dlq_entry = {
            "original_message": message,
            "error": str(error),
            "error_type": type(error).__name__,
            "timestamp": datetime.utcnow().isoformat(),
            "retry_count": message.get("retry_count", 0),
            "conversation_id": message.get("conversation_id")
        }
        
        redis.lpush("invoice_bot:queue:dead_letter", json.dumps(dlq_entry))
        
        # Notify user their request is queued
        self.notify_user_queued(message["user_id"])
    
    def process_dlq(self):
        """
        Background job: retry DLQ items with exponential backoff
        """
        while True:
            entry = redis.brpop("invoice_bot:queue:dead_letter", timeout=5)
            if entry:
                data = json.loads(entry[1])
                if self.should_retry(data):
                    self.retry_message(data)
                else:
                    self.escalate_to_manual(data)
```

### 5.5 Health Check & Self-Healing

```python
class HealthMonitor:
    """
    Continuous health monitoring with automatic recovery
    """
    
    HEALTH_CHECKS = {
        "redis": check_redis_connection,
        "database": check_database_connection,
        "openai_api": check_openai_health,
        "telegram_api": check_telegram_health,
        "disk_space": check_disk_space,
        "memory": check_memory_usage
    }
    
    def run_health_checks(self):
        results = {}
        for component, check_func in self.HEALTH_CHECKS.items():
            try:
                results[component] = check_func()
            except Exception as e:
                results[component] = {"healthy": False, "error": str(e)}
                self.trigger_self_healing(component, e)
        
        return results
    
    def trigger_self_healing(self, component, error):
        """
        Attempt automatic recovery based on component
        """
        healing_actions = {
            "redis": self._restart_redis_connection,
            "database": self._reconnect_database,
            "openai_api": self._switch_to_backup_model,
            "disk_space": self._cleanup_temp_files,
            "memory": self._restart_workers
        }
        
        action = healing_actions.get(component)
        if action:
            try:
                action()
                logger.info(f"Self-healing succeeded for {component}")
            except Exception as e:
                logger.error(f"Self-healing failed for {component}: {e}")
                self.alert_oncall(component, error, e)
```

### 5.6 User Communication During Failures

```python
class FailureCommunicator:
    """
    Always inform user what is happening - never go silent
    """
    
    MESSAGES = {
        "processing": "Processing your document... This may take a moment.",
        "retrying": "I am having a little trouble. Let me try another approach...",
        "degraded": "I am running in simplified mode, but I will still get your invoice done!",
        "manual_needed": "I could not read that automatically. Could you help me by typing the details?",
        "saved": "Do not worry - I have saved your progress! You can continue anytime.",
        "complete": "All done! Here is your invoice.",
        "error_with_recovery": "Oops, something went wrong on my end. I have noted the issue and I am trying again..."
    }
```

---

## 6. ERROR HANDLING BY CATEGORY

### 6.1 Categorized Error Handling

```python
class ErrorHandler:
    """
    Different errors need different handling strategies
    """
    
    ERROR_CATEGORIES = {
        # Temporary - retry with backoff
        "TRANSIENT": [
            RateLimitError, TimeoutError, ConnectionError,
            ServiceUnavailable
        ],
        # Permanent - use fallback immediately
        "PERMANENT": [
            AuthenticationError, InvalidRequestError,
            FileTooLargeError, UnsupportedFormatError
        ],
        # Logic - ask user for clarification
        "LOGIC": [
            AmbiguousInputError, MissingRequiredFieldError,
            InvalidDataFormatError
        ],
        # System - alert admin, use emergency fallback
        "SYSTEM": [
            DatabaseError, OutOfMemoryError, DiskFullError
        ]
    }
    
    def handle_error(self, error, context):
        category = self.categorize_error(error)
        
        handlers = {
            "TRANSIENT": self._handle_transient_error,
            "PERMANENT": self._handle_permanent_error,
            "LOGIC": self._handle_logic_error,
            "SYSTEM": self._handle_system_error
        }
        
        handler = handlers.get(category, self._handle_unknown_error)
        return handler(error, context)
```

---

## 7. IMPLEMENTATION STACK RECOMMENDATION

### 7.1 Technology Stack

```yaml
# Infrastructure
Deployment: Docker + Docker Compose / Kubernetes
Message Queue: Redis (for both queue and state)
Database: PostgreSQL (invoices) + Redis (state)
File Storage: Local temp + S3 for persistence
Monitoring: Prometheus + Grafana + Sentry

# Application Layer
Language: Python 3.11+
Bot Framework: python-telegram-bot (v20+)
Task Queue: Celery with Redis broker
Web Framework: FastAPI (for webhooks)

# Document Processing
OCR: Google Vision API (primary), Tesseract (fallback)
PDF: pdfplumber, PyMuPDF, pdf2image
DOCX: python-docx, mammoth

# AI Layer
Models: OpenAI GPT-4, Anthropic Claude, Local LLM
Orchestration: LiteLLM for unified API
Validation: Pydantic for schema validation

# Resilience Patterns
Circuit Breaker: pybreaker
Retry: tenacity
Rate Limiting: slowapi / redis-rate-limit
```

### 7.2 Directory Structure

```
invoice_agent/
├── bot/
│   ├── handlers/
│   │   ├── commands.py      # /start, /help, /cancel
│   │   ├── messages.py      # Text message handler
│   │   └── documents.py     # File upload handler
│   ├── middleware/
│   │   ├── error_handler.py # Global error handling
│   │   └── rate_limiter.py  # Rate limiting
│   └── responses/
│       └── templates.py     # Message templates
├── core/
│   ├── state_manager.py     # Conversation state
│   ├── config.py            # Configuration
│   └── exceptions.py        # Custom exceptions
├── processing/
│   ├── document/
│   │   ├── image.py         # Image processing
│   │   ├── pdf.py           # PDF processing
│   │   ├── docx.py          # DOCX processing
│   │   └── factory.py       # Document router
│   └── ai/
│       ├── extractor.py     # Data extraction
│       ├── validator.py     # Data validation
│       └── models.py        # Model management
├── resilience/
│   ├── circuit_breakers.py  # Circuit breaker config
│   ├── retry_handler.py     # Retry logic
│   ├── fallback.py          # Fallback strategies
│   └── health_monitor.py    # Health checks
├── models/
│   ├── invoice.py           # Invoice data models
│   └── schema.py            # JSON schemas
├── tasks/
│   └── celery_tasks.py      # Background tasks
├── output/
│   ├── json_generator.py    # JSON output
│   └── pdf_generator.py     # PDF generation
├── tests/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── config.yaml
```

---

## 8. KEY DATA FIELDS & VALIDATION RULES

### 8.1 Invoice Schema (JSON Structure)

```json
{
  "invoice_id": "uuid",
  "version": "1.0",
  "status": "draft|pending|complete",
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  
  "contractor": {
    "name": {
      "value": "string",
      "confidence": 0.95,
      "source": "ai_extracted|user_provided|manual_entry",
      "verified": true
    },
    "address": {
      "street": "string",
      "city": "string",
      "postcode": "string",
      "confidence": 0.88
    },
    "email": {
      "value": "string",
      "validated": true,
      "confidence": 0.92
    },
    "utr_number": {
      "value": "10-digit string",
      "format_valid": true,
      "confidence": 0.85
    },
    "ni_number": {
      "value": "AB123456C format",
      "format_valid": true,
      "confidence": 0.80
    },
    "bank_details": {
      "account_name": "string",
      "account_number": "string",
      "sort_code": "string",
      "confidence": 0.90
    }
  },
  
  "invoice": {
    "number": {
      "value": "string",
      "auto_generated": false,
      "confidence": 0.95
    },
    "date": {
      "value": "YYYY-MM-DD",
      "confidence": 0.92
    },
    "work_start_date": {
      "value": "YYYY-MM-DD",
      "confidence": 0.88
    },
    "work_end_date": {
      "value": "YYYY-MM-DD",
      "confidence": 0.88
    }
  },
  
  "work_items": [
    {
      "id": "uuid",
      "property_address": {
        "value": "string",
        "confidence": 0.85
      },
      "plot_number": {
        "value": "string",
        "confidence": 0.75
      },
      "description": {
        "value": "string",
        "confidence": 0.90
      },
      "amount": {
        "value": 1234.56,
        "currency": "GBP",
        "confidence": 0.92
      }
    }
  ],
  
  "financials": {
    "subtotal": {
      "value": 1234.56,
      "calculated": true,
      "confidence": 0.98
    },
    "vat_rate": {
      "value": 20.0,
      "default_applied": false
    },
    "vat_amount": {
      "value": 246.91,
      "calculated": true,
      "confidence": 0.98
    },
    "cis_rate": {
      "value": 20,
      "options": [0, 20, 30]
    },
    "cis_deduction": {
      "value": 246.91,
      "calculated": true,
      "confidence": 0.98
    },
    "total_due": {
      "value": 1234.56,
      "calculated": true,
      "confidence": 0.99
    }
  },
  
  "operatives": [
    {
      "name": "string",
      "confidence": 0.85
    }
  ],
  
  "processing_metadata": {
    "extraction_method": "gpt4_vision",
    "fallback_used": false,
    "degradation_level": "full",
    "retry_count": 0,
    "processing_time_ms": 2345
  }
}
```

### 8.2 Validation Rules

```python
VALIDATION_RULES = {
    "utr_number": {
        "pattern": r"^\\d{10}$",
        "description": "10 digits only",
        "checksum": True  # HMRC validation
    },
    "ni_number": {
        "pattern": r"^[A-CEGHJ-PR-TW-Z]{2}\\d{6}[A-D]$",
        "description": "2 letters, 6 digits, 1 letter (no D, F, I, Q, U, V)",
        "checksum": False
    },
    "sort_code": {
        "pattern": r"^\\d{6}$",
        "description": "6 digits"
    },
    "account_number": {
        "pattern": r"^\\d{8}$",
        "description": "8 digits"
    },
    "email": {
        "pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
        "description": "Valid email format"
    },
    "postcode": {
        "pattern": r"^[A-Z]{1,2}\\d[A-Z\\d]? ?\\d[A-Z]{2}$",
        "description": "UK postcode format"
    },
    "financials": {
        "vat_calculation": "subtotal * vat_rate / 100",
        "cis_calculation": "subtotal * cis_rate / 100",
        "total_calculation": "subtotal + vat - cis",
        "tolerance": 0.01  # Allow 1p rounding difference
    }
}
```

---

## 9. SUMMARY: NEVER-FAIL PRINCIPLES

### 9.1 Core Principles

| Principle | Implementation |
|-----------|---------------|
| **Immediate ACK** | Telegram webhook returns 200ms within 200ms, processing is async |
| **State Persistence** | Every user action saved to Redis with TTL, survives restarts |
| **Retry with Backoff** | Exponential backoff for transient errors (max 5 retries) |
| **Circuit Breakers** | Prevent cascade failures, auto-recovery after timeout |
| **Fallback Chain** | Multiple strategies: AI -> Basic OCR -> Templates -> Manual |
| **Graceful Degradation** | Reduce functionality but never stop responding |
| **Dead Letter Queue** | Failed messages analyzed and retried automatically |
| **Health Monitoring** | Continuous checks with self-healing actions |
| **User Communication** | Always inform user what is happening |
| **Absolute Fallback** | Emergency response if all else fails |

### 9.2 Response Guarantee

```
┌────────────────────────────────────────────────────────────────┐
│                    RESPONSE GUARANTEE                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  NO MATTER WHAT HAPPENS:                                       │
│                                                                │
│  ✓ User always receives a response within 5 seconds            │
│  ✓ Conversation state is never lost                            │
│  ✓ Partial data is preserved and can be resumed                │
│  ✓ System can recover from any single point of failure         │
│  ✓ Multiple fallback strategies ensure completion              │
│  ✓ Admin is alerted for issues requiring manual intervention   │
│                                                                │
│  FAILURE MODES (all handled gracefully):                       │
│  • AI model unavailable -> Switch to backup model              │
│  • OCR fails -> Request manual input                           │
│  • Database down -> Queue for later processing                 │
│  • Network issues -> Retry with backoff                        │
│  • File corrupted -> Ask for re-upload                         │
│  • Out of memory -> Use simpler processing path                │
│  • Complete system failure -> Notify user, preserve state      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 10. NEXT STEPS FOR IMPLEMENTATION

1. **Set up infrastructure**: Docker, Redis, PostgreSQL
2. **Implement state manager**: Redis-backed conversation state
3. **Build bot layer**: Telegram webhook handlers
4. **Create document processors**: Image, PDF, DOCX with fallbacks
5. **Implement AI layer**: Multi-model extraction with circuit breakers
6. **Add resilience patterns**: Retry, fallback, health monitoring
7. **Build output generators**: JSON and PDF creation
8. **Write comprehensive tests**: Unit, integration, chaos testing
9. **Deploy with monitoring**: Prometheus, Grafana, alerting

---

*Document Version: 1.0*
*Architecture designed for resilient, self-healing conversational AI invoice processing*
