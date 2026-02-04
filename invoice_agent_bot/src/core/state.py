"""
Conversation State Machine

Manages conversation state for each user/chat.
Provides a clean interface for tracking conversation progress
and collecting invoice data incrementally.
"""

from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
import asyncio
from collections import defaultdict

from src.core.config import get_settings
from src.models.invoice import InvoiceData, CustomerInfo, InvoiceItem


class ConversationState(Enum):
    """
    States in the invoice creation conversation flow.
    
    The conversation progresses through these states as the user
    provides information for invoice creation.
    """
    IDLE = auto()                    # No active conversation
    AWAITING_DOCUMENT = auto()       # Waiting for document upload
    PROCESSING_DOCUMENT = auto()     # Document is being processed
    CONFIRMING_EXTRACTED_DATA = auto()  # Confirm AI-extracted data
    COLLECTING_CUSTOMER = auto()     # Collecting customer info
    COLLECTING_ITEMS = auto()        # Collecting line items
    COLLECTING_DATES = auto()        # Collecting issue/due dates
    COLLECTING_NOTES = auto()        # Collecting notes/terms
    REVIEWING = auto()               # Review complete invoice
    GENERATING = auto()              # Generating invoice file
    COMPLETED = auto()               # Invoice created successfully
    ERROR = auto()                   # Error state


