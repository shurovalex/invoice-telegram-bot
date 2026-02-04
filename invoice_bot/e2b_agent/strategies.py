"""
Extraction Strategies for E2B Agent.

Each strategy is a Python code template that runs inside the E2B sandbox.
Strategies are ordered by speed/cost and best use case.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class StrategyType(Enum):
    """Available extraction strategy types."""
    PYTESSERACT_BASIC = "pytesseract_basic"
    PYTESSERACT_ENHANCED = "pytesseract_enhanced"
    PDFPLUMBER_TEXT = "pdfplumber_text"
    PDFPLUMBER_TABLES = "pdfplumber_tables"
    EASYOCR = "easyocr"
    GPT4_VISION = "gpt4_vision"


@dataclass
class ExtractionStrategy:
    """Defines an extraction strategy."""
    name: StrategyType
    description: str
    code_template: str
    cost_tier: int  # 1=cheap/fast, 5=expensive/slow
    best_for: List[str]
    requires_packages: List[str]


# Strategy code templates
# These run INSIDE the E2B sandbox

PYTESSERACT_BASIC_CODE = '''
import pytesseract
from PIL import Image
import sys

try:
    image = Image.open("{file_path}")
    text = pytesseract.image_to_string(image)
    print("===EXTRACTED_TEXT_START===")
    print(text)
    print("===EXTRACTED_TEXT_END===")
except Exception as e:
    print(f"ERROR: {{e}}", file=sys.stderr)
'''

PYTESSERACT_ENHANCED_CODE = '''
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import sys

try:
    # Load image
    image = Image.open("{file_path}")

    # Convert to grayscale
    if image.mode != 'L':
        image = image.convert('L')

    # Enhance contrast
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)

    # Sharpen
    image = image.filter(ImageFilter.SHARPEN)

    # Apply threshold
    image = image.point(lambda p: 255 if p > 140 else 0)

    # OCR with optimized settings
    custom_config = r'--oem 3 --psm 6'
    text = pytesseract.image_to_string(image, config=custom_config)

    print("===EXTRACTED_TEXT_START===")
    print(text)
    print("===EXTRACTED_TEXT_END===")
except Exception as e:
    print(f"ERROR: {{e}}", file=sys.stderr)
'''

PDFPLUMBER_TEXT_CODE = '''
import pdfplumber
import sys

try:
    text_parts = []
    with pdfplumber.open("{file_path}") as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    text = "\\n\\n".join(text_parts)
    print("===EXTRACTED_TEXT_START===")
    print(text)
    print("===EXTRACTED_TEXT_END===")
except Exception as e:
    print(f"ERROR: {{e}}", file=sys.stderr)
'''

PDFPLUMBER_TABLES_CODE = '''
import pdfplumber
import json
import sys

try:
    all_data = {"text": [], "tables": []}
    with pdfplumber.open("{file_path}") as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                all_data["text"].append(page_text)

            tables = page.extract_tables()
            for table in tables:
                all_data["tables"].append(table)

    # Flatten to text representation
    text = "\\n\\n".join(all_data["text"])
    if all_data["tables"]:
        text += "\\n\\nTABLES:\\n"
        for i, table in enumerate(all_data["tables"]):
            text += f"\\nTable {{i+1}}:\\n"
            for row in table:
                text += " | ".join(str(cell) for cell in row if cell) + "\\n"

    print("===EXTRACTED_TEXT_START===")
    print(text)
    print("===EXTRACTED_TEXT_END===")
except Exception as e:
    print(f"ERROR: {{e}}", file=sys.stderr)
'''

EASYOCR_CODE = '''
import easyocr
import sys

try:
    reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    results = reader.readtext("{file_path}", detail=0)
    text = "\\n".join(results)

    print("===EXTRACTED_TEXT_START===")
    print(text)
    print("===EXTRACTED_TEXT_END===")
except Exception as e:
    print(f"ERROR: {{e}}", file=sys.stderr)
'''


# Strategy registry
STRATEGIES = {
    StrategyType.PYTESSERACT_BASIC: ExtractionStrategy(
        name=StrategyType.PYTESSERACT_BASIC,
        description="Basic pytesseract OCR with default settings",
        code_template=PYTESSERACT_BASIC_CODE,
        cost_tier=1,
        best_for=["clear_print", "digital_pdf", "high_quality_scan"],
        requires_packages=["pytesseract", "Pillow"],
    ),

    StrategyType.PYTESSERACT_ENHANCED: ExtractionStrategy(
        name=StrategyType.PYTESSERACT_ENHANCED,
        description="Pytesseract with image preprocessing (grayscale, contrast, threshold)",
        code_template=PYTESSERACT_ENHANCED_CODE,
        cost_tier=1,
        best_for=["low_contrast", "faded_text", "scanned_document"],
        requires_packages=["pytesseract", "Pillow"],
    ),

    StrategyType.PDFPLUMBER_TEXT: ExtractionStrategy(
        name=StrategyType.PDFPLUMBER_TEXT,
        description="PDFPlumber text extraction for digital PDFs",
        code_template=PDFPLUMBER_TEXT_CODE,
        cost_tier=1,
        best_for=["digital_pdf", "text_pdf", "native_pdf"],
        requires_packages=["pdfplumber"],
    ),

    StrategyType.PDFPLUMBER_TABLES: ExtractionStrategy(
        name=StrategyType.PDFPLUMBER_TABLES,
        description="PDFPlumber with table extraction",
        code_template=PDFPLUMBER_TABLES_CODE,
        cost_tier=1,
        best_for=["invoice_with_tables", "structured_pdf", "itemized_invoice"],
        requires_packages=["pdfplumber"],
    ),

    StrategyType.EASYOCR: ExtractionStrategy(
        name=StrategyType.EASYOCR,
        description="EasyOCR neural network based recognition",
        code_template=EASYOCR_CODE,
        cost_tier=2,
        best_for=["handwritten", "varied_fonts", "complex_backgrounds"],
        requires_packages=["easyocr"],
    ),
}


def get_strategy_order(file_type: str) -> List[StrategyType]:
    """
    Get ordered list of strategies to try based on file type.

    Strategies are ordered by:
    1. Cost tier (cheaper first)
    2. Likelihood of success for file type
    """
    if file_type == "pdf":
        return [
            StrategyType.PDFPLUMBER_TEXT,
            StrategyType.PDFPLUMBER_TABLES,
            StrategyType.PYTESSERACT_BASIC,
            StrategyType.PYTESSERACT_ENHANCED,
            StrategyType.GPT4_VISION,
        ]
    else:  # image
        return [
            StrategyType.PYTESSERACT_BASIC,
            StrategyType.PYTESSERACT_ENHANCED,
            StrategyType.EASYOCR,
            StrategyType.GPT4_VISION,
        ]
