#!/usr/bin/env python3
"""
Watchdog/Observer Agent - The guardian of the self-healing system.

This agent:
1. Runs continuously in the background
2. Monitors ALL active tasks
3. Detects stuck/timed-out operations
4. Triggers automatic recovery
5. Sends user feedback without human intervention
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from invoice_bot.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class Watchdog:
    """
    Background watchdog that monitors system health.

    Key responsibilities:
    - Check for stuck tasks every N seconds
    - Trigger automatic recovery for stuck tasks
    - Log system health metrics
    - Ensure no user is left waiting without feedback
    """

    def __init__(
        self,
        orchestrator: "Orchestrator",
        check_interval: float = 5.0,  # Check every 5 seconds
        stuck_threshold: float = 1.5,  # Task is stuck if elapsed > timeout * 1.5
    ):
        self.orchestrator = orchestrator
        self.check_interval = check_interval
        self.stuck_threshold = stuck_threshold
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Statistics
        self.stats = {
            "checks_performed": 0,
            "stuck_tasks_found": 0,
            "recoveries_triggered": 0,
            "last_check": None,
            "started_at": None,
        }

    async def start(self):
        """Start the watchdog background task."""
        if self._running:
            logger.warning("Watchdog already running")
            return

        self._running = True
        self.stats["started_at"] = datetime.now().isoformat()
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"Watchdog started - checking every {self.check_interval}s")

    async def stop(self):
        """Stop the watchdog."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Watchdog stopped")

    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_health()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watchdog error: {e}", exc_info=True)
                await asyncio.sleep(self.check_interval)

    async def _check_health(self):
        """Perform health check and recovery."""
        self.stats["checks_performed"] += 1
        self.stats["last_check"] = datetime.now().isoformat()

        # Get all stuck tasks
        stuck_tasks = await self.orchestrator.get_stuck_tasks()

        if stuck_tasks:
            self.stats["stuck_tasks_found"] += len(stuck_tasks)
            logger.warning(f"Watchdog found {len(stuck_tasks)} stuck task(s)")

            for task in stuck_tasks:
                # Check if task is truly stuck (beyond threshold)
                if task.elapsed_seconds > task.timeout_seconds * self.stuck_threshold:
                    logger.info(
                        f"Recovering stuck task {task.task_id}: "
                        f"type={task.task_type}, "
                        f"elapsed={task.elapsed_seconds:.1f}s, "
                        f"timeout={task.timeout_seconds}s"
                    )
                    await self._recover_task(task)
                    self.stats["recoveries_triggered"] += 1

        # Log health status periodically
        if self.stats["checks_performed"] % 12 == 0:  # Every minute
            health = self.orchestrator.get_health_status()
            logger.info(
                f"System health: active={health['active_tasks']}, "
                f"completed={health['completed_tasks']}, "
                f"failed={health['failed_tasks']}, "
                f"recovered={health['recovered_tasks']}"
            )

    async def _recover_task(self, task):
        """Attempt to recover a stuck task."""
        try:
            await self.orchestrator.recover_stuck_task(task)
            logger.info(f"Successfully recovered task {task.task_id}")
        except Exception as e:
            logger.error(f"Failed to recover task {task.task_id}: {e}")

    def get_stats(self) -> dict:
        """Get watchdog statistics."""
        return {
            **self.stats,
            "running": self._running,
            "orchestrator_health": self.orchestrator.get_health_status(),
        }


class HealthMonitor:
    """
    Extended health monitoring with alerts and metrics.

    This can be used for:
    - External health check endpoints
    - Alerting systems
    - Metrics collection
    """

    def __init__(self, orchestrator: "Orchestrator", watchdog: Watchdog):
        self.orchestrator = orchestrator
        self.watchdog = watchdog

    def is_healthy(self) -> bool:
        """Check if the system is healthy."""
        health = self.orchestrator.get_health_status()

        # System is unhealthy if:
        # - More than 5 active tasks (potential backlog)
        # - Any task running for more than 2x its timeout
        if health["active_tasks"] > 5:
            return False

        for task in health["tasks"]:
            if task["elapsed"] > task["timeout"] * 2:
                return False

        return True

    def get_full_status(self) -> dict:
        """Get complete system status."""
        return {
            "healthy": self.is_healthy(),
            "timestamp": datetime.now().isoformat(),
            "orchestrator": self.orchestrator.get_health_status(),
            "watchdog": self.watchdog.get_stats(),
        }
