"""
E2B Agent Module for Autonomous Invoice Extraction.

This module provides an AI agent that runs in an isolated E2B sandbox
and autonomously tries multiple extraction strategies until success.
"""

from .agent import ExtractionAgent
from .config import E2BConfig

__all__ = ["ExtractionAgent", "E2BConfig"]
