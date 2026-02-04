"""
Pytest configuration and fixtures.
"""

import pytest
import asyncio
from pathlib import Path


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir(tmp_path):
    """Provide a temporary directory for tests."""
    return tmp_path


@pytest.fixture(autouse=True)
def reset_settings():
    """Reset settings before each test."""
    # Import here to avoid circular imports
    from src.core.config import reload_settings
    
    # Set test environment
    import os
    os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
    os.environ["TEST_MODE"] = "true"
    
    reload_settings()
    
    yield
    
    # Cleanup
    os.environ.pop("TEST_MODE", None)