@dataclass
class ConversationContext:
    """
    Context for a single conversation.
    
    Maintains all state and data for an ongoing invoice creation
    conversation with a user.
    """
    user_id: int
    chat_id: int
    state: ConversationState = ConversationState.IDLE
    
    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    
    # Invoice data being built
    invoice_data: Optional[InvoiceData] = field(default_factory=InvoiceData)
    
    # Document handling
    uploaded_document: Optional[Dict[str, Any]] = None
    extracted_data: Optional[Dict[str, Any]] = None
    
    # Conversation history
    messages: List[Dict[str, Any]] = field(default_factory=list)
    
    # State-specific data
    pending_field: Optional[str] = None
    temp_data: Dict[str, Any] = field(default_factory=dict)
    
    # Retry tracking for self-healing
    retry_count: int = 0
    last_error: Optional[str] = None
    
    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.utcnow()
    
    def is_expired(self, timeout_minutes: Optional[int] = None) -> bool:
        """Check if conversation has expired due to inactivity."""
        if timeout_minutes is None:
            timeout_minutes = get_settings().conversation_timeout_minutes
        timeout = timedelta(minutes=timeout_minutes)
        return datetime.utcnow() - self.last_activity > timeout
    
    def add_message(self, role: str, content: str, **kwargs) -> None:
        """Add a message to conversation history."""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow(),
            **kwargs
        })
        self.update_activity()
    
    def transition_to(self, new_state: ConversationState) -> None:
        """Transition to a new state."""
        old_state = self.state
        self.state = new_state
        self.update_activity()
        self.add_message(
            "system",
            f"State transition: {old_state.name} -> {new_state.name}",
            old_state=old_state.name,
            new_state=new_state.name
        )
    
    def record_error(self, error: str, recoverable: bool = True) -> None:
        """Record an error in the conversation."""
        self.last_error = error
        self.retry_count += 1
        self.add_message("system", f"Error: {error}", recoverable=recoverable)
        
        if not recoverable or self.retry_count >= get_settings().max_retry_attempts:
            self.transition_to(ConversationState.ERROR)
    
    def reset_retry_count(self) -> None:
        """Reset retry counter after successful operation."""
        self.retry_count = 0
        self.last_error = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize context to dictionary."""
        return {
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "state": self.state.name,
            "started_at": self.started_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "invoice_data": self.invoice_data.to_dict() if self.invoice_data else None,
            "uploaded_document": self.uploaded_document,
            "extracted_data": self.extracted_data,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
        }


class ConversationManager:
    """
    Manages all active conversations.
    
    Provides a centralized interface for creating, retrieving,
    updating, and cleaning up conversation contexts.
    """
    
    def __init__(self):
        """Initialize the conversation manager."""
        self._conversations: Dict[tuple, ConversationContext] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._state_handlers: Dict[ConversationState, List[Callable]] = defaultdict(list)
    
    async def start(self) -> None:
        """Start the conversation manager and cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def stop(self) -> None:
        """Stop the conversation manager and cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
    
    async def get_or_create(
        self, 
        user_id: int, 
        chat_id: int
    ) -> ConversationContext:
        """
        Get existing conversation or create a new one.
        
        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID
            
        Returns:
            ConversationContext: The conversation context
        """
        key = (user_id, chat_id)
        
        async with self._lock:
            if key not in self._conversations:
                self._conversations[key] = ConversationContext(
                    user_id=user_id,
                    chat_id=chat_id
                )
            return self._conversations[key]
    
    async def get(
        self, 
        user_id: int, 
        chat_id: int
    ) -> Optional[ConversationContext]:
        """
        Get existing conversation if it exists.
        
        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID
            
        Returns:
            Optional[ConversationContext]: The conversation context or None
        """
        key = (user_id, chat_id)
        return self._conversations.get(key)
    
    async def end_conversation(self, user_id: int, chat_id: int) -> bool:
        """
        End and remove a conversation.
        
        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID
            
        Returns:
            bool: True if conversation was removed
        """
        key = (user_id, chat_id)
        
        async with self._lock:
            if key in self._conversations:
                del self._conversations[key]
                return True
            return False
    
    async def reset_conversation(self, user_id: int, chat_id: int) -> ConversationContext:
        """
        Reset a conversation to initial state.
        
        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID
            
        Returns:
            ConversationContext: Fresh conversation context
        """
        key = (user_id, chat_id)
        
        async with self._lock:
            self._conversations[key] = ConversationContext(
                user_id=user_id,
                chat_id=chat_id
            )
            return self._conversations[key]
    
    async def update_state(
        self, 
        user_id: int, 
        chat_id: int, 
        new_state: ConversationState
    ) -> Optional[ConversationContext]:
        """
        Update the state of a conversation.
        
        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID
            new_state: New conversation state
            
        Returns:
            Optional[ConversationContext]: Updated context or None
        """
        context = await self.get(user_id, chat_id)
        if context:
            context.transition_to(new_state)
            # Trigger state handlers
            for handler in self._state_handlers.get(new_state, []):
                asyncio.create_task(handler(context))
        return context
    
    def register_state_handler(
        self, 
        state: ConversationState, 
        handler: Callable
    ) -> None:
        """
        Register a handler to be called on state transition.
        
        Args:
            state: State to watch
            handler: Async callable to invoke
        """
        self._state_handlers[state].append(handler)
    
    async def get_active_conversations(self) -> List[ConversationContext]:
        """
        Get all active conversations.
        
        Returns:
            List[ConversationContext]: List of active contexts
        """
        return list(self._conversations.values())
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get conversation statistics.
        
        Returns:
            Dict with conversation stats
        """
        stats = {
            "total_conversations": len(self._conversations),
            "by_state": {},
            "expired": 0,
        }
        
        for context in self._conversations.values():
            state_name = context.state.name
            stats["by_state"][state_name] = stats["by_state"].get(state_name, 0) + 1
            if context.is_expired():
                stats["expired"] += 1
        
        return stats
    
    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired conversations."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception:
                # Log but don't stop the cleanup loop
                await asyncio.sleep(5)
    
    async def _cleanup_expired(self) -> int:
        """
        Remove expired conversations.
        
        Returns:
            int: Number of conversations removed
        """
        expired_keys = []
        
        for key, context in self._conversations.items():
            if context.is_expired():
                expired_keys.append(key)
        
        async with self._lock:
            for key in expired_keys:
                del self._conversations[key]
        
        return len(expired_keys)


# Global conversation manager instance
_conversation_manager: Optional[ConversationManager] = None


def get_conversation_manager() -> ConversationManager:
    """
    Get the global conversation manager instance.
    
    Returns:
        ConversationManager: Singleton instance
    """
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
    return _conversation_manager


async def initialize_conversations() -> None:
    """Initialize the conversation manager."""
    manager = get_conversation_manager()
    await manager.start()


async def shutdown_conversations() -> None:
    """Shutdown the conversation manager."""
    manager = get_conversation_manager()
    await manager.stop()
