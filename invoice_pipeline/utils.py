"""
Invoice Processing Pipeline - Utility Functions
Helper functions for text processing, pattern matching, and data extraction.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple, Pattern
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import dateparser

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# REGEX PATTERNS FOR INVOICE EXTRACTION
# =============================================================================

class InvoicePatterns:
    """Collection of regex patterns for extracting invoice data."""
    
    # Invoice numbers - various formats
    INVOICE_NUMBER = re.compile(
        r'(?:invoice\s*(?:#|no\.?|number)?[:\s]+)'  # Invoice prefix
        r'([A-Z]{0,3}-?\d[\w\-/]*)',  # The number itself (must start with digit after optional prefix)
        re.IGNORECASE
    )
    
    # Dates - various formats
    DATE_PATTERNS = [
        re.compile(r'(?:invoice\s*)?date[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', re.IGNORECASE),
        re.compile(r'(?:invoice\s*)?date[:\s]*(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})', re.IGNORECASE),
        re.compile(r'(?:date|dated)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', re.IGNORECASE),
    ]
    
    # Period patterns
    PERIOD_START = re.compile(
        r'(?:period\s*(?:start|from|beginning)|week\s*(?:ending|ended)|'
        r'work\s*(?:period|week)[:\s]*(?:from)?)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        re.IGNORECASE
    )
    
    PERIOD_END = re.compile(
        r'(?:period\s*(?:end|to|ending)|week\s*(?:ending|ended)|'
        r'to[:\s]*)(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        re.IGNORECASE
    )
    
    # UTR (Unique Taxpayer Reference) - 10 digits
    UTR = re.compile(
        r'(?:UTR|Unique\s*Taxpayer\s*Reference|Tax\s*Ref)[:\s#]*(\d{10})',
        re.IGNORECASE
    )
    
    # National Insurance Number
    NI_NUMBER = re.compile(
        r'(?:NI|National\s*Insurance|N\.I\.)[:\s#]*([A-Z]{2}\s*\d{2}\s*\d{2}\s*\d{2}\s*[A-Z])',
        re.IGNORECASE
    )
    
    # VAT Number
    VAT_NUMBER = re.compile(
        r'(?:VAT|VAT\s*(?:No|Number|Reg|Registration))[:\s#]*(GB\s*\d{9}(?:\s*\d{3})?)',
        re.IGNORECASE
    )
    
    # Company Number
    COMPANY_NUMBER = re.compile(
        r'(?:Company\s*(?:No|Number|Reg|Registration)|Co\s*No)[:\s#]*(\d{8})',
        re.IGNORECASE
    )
    
    # Email addresses
    EMAIL = re.compile(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    )
    
    # Phone numbers (UK)
    PHONE = re.compile(
        r'(?:Tel|Telephone|Phone|Mobile|Mob|Cell)[:\s]*([\d\s\-+()]{10,20})',
        re.IGNORECASE
    )
    
    # Postcodes (UK)
    POSTCODE = re.compile(
        r'\b([A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})\b'
    )
    
    # Bank details
    SORT_CODE = re.compile(
        r'(?:Sort\s*Code|SC)[:\s]*(\d{2}[\s\-]?\d{2}[\s\-]?\d{2})',
        re.IGNORECASE
    )
    
    ACCOUNT_NUMBER = re.compile(
        r'(?:Account\s*(?:No|Number|#)|Acc\s*No|A/C)[:\s]*(\d{6,8})',
        re.IGNORECASE
    )
    
    # Money amounts
    MONEY_AMOUNT = re.compile(
        r'[£$€]?\s*(\d{1,3}(?:,\d{3})*\.\d{2}|\d+\.\d{2}|\d{1,3}(?:,\d{3})*|\d+)'
    )
    
    # Financial labels
    SUBTOTAL = re.compile(
        r'(?:Sub[\s\-]?total|Net|Nett|Subtotal|Total\s*before\s*VAT)[:\s£$€]*([\d,.]+)',
        re.IGNORECASE
    )
    
    VAT_AMOUNT = re.compile(
        r'(?:VAT|V\.A\.T|Tax)(?:\s*@\s*\d+%?)?[:\s£$€]*([\d,.]+)',
        re.IGNORECASE
    )
    
    VAT_RATE = re.compile(
        r'VAT\s*(?:@|at)\s*(\d+(?:\.\d+)?)\s*%',
        re.IGNORECASE
    )
    
    CIS_DEDUCTION = re.compile(
        r'(?:CIS|Construction\s*Industry\s*Scheme)(?:\s*(?:deduction|deducted))?[:\s£$€\-]*([\d,.]+)',
        re.IGNORECASE
    )
    
    TOTAL_DUE = re.compile(
        r'(?:Total\s*(?:Due|Amount)|Amount\s*Due|Grand\s*Total|Balance\s*Due)[:\s£$€]*([\d,.]+)',
        re.IGNORECASE
    )
    
    # Plot/Property numbers
    PLOT_NUMBER = re.compile(
        r'(?:Plot|Property|Unit|House)[:\s#]*(\d+[A-Z]?)',
        re.IGNORECASE
    )
    
    # Operative/Worker names
    OPERATIVE = re.compile(
        r'(?:Operative|Worker|Employee|Subcontractor|Name)[:\s]*([A-Z][a-z]+\s+[A-Z][a-z]+)',
        re.IGNORECASE
    )


# =============================================================================
# TEXT PROCESSING UTILITIES
# =============================================================================

def clean_text(text: str) -> str:
    """Clean and normalize extracted text."""
    if not text:
        return ""
    
    # Replace multiple whitespace with single space
    text = re.sub(r'\s+', ' ', text)
    
    # Remove null bytes and control characters
    text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', text)
    
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # Remove excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text."""
    if not text:
        return ""
    return ' '.join(text.split())


