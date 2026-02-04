"""
================================================================================
DEAD LETTER QUEUE SYSTEM
================================================================================
Queue for failed operations with automatic retry and manual inspection

Features:
- Automatic retry with exponential backoff
- Priority-based processing
- Persistence to disk
- Manual inspection and replay
- Statistics and monitoring
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List, Callable, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
import uuid
import aiofiles
from pathlib import Path

logger = logging.getLogger(__name__)


class DLQItemStatus(Enum):
    """Status of items in dead letter queue"""
    PENDING = auto()
    PROCESSING = auto()
    RETRYING = auto()
    FAILED = auto()
    SUCCESS = auto()
    DISCARDED = auto()


@dataclass
class DLQItem:
    """Item in the dead letter queue"""
    id: str
    operation_type: str
    payload: Dict[str, Any]
    error_info: Dict[str, Any]
    status: DLQItemStatus
    created_at: datetime
    updated_at: datetime
    retry_count: int = 0
    max_retries: int = 5
    next_retry_at: Optional[datetime] = None
    last_error: Optional[str] = None
    processing_history: List[Dict] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    priority: int = 5  # 1 = highest, 10 = lowest
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "operation_type": self.operation_type,
            "payload": self.payload,
            "error_info": self.error_info,
            "status": self.status.name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "last_error": self.last_error,
            "processing_history": self.processing_history,
            "tags": self.tags,
            "priority": self.priority,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'DLQItem':
        return cls(
            id=data["id"],
            operation_type=data["operation_type"],
            payload=data["payload"],
            error_info=data["error_info"],
            status=DLQItemStatus[data["status"]],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 5),
            next_retry_at=datetime.fromisoformat(data["next_retry_at"]) if data.get("next_retry_at") else None,
            last_error=data.get("last_error"),
            processing_history=data.get("processing_history", []),
            tags=data.get("tags", []),
            priority=data.get("priority", 5),
        )
    
    def mark_processing(self):
        """Mark item as being processed"""
        self.status = DLQItemStatus.PROCESSING
        self.updated_at = datetime.now()
        self.processing_history.append({
            "action": "processing_started",
            "timestamp": datetime.now().isoformat(),
        })
    
    def mark_retry(self, delay_seconds: float = 60):
        """Mark item for retry"""
        self.retry_count += 1
        self.status = DLQItemStatus.RETRYING
        self.updated_at = datetime.now()
        self.next_retry_at = datetime.now() + timedelta(seconds=delay_seconds)
        self.processing_history.append({
            "action": "scheduled_retry",
            "retry_count": self.retry_count,
            "next_retry": self.next_retry_at.isoformat(),
        })
    
    def mark_success(self):
        """Mark item as successfully processed"""
        self.status = DLQItemStatus.SUCCESS
        self.updated_at = datetime.now()
        self.processing_history.append({
            "action": "success",
            "timestamp": datetime.now().isoformat(),
        })
    
    def mark_failed(self, error: str):
        """Mark item as permanently failed"""
        self.status = DLQItemStatus.FAILED
        self.last_error = error
        self.updated_at = datetime.now()
        self.processing_history.append({
            "action": "failed",
            "error": error,
            "timestamp": datetime.now().isoformat(),
        })
    
    def mark_discarded(self, reason: str):
        """Mark item as discarded"""
        self.status = DLQItemStatus.DISCARDED
        self.updated_at = datetime.now()
        self.processing_history.append({
            "action": "discarded",
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        })
    
    def is_ready_for_retry(self) -> bool:
        """Check if item is ready for retry"""
        if self.status not in [DLQItemStatus.PENDING, DLQItemStatus.RETRYING]:
            return False
        if self.retry_count >= self.max_retries:
            return False
        if self.next_retry_at and datetime.now() < self.next_retry_at:
            return False
        return True


class DeadLetterQueue:
    """
    Dead Letter Queue for failed operations
    
    Features:
    - Automatic retry with exponential backoff
    - Priority-based processing
    - Persistence to disk
    - Manual inspection and replay
    - Statistics and monitoring
    """
    
    def __init__(self, storage_path: str = "./dlq_storage"):
        self._storage_path = Path(storage_path)
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._items: Dict[str, DLQItem] = {}
        self._handlers: Dict[str, Callable] = {}
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None
        self._retry_interval = 30  # Seconds between retry checks
        self._stats = {
            "total_enqueued": 0,
            "total_success": 0,
            "total_failed": 0,
            "total_discarded": 0,
        }
        
    async def initialize(self):
        """Initialize DLQ and load persisted items"""
        await self._load_items()
        
    async def _load_items(self):
        """Load persisted items from disk"""
        for file_path in self._storage_path.glob("*.json"):
            try:
                async with aiofiles.open(file_path, 'r') as f:
                    content = await f.read()
                    data = json.loads(content)
                    item = DLQItem.from_dict(data)
                    self._items[item.id] = item
            except Exception as e:
                logger.error(f"Failed to load DLQ item from {file_path}: {e}")
        
        logger.info(f"Loaded {len(self._items)} items from DLQ")
    
    async def _save_item(self, item: DLQItem):
        """Persist item to disk"""
        file_path = self._storage_path / f"{item.id}.json"
        try:
            async with aiofiles.open(file_path, 'w') as f:
                await f.write(json.dumps(item.to_dict(), indent=2))
        except Exception as e:
            logger.error(f"Failed to save DLQ item: {e}")
    
    async def enqueue(
        self,
        operation_type: str,
        payload: Dict[str, Any],
        error: Exception,
        max_retries: int = 5,
        priority: int = 5,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        Add a failed operation to the DLQ
        
        Returns:
            Item ID for tracking
        """
        item_id = str(uuid.uuid4())
        
        item = DLQItem(
            id=item_id,
            operation_type=operation_type,
            payload=payload,
            error_info={
                "error_type": type(error).__name__,
                "error_message": str(error),
                "timestamp": datetime.now().isoformat(),
            },
            status=DLQItemStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            max_retries=max_retries,
            priority=priority,
            tags=tags or [],
        )
        
        self._items[item_id] = item
        await self._save_item(item)
        
        self._stats["total_enqueued"] += 1
        
        logger.info(f"Enqueued failed operation: {operation_type} (ID: {item_id})")
        
        return item_id
    
    def register_handler(self, operation_type: str, handler: Callable):
        """Register a handler for an operation type"""
        self._handlers[operation_type] = handler
        logger.info(f"Registered DLQ handler for {operation_type}")
    
    async def start_processor(self):
        """Start the background retry processor"""
        if self._running:
            return
        
        self._running = True
        self._processor_task = asyncio.create_task(self._processor_loop())
        logger.info("DLQ processor started")
    
    async def stop_processor(self):
        """Stop the background retry processor"""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logger.info("DLQ processor stopped")
    
    async def _processor_loop(self):
        """Main processor loop for retrying items"""
        while self._running:
            try:
                await self._process_ready_items()
                await asyncio.sleep(self._retry_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in DLQ processor loop: {e}")
                await asyncio.sleep(self._retry_interval)
    
    async def _process_ready_items(self):
        """Process items that are ready for retry"""
        ready_items = [
            item for item in self._items.values()
            if item.is_ready_for_retry()
        ]
        
        # Sort by priority (lower = higher priority)
        ready_items.sort(key=lambda x: x.priority)
        
        for item in ready_items:
            await self._process_item(item)
    
    async def _process_item(self, item: DLQItem):
        """Process a single DLQ item"""
        handler = self._handlers.get(item.operation_type)
        
        if not handler:
            logger.warning(f"No handler for operation type: {item.operation_type}")
            item.mark_discarded("No handler registered")
            await self._save_item(item)
            return
        
        item.mark_processing()
        await self._save_item(item)
        
        try:
            # Call the handler
            result = await handler(item.payload)
            
            if result:
                item.mark_success()
                self._stats["total_success"] += 1
                logger.info(f"Successfully processed DLQ item {item.id}")
            else:
                # Handler returned False, treat as failure
                raise Exception("Handler returned False")
            
        except Exception as e:
            error_msg = str(e)
            item.last_error = error_msg
            
            if item.retry_count < item.max_retries:
                # Schedule retry with exponential backoff
                delay = min(60 * (2 ** item.retry_count), 3600)  # Max 1 hour
                item.mark_retry(delay)
                logger.warning(f"DLQ item {item.id} failed, retrying in {delay}s")
            else:
                item.mark_failed(error_msg)
                self._stats["total_failed"] += 1
                logger.error(f"DLQ item {item.id} permanently failed: {error_msg}")
        
        await self._save_item(item)
    
    async def retry_item(self, item_id: str) -> bool:
        """Manually retry a specific item"""
        item = self._items.get(item_id)
        if not item:
            return False
        
        item.retry_count = 0
        item.status = DLQItemStatus.PENDING
        item.next_retry_at = None
        await self._save_item(item)
        
        # Process immediately
        await self._process_item(item)
        return True
    
    async def discard_item(self, item_id: str, reason: str) -> bool:
        """Manually discard an item"""
        item = self._items.get(item_id)
        if not item:
            return False
        
        item.mark_discarded(reason)
        await self._save_item(item)
        self._stats["total_discarded"] += 1
        return True
    
    def get_item(self, item_id: str) -> Optional[DLQItem]:
        """Get a specific item"""
        return self._items.get(item_id)
    
    def get_all_items(
        self,
        status: Optional[DLQItemStatus] = None,
        operation_type: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[DLQItem]:
        """Get items with optional filtering"""
        items = list(self._items.values())
        
        if status:
            items = [i for i in items if i.status == status]
        
        if operation_type:
            items = [i for i in items if i.operation_type == operation_type]
        
        if tags:
            items = [i for i in items if any(t in i.tags for t in tags)]
        
        # Sort by priority and creation time
        items.sort(key=lambda x: (x.priority, x.created_at))
        
        return items
    
    def get_stats(self) -> Dict[str, Any]:
        """Get DLQ statistics"""
        status_counts = {}
        for item in self._items.values():
            status_name = item.status.name
            status_counts[status_name] = status_counts.get(status_name, 0) + 1
        
        return {
            **self._stats,
            "current_items": len(self._items),
            "status_breakdown": status_counts,
            "handlers_registered": list(self._handlers.keys()),
        }
    
    async def cleanup_old_items(self, max_age_days: int = 30):
        """Clean up old successful/discarded items"""
        cutoff = datetime.now() - timedelta(days=max_age_days)
        
        to_remove = []
        for item_id, item in self._items.items():
            if item.status in [DLQItemStatus.SUCCESS, DLQItemStatus.DISCARDED]:
                if item.updated_at < cutoff:
                    to_remove.append(item_id)
        
        for item_id in to_remove:
            del self._items[item_id]
            file_path = self._storage_path / f"{item_id}.json"
            try:
                file_path.unlink()
            except:
                pass
        
        logger.info(f"Cleaned up {len(to_remove)} old DLQ items")


# Convenience function for common operations
async def enqueue_with_dlq(
    dlq: DeadLetterQueue,
    operation_type: str,
    operation: Callable,
    payload: Dict[str, Any],
    max_retries: int = 5,
    priority: int = 5
) -> bool:
    """
    Execute an operation with automatic DLQ fallback
    
    Returns True if successful, False if enqueued to DLQ
    """
    try:
        result = await operation(**payload)
        return True
    except Exception as e:
        await dlq.enqueue(
            operation_type=operation_type,
            payload=payload,
            error=e,
            max_retries=max_retries,
            priority=priority
        )
        return False
