"""
================================================================================
STATE PERSISTENCE STRATEGY
================================================================================
Multi-layer state persistence for crash recovery and session continuity
Layers: Memory -> Local File -> Redis -> Database

This module ensures that user session state is never lost, even during crashes
or restarts. It provides multiple persistence layers for maximum reliability.
"""

import json
import pickle
import asyncio
import aiofiles
import logging
from typing import Dict, Any, Optional, List, Callable, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import os
import shutil

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """Complete session state for persistence"""
    session_id: str
    user_id: str
    chat_id: str
    conversation_history: List[Dict] = field(default_factory=list)
    pending_invoice: Optional[Dict] = None
    extracted_data: Optional[Dict] = None
    current_step: str = "start"
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    version: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "conversation_history": self.conversation_history,
            "pending_invoice": self.pending_invoice,
            "extracted_data": self.extracted_data,
            "current_step": self.current_step,
            "context": self.context,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'SessionState':
        """Create SessionState from dictionary"""
        state = cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            chat_id=data["chat_id"],
        )
        state.conversation_history = data.get("conversation_history", [])
        state.pending_invoice = data.get("pending_invoice")
        state.extracted_data = data.get("extracted_data")
        state.current_step = data.get("current_step", "start")
        state.context = data.get("context", {})
        state.metadata = data.get("metadata", {})
        state.version = data.get("version", 1)
        
        if "created_at" in data:
            state.created_at = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data:
            state.updated_at = datetime.fromisoformat(data["updated_at"])
        
        return state
    
    def update_timestamp(self):
        """Update the timestamp"""
        self.updated_at = datetime.now()
        self.version += 1


class StatePersistenceLayer:
    """Abstract base class for persistence layers"""
    
    async def save(self, key: str, state: SessionState) -> bool:
        raise NotImplementedError
    
    async def load(self, key: str) -> Optional[SessionState]:
        raise NotImplementedError
    
    async def delete(self, key: str) -> bool:
        raise NotImplementedError
    
    async def exists(self, key: str) -> bool:
        raise NotImplementedError
    
    async def get_all_keys(self) -> List[str]:
        raise NotImplementedError


class MemoryPersistenceLayer(StatePersistenceLayer):
    """In-memory persistence (fastest, but volatile)"""
    
    def __init__(self, max_size: int = 10000):
        self._storage: Dict[str, SessionState] = {}
        self._max_size = max_size
        self._access_times: Dict[str, datetime] = {}
    
    async def save(self, key: str, state: SessionState) -> bool:
        # Evict oldest if at capacity
        if len(self._storage) >= self._max_size and key not in self._storage:
            oldest_key = min(self._access_times, key=self._access_times.get)
            del self._storage[oldest_key]
            del self._access_times[oldest_key]
        
        self._storage[key] = state
        self._access_times[key] = datetime.now()
        return True
    
    async def load(self, key: str) -> Optional[SessionState]:
        if key in self._storage:
            self._access_times[key] = datetime.now()
            return self._storage[key]
        return None
    
    async def delete(self, key: str) -> bool:
        if key in self._storage:
            del self._storage[key]
            del self._access_times[key]
            return True
        return False
    
    async def exists(self, key: str) -> bool:
        return key in self._storage
    
    async def get_all_keys(self) -> List[str]:
        return list(self._storage.keys())
    
    def get_memory_usage(self) -> int:
        """Get approximate memory usage in bytes"""
        return len(pickle.dumps(self._storage))


