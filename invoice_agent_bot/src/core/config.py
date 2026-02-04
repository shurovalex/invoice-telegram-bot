"""
Configuration Management Module

Centralized configuration management using Pydantic Settings.
Loads configuration from environment variables and .env files.
"""

from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings have sensible defaults for development,
    but should be overridden in production via environment variables.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra env vars not defined here
    )
    
    # =========================================================================
    # Telegram Bot Configuration
    # =========================================================================
    telegram_bot_token: str = Field(
        ...,
        description="Telegram bot token from @BotFather",
        alias="TELEGRAM_BOT_TOKEN"
    )
    admin_user_ids: List[int] = Field(
        default_factory=list,
        description="List of admin user IDs",
        alias="ADMIN_USER_IDS"
    )
    
    # =========================================================================
    # AI Provider Configuration
    # =========================================================================
    # OpenAI
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key",
        alias="OPENAI_API_KEY"
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model to use",
        alias="OPENAI_MODEL"
    )
    openai_max_tokens: int = Field(
        default=2000,
        description="Maximum tokens for OpenAI responses",
        alias="OPENAI_MAX_TOKENS"
    )
    openai_temperature: float = Field(
        default=0.3,
        description="Temperature for OpenAI responses (0-1)",
        alias="OPENAI_TEMPERATURE"
    )
    
    # Google Gemini
    gemini_api_key: Optional[str] = Field(
        default=None,
        description="Google Gemini API key",
        alias="GEMINI_API_KEY"
    )
    gemini_model: str = Field(
        default="gemini-1.5-flash",
        description="Gemini model to use",
        alias="GEMINI_MODEL"
    )
    gemini_max_tokens: int = Field(
        default=2000,
        description="Maximum tokens for Gemini responses",
        alias="GEMINI_MAX_TOKENS"
    )
    gemini_temperature: float = Field(
        default=0.3,
        description="Temperature for Gemini responses (0-1)",
        alias="GEMINI_TEMPERATURE"
    )
    
    # Provider priority (fallback order)
    ai_provider_priority: List[str] = Field(
        default_factory=lambda: ["openai", "gemini"],
        description="AI provider priority order for fallback",
        alias="AI_PROVIDER_PRIORITY"
    )
    
    # =========================================================================
    # Document Processing Configuration
    # =========================================================================
    max_file_size_mb: int = Field(
        default=20,
        description="Maximum file upload size in MB",
        alias="MAX_FILE_SIZE_MB"
    )
    supported_formats: List[str] = Field(
        default_factory=lambda: ["pdf", "jpg", "jpeg", "png", "docx"],
        description="Supported file formats",
        alias="SUPPORTED_FORMATS"
    )
    ocr_language: str = Field(
        default="eng",
        description="OCR language code",
        alias="OCR_LANGUAGE"
    )
    
    # =========================================================================
    # Invoice Generation Configuration
    # =========================================================================
    default_currency: str = Field(
        default="USD",
        description="Default currency for invoices",
        alias="DEFAULT_CURRENCY"
    )
    
    # Company Information
    company_name: str = Field(
        default="Your Company",
        description="Company name for invoice header",
        alias="COMPANY_NAME"
    )
    company_address: str = Field(
        default="",
        description="Company address for invoice header",
        alias="COMPANY_ADDRESS"
    )
    company_email: Optional[str] = Field(
        default=None,
        description="Company email for invoice header",
        alias="COMPANY_EMAIL"
    )
    company_phone: Optional[str] = Field(
        default=None,
        description="Company phone for invoice header",
        alias="COMPANY_PHONE"
    )
    company_tax_id: Optional[str] = Field(
        default=None,
        description="Company tax ID for invoice header",
        alias="COMPANY_TAX_ID"
    )
    
    # Invoice numbering
    invoice_prefix: str = Field(
        default="INV",
        description="Invoice number prefix",
        alias="INVOICE_PREFIX"
    )
    invoice_start_number: int = Field(
        default=1000,
        description="Starting invoice number",
        alias="INVOICE_START_NUMBER"
    )
    
    # =========================================================================
    # Storage Configuration
    # =========================================================================
    data_dir: Path = Field(
        default=Path("./data"),
        description="Base directory for data storage",
        alias="DATA_DIR"
    )
    database_path: Path = Field(
        default=Path("./data/invoice_bot.db"),
        description="SQLite database path",
        alias="DATABASE_PATH"
    )
    invoice_output_dir: Path = Field(
        default=Path("./data/invoices"),
        description="Invoice output directory",
        alias="INVOICE_OUTPUT_DIR"
    )
    upload_dir: Path = Field(
        default=Path("./data/uploads"),
        description="Upload temporary directory",
        alias="UPLOAD_DIR"
    )
    log_dir: Path = Field(
        default=Path("./data/logs"),
        description="Log directory",
        alias="LOG_DIR"
    )
    
    # =========================================================================
    # Bot Behavior Configuration
    # =========================================================================
    conversation_timeout_minutes: int = Field(
        default=30,
        description="Conversation timeout in minutes",
        alias="CONVERSATION_TIMEOUT_MINUTES"
    )
    max_retry_attempts: int = Field(
        default=3,
        description="Maximum retry attempts for failed operations",
        alias="MAX_RETRY_ATTEMPTS"
    )
    retry_delay_base: int = Field(
        default=2,
        description="Base delay for exponential backoff (seconds)",
        alias="RETRY_DELAY_BASE"
    )
    
    # =========================================================================
    # Logging Configuration
    # =========================================================================
    log_level: str = Field(
        default="INFO",
        description="Logging level",
        alias="LOG_LEVEL"
    )
    enable_file_logging: bool = Field(
        default=True,
        description="Enable file logging",
        alias="ENABLE_FILE_LOGGING"
    )
    enable_console_logging: bool = Field(
        default=True,
        description="Enable console logging",
        alias="ENABLE_CONSOLE_LOGGING"
    )
    
    # =========================================================================
    # Development/Testing Configuration
    # =========================================================================
    debug_mode: bool = Field(
        default=False,
        description="Enable debug mode",
        alias="DEBUG_MODE"
    )
    test_mode: bool = Field(
        default=False,
        description="Enable test mode (mock AI responses)",
        alias="TEST_MODE"
    )
    
    # =========================================================================
    # Validators
    # =========================================================================
    @field_validator("admin_user_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: str | List[int]) -> List[int]:
        """Parse comma-separated admin IDs into list of integers."""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v or []
    
    @field_validator("supported_formats", mode="before")
    @classmethod
    def parse_formats(cls, v: str | List[str]) -> List[str]:
        """Parse comma-separated formats into list."""
        if isinstance(v, str):
            return [x.strip().lower() for x in v.split(",") if x.strip()]
        return v or []
    
    @field_validator("ai_provider_priority", mode="before")
    @classmethod
    def parse_providers(cls, v: str | List[str]) -> List[str]:
        """Parse comma-separated provider priority into list."""
        if isinstance(v, str):
            return [x.strip().lower() for x in v.split(",") if x.strip()]
        return v or []
    
    @field_validator("data_dir", "database_path", "invoice_output_dir", 
                     "upload_dir", "log_dir", mode="before")
    @classmethod
    def parse_paths(cls, v: str | Path) -> Path:
        """Parse string paths into Path objects."""
        if isinstance(v, str):
            return Path(v)
        return v
    
    # =========================================================================
    # Properties
    # =========================================================================
    @property
    def max_file_size_bytes(self) -> int:
        """Return max file size in bytes."""
        return self.max_file_size_mb * 1024 * 1024
    
    @property
    def conversation_timeout_seconds(self) -> int:
        """Return conversation timeout in seconds."""
        return self.conversation_timeout_minutes * 60
    
    @property
    def available_ai_providers(self) -> List[str]:
        """Return list of configured AI providers."""
        providers = []
        if self.openai_api_key:
            providers.append("openai")
        if self.gemini_api_key:
            providers.append("gemini")
        return providers
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return not self.debug_mode and not self.test_mode
    
    def ensure_directories(self) -> None:
        """Create all necessary directories if they don't exist."""
        directories = [
            self.data_dir,
            self.invoice_output_dir,
            self.upload_dir,
            self.log_dir,
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)


# Global settings instance (lazy-loaded)
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get the global settings instance.
    
    Returns:
        Settings: Application settings singleton
    """
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_directories()
    return _settings


def reload_settings() -> Settings:
    """
    Reload settings from environment (useful for testing).
    
    Returns:
        Settings: Fresh settings instance
    """
    global _settings
    _settings = Settings()
    _settings.ensure_directories()
    return _settings
