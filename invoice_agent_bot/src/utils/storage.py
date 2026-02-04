"""
Storage and Persistence Module

Provides data persistence using SQLite for invoice storage,
conversation history, and user data.
"""

import json
import aiosqlite
from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar
from contextlib import asynccontextmanager

from src.core.config import get_settings
from src.models.invoice import InvoiceData, InvoiceStatus, DocumentMetadata
from src.utils.logger import get_logger
from src.utils.error_recovery import ProcessingError

logger = get_logger(__name__)

T = TypeVar("T")


class JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for invoice data types."""
    
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, InvoiceStatus):
            return obj.value
        return super().default(obj)


class BaseRepository(ABC):
    """Abstract base class for repositories."""
    
    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> str:
        """Create a new record."""
        pass
    
    @abstractmethod
    async def get(self, id: str) -> Optional[Dict[str, Any]]:
        """Get a record by ID."""
        pass
    
    @abstractmethod
    async def update(self, id: str, data: Dict[str, Any]) -> bool:
        """Update a record."""
        pass
    
    @abstractmethod
    async def delete(self, id: str) -> bool:
        """Delete a record."""
        pass


class Database:
    """
    SQLite database manager.
    
    Handles connection pooling, migrations, and provides
    a context manager for transactions.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.settings = get_settings()
        self.db_path = db_path or self.settings.database_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: Optional[aiosqlite.Connection] = None
    
    async def connect(self) -> None:
        """Establish database connection."""
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._create_tables()
        logger.info(f"Database connected: {self.db_path}")
    
    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")
    
    async def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        if not self._connection:
            raise RuntimeError("Database not connected")
        
        # Invoices table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id TEXT PRIMARY KEY,
                invoice_number TEXT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                data TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMP,
                paid_at TIMESTAMP
            )
        """)
        
        # Documents table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                local_path TEXT,
                extracted_text TEXT,
                processed BOOLEAN DEFAULT FALSE,
                processing_error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Conversation history table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                state TEXT NOT NULL,
                messages TEXT,
                invoice_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # User preferences table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                default_currency TEXT DEFAULT 'USD',
                default_company TEXT,
                notification_enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_invoices_user ON invoices(user_id)
        """)
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status)
        """)
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id)
        """)
        
        await self._connection.commit()
        logger.info("Database tables initialized")
    
    @asynccontextmanager
    async def transaction(self):
        """Context manager for database transactions."""
        if not self._connection:
            raise RuntimeError("Database not connected")
        
        try:
            yield self._connection
            await self._connection.commit()
        except Exception:
            await self._connection.rollback()
            raise
    
    async def execute(
        self, 
        query: str, 
        parameters: tuple = ()
    ) -> aiosqlite.Cursor:
        """Execute a SQL query."""
        if not self._connection:
            raise RuntimeError("Database not connected")
        return await self._connection.execute(query, parameters)
    
    async def fetchone(
        self, 
        query: str, 
        parameters: tuple = ()
    ) -> Optional[aiosqlite.Row]:
        """Fetch a single row."""
        cursor = await self.execute(query, parameters)
        return await cursor.fetchone()
    
    async def fetchall(
        self, 
        query: str, 
        parameters: tuple = ()
    ) -> List[aiosqlite.Row]:
        """Fetch all rows."""
        cursor = await self.execute(query, parameters)
        return await cursor.fetchall()


