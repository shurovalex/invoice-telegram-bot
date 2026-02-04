# Recovery Flow Diagrams

This document contains visual diagrams of all recovery flows in the self-healing invoice agent system.

## Table of Contents

1. [Main Recovery Flow](#main-recovery-flow)
2. [Circuit Breaker State Flow](#circuit-breaker-state-flow)
3. [AI Model Fallback Chain](#ai-model-fallback-chain)
4. [State Persistence Layers](#state-persistence-layers)
5. [Dead Letter Queue Flow](#dead-letter-queue-flow)
6. [Error Classification Flow](#error-classification-flow)
7. [System Architecture](#system-architecture)
8. [Document Processing Recovery Flow](#document-processing-recovery-flow)

---

## Main Recovery Flow

The main recovery flow shows how every user request is processed with multiple layers of protection:

```mermaid
flowchart TD
    A[User Request] --> B{System Healthy?}
    B -->|Yes| C[Process Normally]
    B -->|No| D[Classify Error]
    
    C --> E{Success?}
    E -->|Yes| F[Return Result]
    E -->|No| D
    
    D --> G{Retryable?}
    G -->|Yes| H[Retry with Backoff]
    G -->|No| I[Skip to Fallback]
    
    H --> J{Retry Success?}
    J -->|Yes| F
    J -->|No| K{Retries Exhausted?}
    K -->|No| H
    K -->|Yes| I
    
    I --> L{Fallback Available?}
    L -->|Yes| M[Use Fallback Model]
    L -->|No| N[Degraded Mode]
    
    M --> O{Fallback Success?}
    O -->|Yes| F
    O -->|No| N
    
    N --> P[Rule-Based Processing]
    P --> Q{Degraded Success?}
    Q -->|Yes| F
    Q -->|No| R[Static Response]
    
    R --> S[Enqueue to DLQ]
    S --> F
    
    F --> T[Update State]
    T --> U[Return to User]
```

**Key Points:**
- Every request goes through multiple recovery layers
- User always receives a response (never crashes)
- Failed operations are queued for later retry
- State is preserved throughout the process

---

## Circuit Breaker State Flow

The circuit breaker prevents cascade failures by temporarily blocking calls to failing services:

```mermaid
stateDiagram-v2
    [*] --> CLOSED: Initialize
    
    CLOSED --> OPEN: Failures >= Threshold
    CLOSED --> CLOSED: Success
    
    OPEN --> HALF_OPEN: Timeout Expired
    OPEN --> OPEN: Request Rejected
    
    HALF_OPEN --> CLOSED: Success >= Threshold
    HALF_OPEN --> OPEN: Any Failure
    
    note right of CLOSED
        Normal operation
        All requests pass through
    end note
    
    note right of OPEN
        Failure threshold reached
        Requests blocked
        Returns fallback response
    end note
    
    note right of HALF_OPEN
        Testing recovery
        Limited requests allowed
    end note
```

**States:**
- **CLOSED**: Normal operation, all requests pass through
- **OPEN**: Service is failing, requests are blocked
- **HALF_OPEN**: Testing if service has recovered

**Transitions:**
- CLOSED → OPEN: After N consecutive failures
- OPEN → HALF_OPEN: After recovery timeout
- HALF_OPEN → CLOSED: After M consecutive successes
- HALF_OPEN → OPEN: Any failure

---

## AI Model Fallback Chain

Multi-tier fallback system for AI model failures:

```mermaid
flowchart LR
    A[User Request] --> B{Primary Model<br/>GPT-4/Claude-3}
    
    B -->|Success| Z[Return Response]
    B -->|Timeout| C{Secondary Model<br/>GPT-3.5}
    B -->|Rate Limit| C
    B -->|Error| C
    
    C -->|Success| Z
    C -->|Failure| D{Tertiary Model<br/>Local LLM}
    
    D -->|Success| Z
    D -->|Failure| E[Rule-Based<br/>Processing]
    
    E -->|Success| Z
    E -->|Failure| F[Static<br/>Response]
    
    F --> Z
    
    Z --> G[Log Model Used]
    Z --> H[Update Stats]
```

**Fallback Chain:**
1. **Primary**: GPT-4, Claude-3 (best quality)
2. **Secondary**: GPT-3.5 (good quality, faster)
3. **Tertiary**: Local LLM (offline capable)
4. **Rule-Based**: Pattern matching (no AI)
5. **Static**: Pre-written responses (never fails)

---

## State Persistence Layers

Multi-layer state persistence for crash recovery:

```mermaid
flowchart TD
    A[Save State] --> B[Layer 1: Memory]
    B --> C{Success?}
    C -->|Yes| D[Fast Response]
    C -->|No| E[Layer 2: File]
    
    D --> F{Periodic Sync}
    F -->|Yes| G[Layer 2: File]
    F -->|No| H[Continue]
    
    E --> I{Success?}
    I -->|Yes| J[File Persisted]
    I -->|No| K[Layer 3: Redis]
    
    G --> L{Success?}
    L -->|Yes| M[File Synced]
    L -->|No| N[Retry Later]
    
    K --> O{Success?}
    O -->|Yes| P[Redis Persisted]
    O -->|No| Q[Log Error]
    
    J --> R[Recovery Ready]
    M --> R
    P --> R
    Q --> S[Degraded Mode]
    
    H --> T[Next Operation]
    R --> T
    S --> T
```

**Persistence Layers:**
1. **Memory**: Fastest, volatile (primary write)
2. **File**: Survives restarts (periodic sync)
3. **Redis**: Distributed, fast (optional)

**Strategy:**
- Write to memory immediately for speed
- Sync to file periodically (every 60s)
- Use Redis if available for distributed setups

---

## Dead Letter Queue Flow

Queue for failed operations with automatic retry:

```mermaid
flowchart TD
    A[Operation Fails] --> B[Enqueue to DLQ]
    B --> C[Persist to Disk]
    C --> D{Immediate Retry?}
    
    D -->|Yes| E[Try Now]
    D -->|No| F[Schedule Retry]
    
    E --> G{Success?}
    G -->|Yes| H[Mark Success]
    G -->|No| I{Retry Count < Max?}
    
    F --> J[Wait Interval]
    J --> K[Background Processor]
    K --> L{Item Ready?}
    L -->|Yes| M[Process Item]
    L -->|No| J
    
    M --> N{Handler Success?}
    N -->|Yes| H
    N -->|No| O{Retry Count < Max?}
    
    I -->|Yes| P[Schedule Next Retry]
    I -->|No| Q[Mark Failed]
    
    O -->|Yes| P
    O -->|No| Q
    
    P --> R[Calculate Backoff]
    R --> F
    
    H --> S[Notify User]
    Q --> T[Alert Admin]
```

**Features:**
- Automatic retry with exponential backoff
- Priority-based processing
- Persistent storage
- Manual inspection and replay

---

## Error Classification Flow

How errors are classified for targeted recovery:

```mermaid
flowchart TD
    A[Error Occurs] --> B[Extract Error Info]
    B --> C{Match Known Pattern?}
    
    C -->|Yes| D[Classify by Pattern]
    C -->|No| E[Classify by Type]
    
    D --> F[Determine Category]
    E --> F
    
    F --> G{Retryable?}
    G -->|Yes| H[Set Retry Params]
    G -->|No| I[Set Non-Retryable]
    
    H --> J[Calculate Max Retries]
    I --> K[Set Fallback Strategy]
    
    J --> L[Calculate Base Delay]
    K --> M[Generate User Message]
    
    L --> N[Determine Log Level]
    M --> O[Return Classification]
    N --> O
    
    O --> P[Execute Recovery]
```

**Classification Output:**
- Error category (AI model, database, network, etc.)
- Severity level (critical, high, medium, low)
- Retryability (yes/no)
- Retry parameters (max retries, delays)
- Fallback strategy
- User-friendly message

---

## System Architecture

Complete system architecture overview:

```mermaid
flowchart TB
    subgraph User_Layer["User Layer"]
        U[Telegram User]
    end
    
    subgraph Agent_Layer["Self-Healing Agent Layer"]
        A[Message Handler]
        B[Error Classifier]
        C[User Message Manager]
    end
    
    subgraph Recovery_Layer["Recovery Layer"]
        D[Retry Handler]
        E[Circuit Breaker]
        F[AI Fallback Chain]
        G[Degraded Mode Handler]
    end
    
    subgraph Persistence_Layer["Persistence Layer"]
        H[Memory Cache]
        I[File Storage]
        J[Redis]
    end
    
    subgraph External_Services["External Services"]
        K[OpenAI API]
        L[Anthropic API]
        M[Database]
        N[File Services]
        O[Webhooks]
    end
    
    subgraph Monitoring_Layer["Monitoring Layer"]
        P[Dead Letter Queue]
        Q[Health Monitor]
        R[Metrics Collector]
    end
    
    U --> A
    A --> B
    A --> C
    
    B --> D
    B --> E
    
    D --> F
    E --> F
    F --> G
    
    F --> K
    F --> L
    G --> H
    
    H --> I
    I --> J
    
    A --> M
    A --> N
    A --> O
    
    D --> P
    E --> Q
    F --> R
    
    P --> Q
    Q --> R
```

---

## Document Processing Recovery Flow

Specialized recovery flow for document processing:

```mermaid
flowchart TD
    A[User Uploads Document] --> B[Download File]
    
    B --> C{Download Success?}
    C -->|No| D[Retry Download]
    C -->|Yes| E[Validate File]
    
    D --> F{Retry Success?}
    F -->|Yes| E
    F -->|No| G[Request Re-upload]
    
    E --> H{Valid Format?}
    H -->|No| I[Format Error Message]
    H -->|Yes| J[Extract Text/OCR]
    
    I --> G
    
    J --> K{OCR Success?}
    K -->|Yes| L[AI Extraction]
    K -->|No| M[Retry OCR]
    
    M --> N{Retry Success?}
    N -->|Yes| L
    N -->|No| O[Rule-Based Extraction]
    
    L --> P{AI Success?}
    P -->|Yes| Q[Validate Data]
    P -->|No| R{Fallback Model?}
    
    R -->|Yes| S[Try Fallback AI]
    R -->|No| O
    
    S --> T{Fallback Success?}
    T -->|Yes| Q
    T -->|No| O
    
    O --> Q
    
    Q --> U{Data Valid?}
    U -->|Yes| V[Save to Database]
    U -->|No| W[Request Clarification]
    
    V --> X{Save Success?}
    X -->|Yes| Y[Confirm to User]
    X -->|No| Z[Queue to DLQ]
    
    Z --> Y
    W --> Y
    G --> AA[Help Message]
    AA --> Y
```

**Recovery Points:**
1. Download retry (3 attempts)
2. OCR retry (3 attempts)
3. AI fallback chain
4. Rule-based extraction
5. DLQ for database failures

---

## Summary

The self-healing system provides:

1. **Never-Fail Guarantee**: Users always receive a response
2. **Layered Recovery**: Multiple fallback strategies
3. **Automatic Retry**: Intelligent retry with backoff
4. **Circuit Breakers**: Prevent cascade failures
5. **State Persistence**: Survive crashes and restarts
6. **Dead Letter Queue**: Handle and retry failed operations
7. **User-Friendly Messages**: No technical jargon exposed
