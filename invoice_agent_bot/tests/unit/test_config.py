"""
Unit tests for configuration module.
"""

import pytest
from pathlib import Path

from src.core.config import Settings, get_settings, reload_settings


class TestSettings:
    """Tests for Settings model."""
    
    def test_default_values(self, monkeypatch):
        """Test default configuration values."""
        # Clear any existing env vars
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        
        # Set required token
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        
        settings = reload_settings()
        
        assert settings.telegram_bot_token == "test_token"
        assert settings.openai_model == "gpt-4o-mini"
        assert settings.gemini_model == "gemini-1.5-flash"
        assert settings.default_currency == "USD"
        assert settings.max_file_size_mb == 20
    
    def test_admin_ids_parsing(self, monkeypatch):
        """Test admin user IDs parsing."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("ADMIN_USER_IDS", "123456,789012,345678")
        
        settings = reload_settings()
        
        assert settings.admin_user_ids == [123456, 789012, 345678]
    
    def test_max_file_size_bytes(self, monkeypatch):
        """Test max file size conversion."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("MAX_FILE_SIZE_MB", "10")
        
        settings = reload_settings()
        
        assert settings.max_file_size_bytes == 10 * 1024 * 1024
    
    def test_ai_providers(self, monkeypatch):
        """Test AI provider availability detection."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        
        settings = reload_settings()
        
        assert "openai" in settings.available_ai_providers
        assert "gemini" not in settings.available_ai_providers
