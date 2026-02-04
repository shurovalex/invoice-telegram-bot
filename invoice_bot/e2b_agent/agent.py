"""
E2B Extraction Agent - Autonomous Invoice Data Extraction.

This agent runs extraction code in isolated E2B sandboxes and
autonomously reasons about failures to try different strategies.
"""

import asyncio
import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

from openai import AsyncOpenAI

from .config import E2BConfig
from .strategies import STRATEGIES, StrategyType, get_strategy_order

logger = logging.getLogger(__name__)


@dataclass
class ExtractionAttempt:
    """Record of a single extraction attempt."""
    strategy: StrategyType
    raw_text: str
    extracted_data: Dict[str, Any]
    quality_score: float
    quality_issues: List[str]
    execution_time_ms: int
    error: Optional[str] = None


@dataclass
class AgentState:
    """Current state of the extraction agent."""
    file_path: str
    file_type: str
    attempts: List[ExtractionAttempt] = field(default_factory=list)
    best_attempt: Optional[ExtractionAttempt] = None
    reasoning_history: List[str] = field(default_factory=list)
    total_time_ms: int = 0


class ExtractionAgent:
    """
    Autonomous agent for invoice data extraction.

    Uses E2B sandboxes to execute extraction code and
    reasons about failures to try different strategies.
    """

    def __init__(self, config: Optional[E2BConfig] = None):
        """Initialize the extraction agent."""
        self.config = config or E2BConfig.from_env()
        self.openai_client = None

        if self.config.OPENAI_API_KEY:
            self.openai_client = AsyncOpenAI(api_key=self.config.OPENAI_API_KEY)

    def is_available(self) -> bool:
        """Check if E2B agent is available."""
        return self.config.is_available()

    async def extract_invoice(
        self,
        file_bytes: bytes,
        filename: str
    ) -> Tuple[Dict[str, Any], "AgentState"]:
        """
        Main entry point: Extract invoice data from document.

        Args:
            file_bytes: Raw document bytes
            filename: Original filename

        Returns:
            Tuple of (extracted_data dict, AgentState with reasoning history)
        """
        start_time = time.time()

        # Determine file type
        file_type = self._detect_file_type(filename)

        # Initialize state
        state = AgentState(
            file_path=f"/tmp/{filename}",
            file_type=file_type
        )

        state.reasoning_history.append(f"Starting extraction for {file_type} file: {filename}")

        # Import E2B here to avoid import errors if not installed
        try:
            from e2b_code_interpreter import Sandbox
        except ImportError:
            state.reasoning_history.append("E2B not installed, falling back to GPT-4 Vision")
            return await self._extract_with_vision_only(file_bytes, filename, state)

        # Get strategy order
        strategy_order = get_strategy_order(file_type)
        state.reasoning_history.append(f"Strategy order: {[s.value for s in strategy_order]}")

        sandbox = None
        try:
            # Create sandbox (blocking call - run in thread)
            state.reasoning_history.append("Creating E2B sandbox...")
            logger.info("[E2B] Creating sandbox...")
            sandbox = await asyncio.to_thread(
                Sandbox,
                api_key=self.config.E2B_API_KEY,
                timeout=self.config.SANDBOX_TIMEOUT
            )
            logger.info(f"[E2B] Sandbox created: {sandbox}")

            # Install required packages
            await self._install_packages(sandbox, state)

            # Write file to sandbox (blocking call - run in thread)
            logger.info(f"[E2B] Writing file to sandbox: {state.file_path}")
            await asyncio.to_thread(sandbox.files.write, state.file_path, file_bytes)
            state.reasoning_history.append(f"Uploaded file to sandbox: {state.file_path}")

            # Agent reasoning loop
            for attempt_num in range(self.config.MAX_STRATEGIES):
                if not strategy_order:
                    state.reasoning_history.append("No more strategies available")
                    break

                # Get next strategy
                strategy_type = strategy_order.pop(0)

                # Skip GPT4_VISION in sandbox loop (handled separately)
                if strategy_type == StrategyType.GPT4_VISION:
                    continue

                strategy = STRATEGIES.get(strategy_type)
                if not strategy:
                    continue

                state.reasoning_history.append(
                    f"Attempt {attempt_num + 1}: {strategy.description}"
                )

                # Execute strategy
                attempt = await self._execute_strategy(sandbox, state, strategy)
                state.attempts.append(attempt)

                if attempt.error:
                    state.reasoning_history.append(f"Strategy failed: {attempt.error}")
                    continue

                # Parse extracted text into fields
                if attempt.raw_text:
                    attempt.extracted_data = await self._parse_invoice_fields(attempt.raw_text)

                # Assess quality
                quality_score, quality_issues = await self._assess_quality(
                    attempt.raw_text,
                    attempt.extracted_data
                )
                attempt.quality_score = quality_score
                attempt.quality_issues = quality_issues

                state.reasoning_history.append(
                    f"Quality: {quality_score:.2f}, Issues: {quality_issues}"
                )

                # Update best attempt
                if state.best_attempt is None or quality_score > state.best_attempt.quality_score:
                    state.best_attempt = attempt

                # Check if quality is good enough
                if quality_score >= self.config.GOOD_QUALITY_THRESHOLD:
                    state.reasoning_history.append(
                        f"Quality threshold met ({quality_score:.2f} >= {self.config.GOOD_QUALITY_THRESHOLD})"
                    )
                    break

                # Reason about what to try next
                if quality_score < self.config.MIN_QUALITY_THRESHOLD:
                    next_strategies = await self._reason_about_failure(state, attempt)
                    for s in reversed(next_strategies):
                        if s not in [a.strategy for a in state.attempts] and s not in strategy_order:
                            strategy_order.insert(0, s)

        except Exception as e:
            logger.error(f"E2B extraction error: {e}")
            state.reasoning_history.append(f"E2B error: {e}")

        finally:
            # Always close sandbox (blocking call - run in thread)
            if sandbox:
                try:
                    logger.info("[E2B] Closing sandbox...")
                    await asyncio.to_thread(sandbox.close)
                    state.reasoning_history.append("Sandbox closed")
                    logger.info("[E2B] Sandbox closed successfully")
                except Exception as e:
                    logger.warning(f"[E2B] Error closing sandbox: {e}")

        # If no good result, try GPT-4 Vision as final fallback
        if (state.best_attempt is None or
            state.best_attempt.quality_score < self.config.MIN_QUALITY_THRESHOLD):
            state.reasoning_history.append("Trying GPT-4 Vision as final fallback...")
            vision_result = await self._extract_with_vision(file_bytes, filename)
            if vision_result:
                vision_attempt = ExtractionAttempt(
                    strategy=StrategyType.GPT4_VISION,
                    raw_text="[Vision extraction]",
                    extracted_data=vision_result,
                    quality_score=0.0,
                    quality_issues=[],
                    execution_time_ms=0
                )
                # Assess vision quality
                quality, issues = await self._assess_quality("", vision_result)
                vision_attempt.quality_score = quality
                vision_attempt.quality_issues = issues
                state.attempts.append(vision_attempt)

                if state.best_attempt is None or quality > state.best_attempt.quality_score:
                    state.best_attempt = vision_attempt
                    state.reasoning_history.append(f"Vision quality: {quality:.2f}")

        # Calculate total time
        state.total_time_ms = int((time.time() - start_time) * 1000)

        # Return best result
        if state.best_attempt:
            return state.best_attempt.extracted_data, state
        else:
            return {}, state

    async def _install_packages(self, sandbox, state: AgentState):
        """Install required packages in sandbox."""
        packages = ["pytesseract", "Pillow", "pdfplumber"]

        state.reasoning_history.append(f"Installing packages: {packages}")
        logger.info(f"[E2B] Installing packages: {packages}")

        try:
            # Install via pip
            install_code = f"""
import subprocess
import sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", {', '.join(f'"{p}"' for p in packages)}])
print("Packages installed successfully")
"""
            # Run in thread (blocking call)
            result = await asyncio.to_thread(sandbox.run_code, install_code)
            logger.info(f"[E2B] Package install result: {result}")
            if result.error:
                state.reasoning_history.append(f"Package install warning: {result.error}")
                logger.warning(f"[E2B] Package install error: {result.error}")
        except Exception as e:
            state.reasoning_history.append(f"Package install error: {e}")
            logger.error(f"[E2B] Package install exception: {e}")

    async def _execute_strategy(
        self,
        sandbox,
        state: AgentState,
        strategy
    ) -> ExtractionAttempt:
        """Execute an extraction strategy in the sandbox."""
        start_time = time.time()

        try:
            # Prepare code
            code = strategy.code_template.format(file_path=state.file_path)

            # Execute in thread (blocking call)
            logger.info(f"[E2B] Executing strategy: {strategy.name}")
            result = await asyncio.to_thread(sandbox.run_code, code)
            logger.info(f"[E2B] Strategy execution complete, result: {result}")

            # Parse output
            raw_text = self._parse_output(result.logs.stdout if result.logs else "")
            logger.info(f"[E2B] Extracted text length: {len(raw_text)}")

            if result.error:
                return ExtractionAttempt(
                    strategy=strategy.name,
                    raw_text="",
                    extracted_data={},
                    quality_score=0.0,
                    quality_issues=["Execution error"],
                    execution_time_ms=int((time.time() - start_time) * 1000),
                    error=str(result.error)
                )

            return ExtractionAttempt(
                strategy=strategy.name,
                raw_text=raw_text,
                extracted_data={},
                quality_score=0.0,
                quality_issues=[],
                execution_time_ms=int((time.time() - start_time) * 1000)
            )

        except Exception as e:
            return ExtractionAttempt(
                strategy=strategy.name,
                raw_text="",
                extracted_data={},
                quality_score=0.0,
                quality_issues=["Exception"],
                execution_time_ms=int((time.time() - start_time) * 1000),
                error=str(e)
            )

    def _parse_output(self, stdout: str) -> str:
        """Extract text between markers."""
        if "===EXTRACTED_TEXT_START===" in stdout and "===EXTRACTED_TEXT_END===" in stdout:
            start = stdout.index("===EXTRACTED_TEXT_START===") + len("===EXTRACTED_TEXT_START===")
            end = stdout.index("===EXTRACTED_TEXT_END===")
            return stdout[start:end].strip()
        return stdout.strip()

    def _detect_file_type(self, filename: str) -> str:
        """Detect file type from filename."""
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp']:
            return "image"
        elif ext == 'pdf':
            return "pdf"
        elif ext in ['doc', 'docx']:
            return "docx"
        return "image"  # Default to image

    async def _parse_invoice_fields(self, raw_text: str) -> Dict[str, Any]:
        """Use LLM to parse invoice fields from raw text."""
        if not raw_text.strip() or not self.openai_client:
            return {}

        prompt = f"""Extract invoice data from this text. Return a JSON object with these fields:

{{
    "contractor_name": "string or null",
    "contractor_email": "string or null",
    "contractor_address": "string or null",
    "contractor_utr": "string or null",
    "contractor_ni": "string or null",
    "bank_account": "string or null",
    "sort_code": "string or null",
    "invoice_number": "string or null",
    "invoice_date": "string or null",
    "work_start_date": "string or null",
    "work_end_date": "string or null",
    "subtotal": number or null,
    "vat_amount": number or null,
    "cis_amount": number or null,
    "total": number or null
}}

TEXT:
{raw_text[:4000]}

Return ONLY valid JSON, no explanation."""

        try:
            response = await asyncio.wait_for(
                self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1000,
                    temperature=0.1,
                ),
                timeout=self.config.LLM_TIMEOUT
            )

            result_text = response.choices[0].message.content.strip()

            # Handle markdown code blocks
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]

            return json.loads(result_text)

        except Exception as e:
            logger.error(f"Field parsing failed: {e}")
            return {}

    async def _assess_quality(
        self,
        raw_text: str,
        extracted_data: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        """Assess quality of extraction."""
        issues = []

        # Basic heuristics
        if not extracted_data:
            return 0.1, ["No data extracted"]

        # Count filled fields
        filled = sum(1 for v in extracted_data.values() if v is not None and v != "" and v != 0)

        if filled < 3:
            issues.append("Very few fields extracted")

        # Check for garbage in text
        if raw_text:
            garbage_ratio = sum(1 for c in raw_text if not c.isalnum() and not c.isspace()) / max(len(raw_text), 1)
            if garbage_ratio > 0.3:
                issues.append("High garbage character ratio")

        # Use LLM for deeper assessment if available
        if self.openai_client and extracted_data:
            try:
                prompt = f"""Rate this invoice extraction quality (0.0 to 1.0):

DATA: {json.dumps(extracted_data, indent=2)[:800]}

CRITERIA:
- 0.0-0.2: Garbage/corrupted data
- 0.2-0.4: Mostly empty
- 0.4-0.6: Some valid data, incomplete
- 0.6-0.8: Good, most fields valid
- 0.8-1.0: Excellent, all fields valid

Return ONLY a decimal number."""

                response = await asyncio.wait_for(
                    self.openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=10,
                        temperature=0.1,
                    ),
                    timeout=10.0
                )

                score = float(response.choices[0].message.content.strip())
                return max(0.0, min(1.0, score)), issues

            except Exception as e:
                logger.warning(f"Quality assessment failed: {e}")

        # Heuristic fallback
        heuristic_score = min(1.0, filled / 8)
        if issues:
            heuristic_score *= 0.6
        return heuristic_score, issues

    async def _reason_about_failure(
        self,
        state: AgentState,
        attempt: ExtractionAttempt
    ) -> List[StrategyType]:
        """Reason about extraction failure and suggest next strategies."""
        if not self.openai_client:
            return [StrategyType.GPT4_VISION]

        attempts_summary = "\n".join([
            f"- {a.strategy.value}: quality={a.quality_score:.2f}"
            for a in state.attempts
        ])

        available = [s.value for s in StrategyType
                     if s not in [a.strategy for a in state.attempts]]

        prompt = f"""Analyze this invoice extraction failure and suggest next strategy.

FILE TYPE: {state.file_type}

ATTEMPTS:
{attempts_summary}

LAST RAW TEXT (first 200 chars):
{attempt.raw_text[:200]}

AVAILABLE: {available}

Consider:
- Garbled text -> try different preprocessing
- Missing fields -> try table extraction
- Handwritten -> try EasyOCR
- All else fails -> use GPT-4 Vision

Return JSON array of strategies to try: ["strategy1"]"""

        try:
            response = await asyncio.wait_for(
                self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=50,
                    temperature=0.3,
                ),
                timeout=10.0
            )

            result = json.loads(response.choices[0].message.content.strip())
            return [StrategyType(s) for s in result if s in [st.value for st in StrategyType]]

        except Exception:
            return [StrategyType.GPT4_VISION]

    async def _extract_with_vision(
        self,
        file_bytes: bytes,
        filename: str
    ) -> Optional[Dict[str, Any]]:
        """Extract invoice data using GPT-4 Vision."""
        if not self.openai_client:
            return None

        try:
            # Encode image
            image_data = base64.b64encode(file_bytes).decode("utf-8")

            # Determine media type
            ext = filename.lower().split('.')[-1] if '.' in filename else 'jpeg'
            media_type = "image/png" if ext == "png" else "image/jpeg"

            prompt = """Extract invoice data from this image. Return a JSON object:

{
    "contractor_name": "string or null",
    "contractor_email": "string or null",
    "contractor_address": "string or null",
    "contractor_utr": "string or null",
    "contractor_ni": "string or null",
    "bank_account": "string or null",
    "sort_code": "string or null",
    "invoice_number": "string or null",
    "invoice_date": "string or null",
    "subtotal": number or null,
    "vat_amount": number or null,
    "cis_amount": number or null,
    "total": number or null
}

Return ONLY valid JSON."""

            response = await asyncio.wait_for(
                self.openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{image_data}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }],
                    max_tokens=1000,
                    temperature=0.1,
                ),
                timeout=30.0
            )

            result_text = response.choices[0].message.content.strip()
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]

            return json.loads(result_text)

        except Exception as e:
            logger.error(f"Vision extraction failed: {e}")
            return None

    async def _extract_with_vision_only(
        self,
        file_bytes: bytes,
        filename: str,
        state: AgentState
    ) -> Tuple[Dict[str, Any], AgentState]:
        """Fallback when E2B is not available - use vision only."""
        result = await self._extract_with_vision(file_bytes, filename)

        if result:
            quality, issues = await self._assess_quality("", result)
            state.best_attempt = ExtractionAttempt(
                strategy=StrategyType.GPT4_VISION,
                raw_text="",
                extracted_data=result,
                quality_score=quality,
                quality_issues=issues,
                execution_time_ms=0
            )
            state.reasoning_history.append(f"Vision-only extraction, quality: {quality:.2f}")
            return result, state

        state.reasoning_history.append("Vision extraction failed")
        return {}, state
