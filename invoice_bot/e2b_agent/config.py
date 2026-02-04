"""
E2B Agent Configuration.
"""

import os
from dataclasses import dataclass


@dataclass
class E2BConfig:
    """E2B Agent Configuration"""

    # API Keys (loaded from environment)
    E2B_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # Sandbox configuration
    SANDBOX_TEMPLATE: str = "base"  # Use E2B's base Python template
    SANDBOX_TIMEOUT: int = 120  # Auto-close after 2 minutes

    # Timeouts (seconds)
    CODE_EXECUTION_TIMEOUT: int = 60
    TOTAL_EXTRACTION_TIMEOUT: int = 180
    LLM_TIMEOUT: int = 15

    # Quality thresholds
    MIN_QUALITY_THRESHOLD: float = 0.4
    GOOD_QUALITY_THRESHOLD: float = 0.65

    # Limits
    MAX_STRATEGIES: int = 5
    MAX_RETRIES_PER_STRATEGY: int = 1

    @classmethod
    def from_env(cls) -> "E2BConfig":
        """Load configuration from environment variables."""
        return cls(
            E2B_API_KEY=os.getenv("E2B_API_KEY", ""),
            OPENAI_API_KEY=os.getenv("OPENAI_API_KEY", ""),
        )

    def is_available(self) -> bool:
        """Check if E2B is configured and available."""
        return bool(self.E2B_API_KEY and self.OPENAI_API_KEY)