def extract_lines(text: str) -> List[str]:
    """Extract non-empty lines from text."""
    if not text:
        return []
    lines = text.split('\n')
    return [line.strip() for line in lines if line.strip()]


def find_nearby_text(text: str, keyword: str, context_chars: int = 100) -> List[str]:
    """Find text near a keyword."""
    if not text or not keyword:
        return []
    
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    matches = []
    
    for match in pattern.finditer(text):
        start = max(0, match.start() - context_chars)
        end = min(len(text), match.end() + context_chars)
        matches.append(text[start:end])
    
    return matches


# =============================================================================
# DATE PARSING UTILITIES
# =============================================================================

def parse_date_flexible(date_str: str) -> Optional[date]:
    """Parse date from string using multiple formats."""
    if not date_str:
        return None
    
    # Clean the string
    date_str = date_str.strip()
    
    # Try dateparser first (most flexible)
    try:
        parsed = dateparser.parse(date_str, settings={'DATE_ORDER': 'DMY'})
        if parsed:
            return parsed.date()
    except Exception:
        pass
    
    # Manual format attempts
    formats = [
        '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y',
        '%Y/%m/%d', '%Y-%m-%d', '%Y.%m.%d',
        '%d/%m/%y', '%d-%m-%y', '%d.%m.%y',
        '%d %B %Y', '%d %b %Y',
        '%B %d, %Y', '%b %d, %Y',
        '%d%m%Y', '%Y%m%d',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    
    return None


def parse_date_range(text: str) -> Tuple[Optional[date], Optional[date]]:
    """Extract date range from text."""
    # Look for patterns like "01/01/2024 to 31/01/2024" or "01/01/2024 - 31/01/2024"
    patterns = [
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:to|through|thru|-)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'(?:from|period|week)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:to|through|thru|-)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start = parse_date_flexible(match.group(1))
            end = parse_date_flexible(match.group(2))
            return start, end
    
    return None, None


# =============================================================================
# MONEY PARSING UTILITIES
# =============================================================================

def parse_money(amount_str: str) -> Optional[Decimal]:
    """Parse monetary amount from string."""
    if not amount_str:
        return None
    
    # Remove currency symbols and whitespace
    cleaned = re.sub(r'[£$€,\s]', '', amount_str.strip())
    
    # Handle negative amounts
    is_negative = cleaned.startswith('-') or cleaned.startswith('(')
    cleaned = re.sub(r'[\-()]', '', cleaned)
    
    try:
        amount = Decimal(cleaned)
        if is_negative:
            amount = -amount
        return amount
    except (InvalidOperation, ValueError):
        return None


def find_money_in_text(text: str) -> List[Decimal]:
    """Find all monetary amounts in text."""
    amounts = []
    pattern = re.compile(r'[£$€]?\s*(\d{1,3}(?:,\d{3})*\.\d{2}|\d+\.\d{2})')
    
    for match in pattern.finditer(text):
        amount = parse_money(match.group(0))
        if amount is not None:
            amounts.append(amount)
    
    return amounts


# =============================================================================
# PATTERN EXTRACTION UTILITIES
# =============================================================================

def extract_pattern(text: str, pattern: Pattern, group: int = 1) -> Optional[str]:
    """Extract a single match from text using pattern."""
    if not text:
        return None
    
    match = pattern.search(text)
    if match:
        try:
            return match.group(group).strip()
        except IndexError:
            return None
    return None


def extract_all_patterns(text: str, pattern: Pattern, group: int = 1) -> List[str]:
    """Extract all matches from text using pattern."""
    if not text:
        return []
    
    matches = []
    for match in pattern.finditer(text):
        try:
            value = match.group(group).strip()
            if value:
                matches.append(value)
        except IndexError:
            continue
    
    return matches


def extract_with_context(text: str, pattern: Pattern, context_lines: int = 2) -> List[Dict[str, Any]]:
    """Extract matches with surrounding context."""
    if not text:
        return []
    
    lines = text.split('\n')
    results = []
    
    for i, line in enumerate(lines):
        match = pattern.search(line)
        if match:
            # Get context lines
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            context = '\n'.join(lines[start:end])
            
            results.append({
                'match': match.group(0),
                'line': line,
                'context': context,
                'line_number': i
            })
    
    return results


# =============================================================================
# ADDRESS EXTRACTION
# =============================================================================

def extract_address(text: str) -> Dict[str, str]:
    """Extract address components from text."""
    address = {
        'street': None,
        'city': None,
        'postcode': None,
        'country': 'UK'
    }
    
    # Extract postcode first (most reliable)
    postcode_match = InvoicePatterns.POSTCODE.search(text)
    if postcode_match:
        address['postcode'] = postcode_match.group(1).upper()
    
    # Look for common UK cities
    uk_cities = [
        'London', 'Birmingham', 'Manchester', 'Leeds', 'Glasgow', 'Sheffield',
        'Bradford', 'Liverpool', 'Edinburgh', 'Bristol', 'Cardiff', 'Belfast',
        'Leicester', 'Coventry', 'Nottingham', 'Newcastle', 'Hull', 'Plymouth',
        'Stoke', 'Wolverhampton', 'Derby', 'Swansea', 'Southampton', 'Aberdeen',
        'Portsmouth', 'York', 'Peterborough', 'Dundee', 'Lancaster', 'Oxford'
    ]
    
    city_pattern = re.compile(
        r'\b(' + '|'.join(uk_cities) + r')\b',
        re.IGNORECASE
    )
    city_match = city_pattern.search(text)
    if city_match:
        address['city'] = city_match.group(1)
    
    return address


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

def is_valid_email(email: str) -> bool:
    """Validate email address format."""
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def is_valid_uk_postcode(postcode: str) -> bool:
    """Validate UK postcode format."""
    if not postcode:
        return False
    pattern = r'^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$'
    return bool(re.match(pattern, postcode.upper().replace(' ', '')))


def is_valid_utr(utr: str) -> bool:
    """Validate UTR format (10 digits)."""
    if not utr:
        return False
    utr = re.sub(r'\D', '', utr)
    return len(utr) == 10


def is_valid_ni_number(ni: str) -> bool:
    """Validate National Insurance number format."""
    if not ni:
        return False
    ni = ni.upper().replace(' ', '')
    pattern = r'^[A-Z]{2}\d{6}[A-Z]$'
    return bool(re.match(pattern, ni))


# =============================================================================
# CONFIDENCE SCORING
# =============================================================================

def calculate_extraction_confidence(text: str, extracted_data: Dict[str, Any]) -> float:
    """Calculate confidence score based on extracted data completeness."""
    if not text or not extracted_data:
        return 0.0
    
    confidence = 0.0
    checks = 0
    
    # Check for invoice number
    if extracted_data.get('invoice_number'):
        confidence += 0.15
    checks += 1
    
    # Check for invoice date
    if extracted_data.get('invoice_date'):
        confidence += 0.15
    checks += 1
    
    # Check for contractor name
    contractor = extracted_data.get('contractor', {})
    if contractor and contractor.get('name'):
        confidence += 0.15
    checks += 1
    
    # Check for financials
    financials = extracted_data.get('financials', {})
    if financials:
        if financials.get('subtotal') or financials.get('total_due'):
            confidence += 0.2
        if financials.get('vat_amount') is not None:
            confidence += 0.1
    checks += 2
    
    # Check for work items
    work_items = extracted_data.get('work_items', [])
    if work_items:
        confidence += min(len(work_items) * 0.1, 0.25)
    checks += 1
    
    return min(confidence, 1.0)


def merge_confidence_scores(scores: List[float]) -> float:
    """Merge multiple confidence scores, giving weight to higher scores."""
    if not scores:
        return 0.0
    
    # Weighted average favoring higher scores
    weighted_sum = sum(s ** 2 for s in scores)
    total_weight = sum(scores)
    
    if total_weight == 0:
        return 0.0
    
    return weighted_sum / total_weight
