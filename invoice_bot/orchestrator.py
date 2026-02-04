#!/usr/bin/env python3
"""
Orchestrator Agent - The brain of the self-healing system.

This agent:
1. Receives ALL incoming messages
2. Delegates tasks to worker agents with TIMEOUTS
3. Tracks all active tasks
4. Triggers recovery when failures detected
5. Ensures users ALWAYS get a response
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Callable, Any
from telegram import Update, Bot

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Status of a tracked task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RECOVERED = "recovered"


@dataclass
class TrackedTask:
    """A task being tracked by the orchestrator."""
    task_id: str
    chat_id: int
    user_id: int
    task_type: str  # "document_processing", "invoice_generation", etc.
    started_at: float
    timeout_seconds: float = 30.0
    status: TaskStatus = TaskStatus.PENDING
    message_id: Optional[int] = None  # Processing message to delete on completion
    retry_count: int = 0
    max_retries: int = 3
    error: Optional[str] = None
    result: Any = None

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.started_at

    @property
    def is_timed_out(self) -> bool:
        return self.elapsed_seconds > self.timeout_seconds and self.status == TaskStatus.RUNNING

    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries


class Orchestrator:
    """
    Central orchestrator that manages all bot operations.

    Key responsibilities:
    - Track all active tasks
    - Enforce timeouts on all operations
    - Provide fallback responses when tasks fail
    - Ensure users ALWAYS get feedback
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.active_tasks: Dict[str, TrackedTask] = {}
        self.task_history: Dict[str, TrackedTask] = {}
        self._lock = asyncio.Lock()

        # Default timeouts for different task types
        self.timeouts = {
            "document_processing": 45.0,  # OCR can be slow
            "invoice_generation": 30.0,
            "ai_extraction": 60.0,
            "file_download": 15.0,
            "default": 30.0,
        }

        # Fallback messages for different failure types
        self.fallback_messages = {
            "document_processing": (
                "⚠️ **Document Processing Issue**\n\n"
                "I'm having trouble reading your document. This can happen with:\n"
                "• Handwritten text\n"
                "• Poor image quality\n"
                "• Complex layouts\n\n"
                "**What you can do:**\n"
                "1. Try uploading a clearer image\n"
                "2. Use /chat to enter details manually\n"
                "3. Send /start to restart\n\n"
                "_I'll keep trying in the background and notify you if successful._"
            ),
            "timeout": (
                "⏱️ **Processing Taking Longer Than Expected**\n\n"
                "Your request is taking longer than usual. "
                "I'm still working on it and will notify you when done.\n\n"
                "You can:\n"
                "• Wait for my response\n"
                "• Send /cancel to stop and try again\n"
                "• Send /chat to enter details manually"
            ),
            "default": (
                "❌ **Something went wrong**\n\n"
                "I encountered an issue processing your request. "
                "Please try again or use /help for assistance."
            ),
        }

    async def start_task(
        self,
        chat_id: int,
        user_id: int,
        task_type: str,
        processing_message_id: Optional[int] = None
    ) -> TrackedTask:
        """Start tracking a new task."""
        task_id = str(uuid.uuid4())[:8]
        timeout = self.timeouts.get(task_type, self.timeouts["default"])

        task = TrackedTask(
            task_id=task_id,
            chat_id=chat_id,
            user_id=user_id,
            task_type=task_type,
            started_at=time.time(),
            timeout_seconds=timeout,
            status=TaskStatus.RUNNING,
            message_id=processing_message_id,
        )

        async with self._lock:
            self.active_tasks[task_id] = task

        logger.info(f"Started task {task_id} ({task_type}) for user {user_id}")
        return task

    async def complete_task(self, task_id: str, result: Any = None):
        """Mark a task as completed."""
        async with self._lock:
            if task_id in self.active_tasks:
                task = self.active_tasks.pop(task_id)
                task.status = TaskStatus.COMPLETED
                task.result = result
                self.task_history[task_id] = task
                logger.info(f"Task {task_id} completed in {task.elapsed_seconds:.1f}s")

    async def fail_task(self, task_id: str, error: str):
        """Mark a task as failed."""
        async with self._lock:
            if task_id in self.active_tasks:
                task = self.active_tasks.pop(task_id)
                task.status = TaskStatus.FAILED
                task.error = error
                self.task_history[task_id] = task
                logger.error(f"Task {task_id} failed: {error}")

    async def execute_with_timeout(
        self,
        coro: Callable,
        chat_id: int,
        user_id: int,
        task_type: str,
        processing_message_id: Optional[int] = None,
        fallback_handler: Optional[Callable] = None,
    ) -> Any:
        """
        Execute a coroutine with timeout tracking and automatic recovery.

        This is the CORE method - it ensures:
        1. Task is tracked
        2. Timeout is enforced
        3. User gets feedback on timeout
        4. Fallback is triggered if available
        """
        task = await self.start_task(chat_id, user_id, task_type, processing_message_id)

        try:
            # Execute with timeout
            timeout = self.timeouts.get(task_type, self.timeouts["default"])
            result = await asyncio.wait_for(coro, timeout=timeout)
            await self.complete_task(task.task_id, result)
            return result

        except asyncio.TimeoutError:
            logger.warning(f"Task {task.task_id} ({task_type}) timed out after {timeout}s")
            task.status = TaskStatus.TIMEOUT

            # Send timeout feedback to user
            await self._send_timeout_feedback(chat_id, task_type)

            # Try fallback if available
            if fallback_handler:
                try:
                    logger.info(f"Attempting fallback for task {task.task_id}")
                    result = await fallback_handler()
                    task.status = TaskStatus.RECOVERED
                    await self.complete_task(task.task_id, result)
                    return result
                except Exception as e:
                    logger.error(f"Fallback failed for task {task.task_id}: {e}")

            await self.fail_task(task.task_id, f"Timeout after {timeout}s")
            raise

        except Exception as e:
            logger.error(f"Task {task.task_id} error: {e}")
            await self.fail_task(task.task_id, str(e))

            # Send error feedback to user
            await self._send_error_feedback(chat_id, task_type, str(e))
            raise

    async def _send_timeout_feedback(self, chat_id: int, task_type: str):
        """Send user-friendly timeout message."""
        try:
            message = self.fallback_messages.get(
                task_type,
                self.fallback_messages["timeout"]
            )
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send timeout feedback: {e}")

    async def _send_error_feedback(self, chat_id: int, task_type: str, error: str):
        """Send user-friendly error message."""
        try:
            message = self.fallback_messages.get(
                task_type,
                self.fallback_messages["default"]
            )
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send error feedback: {e}")

    async def get_stuck_tasks(self) -> list[TrackedTask]:
        """Get all tasks that appear to be stuck."""
        stuck = []
        async with self._lock:
            for task in self.active_tasks.values():
                if task.is_timed_out:
                    stuck.append(task)
        return stuck

    async def recover_stuck_task(self, task: TrackedTask):
        """Attempt to recover a stuck task."""
        logger.info(f"Attempting recovery for stuck task {task.task_id}")

        # Send feedback to user
        await self._send_timeout_feedback(task.chat_id, task.task_type)

        # Mark as failed
        await self.fail_task(task.task_id, "Stuck task recovered by watchdog")

        # Clean up processing message if exists
        if task.message_id:
            try:
                await self.bot.delete_message(task.chat_id, task.message_id)
            except Exception:
                pass

    def get_health_status(self) -> Dict:
        """Get health status for monitoring."""
        return {
            "active_tasks": len(self.active_tasks),
            "completed_tasks": len([t for t in self.task_history.values() if t.status == TaskStatus.COMPLETED]),
            "failed_tasks": len([t for t in self.task_history.values() if t.status == TaskStatus.FAILED]),
            "timeout_tasks": len([t for t in self.task_history.values() if t.status == TaskStatus.TIMEOUT]),
            "recovered_tasks": len([t for t in self.task_history.values() if t.status == TaskStatus.RECOVERED]),
            "tasks": [
                {
                    "task_id": t.task_id,
                    "type": t.task_type,
                    "status": t.status.value,
                    "elapsed": t.elapsed_seconds,
                    "timeout": t.timeout_seconds,
                }
                for t in self.active_tasks.values()
            ]
        }