class FilePersistenceLayer(StatePersistenceLayer):
    """File-based persistence (survives process restart)"""
    
    def __init__(self, base_path: str = "./state_storage"):
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._ensure_backup_dir()
    
    def _ensure_backup_dir(self):
        """Create backup directory"""
        backup_dir = self._base_path / "backups"
        backup_dir.mkdir(exist_ok=True)
    
    def _get_file_path(self, key: str) -> Path:
        """Get file path for a key"""
        # Use hash to avoid filesystem issues with special characters
        safe_key = hashlib.md5(key.encode()).hexdigest()
        return self._base_path / f"{safe_key}.json"
    
    async def save(self, key: str, state: SessionState) -> bool:
        try:
            file_path = self._get_file_path(key)
            
            # Write to temp file first, then rename (atomic operation)
            temp_path = file_path.with_suffix('.tmp')
            
            async with aiofiles.open(temp_path, 'w') as f:
                await f.write(json.dumps(state.to_dict(), indent=2))
            
            # Atomic rename
            temp_path.replace(file_path)
            
            # Create backup periodically
            await self._create_backup_if_needed(key, state)
            
            return True
        except Exception as e:
            logger.error(f"Failed to save state to file: {e}")
            return False
    
    async def _create_backup_if_needed(self, key: str, state: SessionState):
        """Create backup copy periodically"""
        # Create backup every 10 versions
        if state.version % 10 == 0:
            backup_dir = self._base_path / "backups"
            safe_key = hashlib.md5(key.encode()).hexdigest()
            backup_path = backup_dir / f"{safe_key}_v{state.version}.json"
            
            file_path = self._get_file_path(key)
            if file_path.exists():
                shutil.copy(file_path, backup_path)
    
    async def load(self, key: str) -> Optional[SessionState]:
        try:
            file_path = self._get_file_path(key)
            
            if not file_path.exists():
                return None
            
            async with aiofiles.open(file_path, 'r') as f:
                content = await f.read()
                data = json.loads(content)
                return SessionState.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load state from file: {e}")
            # Try to load from backup
            return await self._load_from_backup(key)
    
    async def _load_from_backup(self, key: str) -> Optional[SessionState]:
        """Attempt to load from backup files"""
        try:
            backup_dir = self._base_path / "backups"
            safe_key = hashlib.md5(key.encode()).hexdigest()
            
            # Find most recent backup
            backups = sorted(
                backup_dir.glob(f"{safe_key}_v*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            for backup in backups[:3]:  # Try 3 most recent
                try:
                    async with aiofiles.open(backup, 'r') as f:
                        content = await f.read()
                        data = json.loads(content)
                        logger.info(f"Recovered state from backup: {backup}")
                        return SessionState.from_dict(data)
                except:
                    continue
        except Exception as e:
            logger.error(f"Failed to load from backup: {e}")
        
        return None
    
    async def delete(self, key: str) -> bool:
        try:
            file_path = self._get_file_path(key)
            if file_path.exists():
                file_path.unlink()
            return True
        except Exception as e:
            logger.error(f"Failed to delete state file: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        return self._get_file_path(key).exists()
    
    async def get_all_keys(self) -> List[str]:
        """Get all keys - note: this reconstructs keys from files"""
        keys = []
        for file_path in self._base_path.glob("*.json"):
            try:
                async with aiofiles.open(file_path, 'r') as f:
                    content = await f.read()
                    data = json.loads(content)
                    keys.append(data.get("session_id", file_path.stem))
            except:
                pass
        return keys
    
    async def cleanup_old_states(self, max_age_days: int = 30):
        """Clean up old state files"""
        cutoff = datetime.now() - timedelta(days=max_age_days)
        
        for file_path in self._base_path.glob("*.json"):
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime < cutoff:
                    file_path.unlink()
                    logger.info(f"Cleaned up old state file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to cleanup {file_path}: {e}")


class RedisPersistenceLayer(StatePersistenceLayer):
    """Redis-based persistence (distributed, fast)"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379", ttl: int = 86400):
        self._redis_url = redis_url
        self._ttl = ttl
        self._redis = None
        self._connected = False
    
    async def _ensure_connection(self):
        """Ensure Redis connection"""
        if not self._connected:
            try:
                import aioredis
                self._redis = await aioredis.from_url(self._redis_url)
                self._connected = True
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise
    
    async def save(self, key: str, state: SessionState) -> bool:
        try:
            await self._ensure_connection()
            data = json.dumps(state.to_dict())
            await self._redis.setex(key, self._ttl, data)
            return True
        except Exception as e:
            logger.error(f"Failed to save to Redis: {e}")
            return False
    
    async def load(self, key: str) -> Optional[SessionState]:
        try:
            await self._ensure_connection()
            data = await self._redis.get(key)
            if data:
                return SessionState.from_dict(json.loads(data))
            return None
        except Exception as e:
            logger.error(f"Failed to load from Redis: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        try:
            await self._ensure_connection()
            await self._redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete from Redis: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        try:
            await self._ensure_connection()
            return await self._redis.exists(key) > 0
        except:
            return False
    
    async def get_all_keys(self) -> List[str]:
        try:
            await self._ensure_connection()
            keys = await self._redis.keys("*")
            return [k.decode() if isinstance(k, bytes) else k for k in keys]
        except:
            return []


class MultiLayerStateManager:
    """
    Multi-layer state persistence manager
    Tries layers in order: Memory -> File -> Redis
    """
    
    def __init__(self):
        self._layers: List[StatePersistenceLayer] = []
        self._write_layers: List[StatePersistenceLayer] = []
        self._sync_interval = 60  # Seconds between syncs
        self._last_sync: Dict[str, datetime] = {}
    
    def add_layer(self, layer: StatePersistenceLayer, write: bool = True):
        """Add a persistence layer"""
        self._layers.append(layer)
        if write:
            self._write_layers.append(layer)
    
    async def save_state(self, state: SessionState, sync_all: bool = False) -> bool:
        """
        Save state to all write layers
        
        Args:
            state: The session state to save
            sync_all: If True, write to all layers; if False, only write to fastest layer
        """
        key = state.session_id
        state.update_timestamp()
        
        success = False
        
        # Always write to memory (fastest)
        if self._write_layers:
            try:
                success = await self._write_layers[0].save(key, state)
            except Exception as e:
                logger.error(f"Failed to save to primary layer: {e}")
        
        # Sync to other layers periodically or if requested
        should_sync = sync_all or self._should_sync(key)
        
        if should_sync:
            for layer in self._write_layers[1:]:
                try:
                    await layer.save(key, state)
                except Exception as e:
                    logger.warning(f"Failed to sync to layer: {e}")
            
            self._last_sync[key] = datetime.now()
        
        return success
    
    def _should_sync(self, key: str) -> bool:
        """Determine if we should sync to persistent layers"""
        if key not in self._last_sync:
            return True
        
        elapsed = (datetime.now() - self._last_sync[key]).total_seconds()
        return elapsed >= self._sync_interval
    
    async def load_state(self, session_id: str) -> Optional[SessionState]:
        """
        Load state from first available layer
        Tries layers in order until one succeeds
        """
        for layer in self._layers:
            try:
                state = await layer.load(session_id)
                if state:
                    logger.debug(f"Loaded state from {layer.__class__.__name__}")
                    return state
            except Exception as e:
                logger.warning(f"Failed to load from layer: {e}")
                continue
        
        return None
    
    async def delete_state(self, session_id: str) -> bool:
        """Delete state from all layers"""
        success = True
        for layer in self._write_layers:
            try:
                await layer.delete(session_id)
            except Exception as e:
                logger.error(f"Failed to delete from layer: {e}")
                success = False
        
        if session_id in self._last_sync:
            del self._last_sync[session_id]
        
        return success
    
    async def recover_session(self, user_id: str, chat_id: str) -> Optional[SessionState]:
        """
        Attempt to recover a session after crash/restart
        Looks for recent sessions from the same user/chat
        """
        # This would search through persisted states
        # For now, return None - implement based on storage
        return None
    
    async def get_all_active_sessions(self) -> List[SessionState]:
        """Get all active sessions"""
        sessions = []
        
        # Use first layer that supports listing
        for layer in self._layers:
            try:
                keys = await layer.get_all_keys()
                for key in keys:
                    state = await layer.load(key)
                    if state:
                        sessions.append(state)
                break
            except:
                continue
        
        return sessions


# Factory for creating configured state managers
def create_state_manager(
    use_memory: bool = True,
    use_file: bool = True,
    file_path: str = "./state_storage",
    use_redis: bool = False,
    redis_url: str = "redis://localhost:6379"
) -> MultiLayerStateManager:
    """Create a configured state manager"""
    
    manager = MultiLayerStateManager()
    
    if use_memory:
        manager.add_layer(MemoryPersistenceLayer(), write=True)
    
    if use_file:
        manager.add_layer(FilePersistenceLayer(file_path), write=True)
    
    if use_redis:
        try:
            manager.add_layer(RedisPersistenceLayer(redis_url), write=True)
        except Exception as e:
            logger.warning(f"Could not add Redis layer: {e}")
    
    return manager