class InvoiceRepository(BaseRepository):
    """Repository for invoice data."""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def create(self, invoice: InvoiceData) -> str:
        """Save a new invoice."""
        try:
            data_json = json.dumps(invoice.to_dict(), cls=JSONEncoder)
            
            await self.db.execute(
                """
                INSERT INTO invoices 
                (id, invoice_number, user_id, chat_id, data, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice.id,
                    invoice.invoice_number,
                    invoice.user_id,
                    invoice.chat_id,
                    data_json,
                    invoice.status.value,
                )
            )
            
            logger.info(f"Invoice created: {invoice.id}")
            return invoice.id
            
        except Exception as e:
            logger.error(f"Failed to create invoice: {e}")
            raise ProcessingError(f"Failed to save invoice: {e}")
    
    async def get(self, invoice_id: str) -> Optional[InvoiceData]:
        """Get invoice by ID."""
        try:
            row = await self.db.fetchone(
                "SELECT data FROM invoices WHERE id = ?",
                (invoice_id,)
            )
            
            if row:
                data = json.loads(row["data"])
                return InvoiceData.from_dict(data)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get invoice: {e}")
            raise ProcessingError(f"Failed to retrieve invoice: {e}")
    
    async def get_by_number(self, invoice_number: str) -> Optional[InvoiceData]:
        """Get invoice by invoice number."""
        try:
            row = await self.db.fetchone(
                "SELECT data FROM invoices WHERE invoice_number = ?",
                (invoice_number,)
            )
            
            if row:
                data = json.loads(row["data"])
                return InvoiceData.from_dict(data)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get invoice by number: {e}")
            raise ProcessingError(f"Failed to retrieve invoice: {e}")
    
    async def update(self, invoice_id: str, invoice: InvoiceData) -> bool:
        """Update an existing invoice."""
        try:
            data_json = json.dumps(invoice.to_dict(), cls=JSONEncoder)
            
            cursor = await self.db.execute(
                """
                UPDATE invoices 
                SET data = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (data_json, invoice.status.value, invoice_id)
            )
            
            updated = cursor.rowcount > 0
            if updated:
                logger.info(f"Invoice updated: {invoice_id}")
            return updated
            
        except Exception as e:
            logger.error(f"Failed to update invoice: {e}")
            raise ProcessingError(f"Failed to update invoice: {e}")
    
    async def delete(self, invoice_id: str) -> bool:
        """Delete an invoice."""
        try:
            cursor = await self.db.execute(
                "DELETE FROM invoices WHERE id = ?",
                (invoice_id,)
            )
            
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Invoice deleted: {invoice_id}")
            return deleted
            
        except Exception as e:
            logger.error(f"Failed to delete invoice: {e}")
            raise ProcessingError(f"Failed to delete invoice: {e}")
    
    async def list_by_user(
        self, 
        user_id: int, 
        limit: int = 50,
        offset: int = 0
    ) -> List[InvoiceData]:
        """List invoices for a user."""
        try:
            rows = await self.db.fetchall(
                """
                SELECT data FROM invoices 
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset)
            )
            
            invoices = []
            for row in rows:
                data = json.loads(row["data"])
                invoices.append(InvoiceData.from_dict(data))
            
            return invoices
            
        except Exception as e:
            logger.error(f"Failed to list invoices: {e}")
            raise ProcessingError(f"Failed to list invoices: {e}")
    
    async def get_next_invoice_number(self, prefix: str) -> str:
        """Generate next invoice number."""
        try:
            row = await self.db.fetchone(
                """
                SELECT COUNT(*) as count FROM invoices 
                WHERE invoice_number LIKE ?
                """,
                (f"{prefix}%",)
            )
            
            count = row["count"] if row else 0
            next_number = self.db.settings.invoice_start_number + count
            
            return f"{prefix}-{next_number}"
            
        except Exception as e:
            logger.error(f"Failed to generate invoice number: {e}")
            # Fallback to timestamp-based number
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            return f"{prefix}-{timestamp}"


class DocumentRepository(BaseRepository):
    """Repository for document metadata."""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def create(self, metadata: DocumentMetadata) -> str:
        """Save document metadata."""
        try:
            await self.db.execute(
                """
                INSERT INTO documents 
                (id, file_name, file_type, file_size, user_id, chat_id, local_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metadata.file_id,
                    metadata.file_name,
                    metadata.file_type,
                    metadata.file_size,
                    metadata.user_id,
                    metadata.chat_id,
                    metadata.local_path,
                )
            )
            
            logger.info(f"Document metadata saved: {metadata.file_id}")
            return metadata.file_id
            
        except Exception as e:
            logger.error(f"Failed to save document metadata: {e}")
            raise ProcessingError(f"Failed to save document: {e}")
    
    async def get(self, document_id: str) -> Optional[DocumentMetadata]:
        """Get document metadata by ID."""
        try:
            row = await self.db.fetchone(
                "SELECT * FROM documents WHERE id = ?",
                (document_id,)
            )
            
            if row:
                return DocumentMetadata(
                    file_id=row["id"],
                    file_name=row["file_name"],
                    file_type=row["file_type"],
                    file_size=row["file_size"],
                    user_id=row["user_id"],
                    chat_id=row["chat_id"],
                    local_path=row["local_path"],
                    processed=bool(row["processed"]),
                    processing_error=row["processing_error"],
                )
            return None
            
        except Exception as e:
            logger.error(f"Failed to get document: {e}")
            raise ProcessingError(f"Failed to retrieve document: {e}")
    
    async def update_processing_status(
        self, 
        document_id: str, 
        processed: bool,
        error: Optional[str] = None,
        extracted_text: Optional[str] = None
    ) -> bool:
        """Update document processing status."""
        try:
            cursor = await self.db.execute(
                """
                UPDATE documents 
                SET processed = ?, processing_error = ?, extracted_text = ?
                WHERE id = ?
                """,
                (processed, error, extracted_text, document_id)
            )
            
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Failed to update document status: {e}")
            raise ProcessingError(f"Failed to update document: {e}")
    
    async def delete(self, document_id: str) -> bool:
        """Delete document metadata.""""
        try:
            cursor = await self.db.execute(
                "DELETE FROM documents WHERE id = ?",
                (document_id,)
            )
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Failed to delete document: {e}")
            raise ProcessingError(f"Failed to delete document: {e}")


class StorageManager:
    """
    Centralized storage manager.
    
    Coordinates database operations and provides
    high-level storage operations.
    """
    
    def __init__(self):
        self.db = Database()
        self.invoices: Optional[InvoiceRepository] = None
        self.documents: Optional[DocumentRepository] = None
    
    async def initialize(self) -> None:
        """Initialize storage manager."""
        await self.db.connect()
        self.invoices = InvoiceRepository(self.db)
        self.documents = DocumentRepository(self.db)
        logger.info("Storage manager initialized")
    
    async def close(self) -> None:
        """Close storage manager."""
        await self.db.close()
        logger.info("Storage manager closed")
    
    async def health_check(self) -> Dict[str, Any]:
        """Check storage health."""
        try:
            # Try a simple query
            await self.db.fetchone("SELECT 1")
            return {"status": "healthy", "database": "connected"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


# Global storage manager instance
_storage_manager: Optional[StorageManager] = None


async def get_storage() -> StorageManager:
    """
    Get the global storage manager instance.
    
    Returns:
        StorageManager: Initialized singleton
    """
    global _storage_manager
    if _storage_manager is None:
        _storage_manager = StorageManager()
        await _storage_manager.initialize()
    return _storage_manager


async def initialize_storage() -> None:
    """Initialize the storage manager."""
    await get_storage()


async def shutdown_storage() -> None:
    """Shutdown the storage manager."""
    global _storage_manager
    if _storage_manager:
        await _storage_manager.close()
        _storage_manager = None
