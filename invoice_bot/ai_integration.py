#!/usr/bin/env python3
"""
AI Integration Module for Self-Healing Invoice Extraction.

This module provides:
1. AI-powered quality assessment of extracted data
2. Vision-based extraction fallback (GPT-4 Vision)
3. Intelligent retry decisions
"""

import asyncio
import base64
import logging
import os
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Quality threshold - below this, extraction is considered failed
QUALITY_THRESHOLD = 0.4


class AIQualityAssessor:
    """
    AI-powered extraction quality assessor.

    Uses OpenAI to:
    1. Assess if extracted data is garbage or valid
    2. Extract data directly from images using vision
    3. Decide whether to retry or accept extraction
    """

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = None
        self._initialized = False

    async def _ensure_client(self):
        """Lazy initialization of OpenAI client."""
        if not self._initialized:
            if not self.api_key:
                logger.warning("OPENAI_API_KEY not set - AI quality assessment disabled")
                self._initialized = True
                return

            try:
                from openai import AsyncOpenAI
                self.client = AsyncOpenAI(api_key=self.api_key)
                self._initialized = True
                logger.info("OpenAI client initialized for quality assessment")
            except ImportError:
                logger.warning("openai package not installed - AI quality assessment disabled")
                self._initialized = True

    async def assess_quality(self, extracted_data: Dict[str, Any]) -> float:
        """
        Use AI to assess if extraction is garbage or valid.

        Returns:
            float: Quality score from 0.0 (garbage) to 1.0 (excellent)
        """
        await self._ensure_client()

        if not self.client:
            # Fallback: basic heuristic assessment
            return self._heuristic_quality_check(extracted_data)

        try:
            prompt = f"""Rate the quality of this invoice data extraction on a scale of 0.0 to 1.0.

EXTRACTED DATA:
- Contractor Name: {extracted_data.get('contractor_name', 'Not found')}
- Email: {extracted_data.get('contractor_email', 'Not found')}
- Address: {extracted_data.get('contractor_address', 'Not found')}
- Invoice Number: {extracted_data.get('invoice_number', 'Not found')}
- Invoice Date: {extracted_data.get('invoice_date', 'Not found')}
- Subtotal: {extracted_data.get('subtotal', 0)}
- Total: {extracted_data.get('total', 0)}

SCORING CRITERIA:
- Score 0.0-0.2: Data is clearly OCR garbage (random characters like "INVaw Wo", "Wes", corrupted text)
- Score 0.2-0.4: Most fields are "Not found" or empty, very little useful data
- Score 0.4-0.6: Some valid data extracted but incomplete
- Score 0.6-0.8: Good extraction with most fields populated correctly
- Score 0.8-1.0: Excellent extraction with all fields looking valid

IMPORTANT: Return ONLY a single decimal number between 0.0 and 1.0, nothing else."""

            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=10,
                    temperature=0.1,
                ),
                timeout=10.0
            )

            score_text = response.choices[0].message.content.strip()
            score = float(score_text)
            score = max(0.0, min(1.0, score))  # Clamp to 0-1

            logger.info(f"AI quality assessment: {score:.2f}")
            return score

        except asyncio.TimeoutError:
            logger.warning("AI quality assessment timed out, using heuristic")
            return self._heuristic_quality_check(extracted_data)
        except Exception as e:
            logger.error(f"AI quality assessment failed: {e}")
            return self._heuristic_quality_check(extracted_data)

    def _heuristic_quality_check(self, data: Dict[str, Any]) -> float:
        """
        Fallback heuristic quality check when AI is unavailable.

        Checks for:
        - Number of populated fields
        - Garbage character detection
        - Valid email format
        - Numeric values present
        """
        score = 0.0
        max_score = 10.0

        # Check contractor name (2 points)
        name = data.get('contractor_name', '')
        if name and name != 'Not found' and len(name) > 2:
            # Check for garbage characters
            if self._is_valid_text(name):
                score += 2.0
            else:
                score += 0.5  # Partial credit for having something

        # Check email (2 points)
        email = data.get('contractor_email', '')
        if email and '@' in email and '.' in email:
            score += 2.0

        # Check address (1 point)
        address = data.get('contractor_address', '')
        if address and address != 'Not found' and len(address) > 5:
            score += 1.0

        # Check invoice number (1.5 points)
        inv_num = data.get('invoice_number', '')
        if inv_num and inv_num != 'Not found':
            score += 1.5

        # Check date (1 point)
        date = data.get('invoice_date', '')
        if date and date != 'Not found':
            score += 1.0

        # Check amounts (2.5 points)
        subtotal = data.get('subtotal', 0)
        total = data.get('total', 0)
        if subtotal and subtotal > 0:
            score += 1.25
        if total and total > 0:
            score += 1.25

        final_score = score / max_score
        logger.info(f"Heuristic quality assessment: {final_score:.2f}")
        return final_score

    def _is_valid_text(self, text: str) -> bool:
        """Check if text looks like valid data vs OCR garbage."""
        if not text:
            return False

        # Count alphanumeric vs special characters
        alpha_count = sum(1 for c in text if c.isalnum() or c.isspace())
        total = len(text)

        if total == 0:
            return False

        # If less than 70% alphanumeric, likely garbage
        ratio = alpha_count / total
        return ratio > 0.7

    async def extract_with_vision(self, image_path: str) -> Optional[Dict[str, Any]]:
        """
        Use GPT-4 Vision to extract invoice data directly from image.

        This is the fallback when OCR produces garbage.
        """
        await self._ensure_client()

        if not self.client:
            logger.warning("OpenAI client not available for vision extraction")
            return None

        try:
            # Read and encode image
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            # Determine image type
            if image_path.lower().endswith('.png'):
                media_type = "image/png"
            else:
                media_type = "image/jpeg"

            prompt = """Analyze this invoice/document image and extract the following information.
Return a JSON object with these fields (use null for fields you cannot find):

{
    "contractor_name": "Full name of the contractor/company",
    "contractor_email": "Email address",
    "contractor_address": "Full address",
    "contractor_utr": "UTR number if present",
    "contractor_ni": "National Insurance number if present",
    "bank_account": "Bank account number",
    "sort_code": "Sort code",
    "invoice_number": "Invoice number/reference",
    "invoice_date": "Invoice date (DD/MM/YYYY format)",
    "work_start_date": "Work start date if present",
    "work_end_date": "Work end date if present",
    "subtotal": 0.00,
    "vat_amount": 0.00,
    "cis_amount": 0.00,
    "total": 0.00
}

IMPORTANT: Return ONLY valid JSON, no other text."""

            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
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
                        }
                    ],
                    max_tokens=1000,
                    temperature=0.1,
                ),
                timeout=30.0
            )

            result_text = response.choices[0].message.content.strip()

            # Parse JSON response
            import json
            # Handle potential markdown code blocks
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]

            data = json.loads(result_text)
            logger.info(f"Vision extraction successful: {list(data.keys())}")
            return data

        except asyncio.TimeoutError:
            logger.error("Vision extraction timed out")
            return None
        except Exception as e:
            logger.error(f"Vision extraction failed: {e}")
            return None


# Global instance
ai_assessor = AIQualityAssessor()
