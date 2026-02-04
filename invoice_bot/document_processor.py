#!/usr/bin/env python3
"""
Document processing module for extracting invoice data from uploaded files.
Supports PDF, DOCX, and image files (JPEG, PNG).
"""

import os
import re
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from invoice_bot.invoice_data import InvoiceData, WorkItem

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Process uploaded documents and extract invoice data."""
    
    def __init__(self):
        self.patterns = self._compile_patterns()
    
    def _compile_patterns(self) -> Dict[str, re.Pattern]:
        """Compile regex patterns for data extraction."""
        return {
            # Email pattern
            "email": re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'),
            
            # UK Postcode pattern
            "postcode": re.compile(r'[A-Z]{1,2}[0-9][A-Z0-9]?\s*[0-9][A-Z]{2}'),
            
            # Phone pattern
            "phone": re.compile(r'(?:\+44|0)\s?[0-9]{4}\s?[0-9]{6}'),
            
            # UTR pattern (10 digits)
            "utr": re.compile(r'\b\d{10}\b'),
            
            # NI Number pattern
            "ni_number": re.compile(r'[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]'),
            
            # Sort code pattern
            "sort_code": re.compile(r'\b\d{2}[-\s]?\d{2}[-\s]?\d{2}\b'),
            
            # Bank account pattern (8 digits)
            "bank_account": re.compile(r'\b\d{8}\b'),
            
            # Invoice number patterns
            "invoice_number": re.compile(r'(?:invoice\s*(?:#|number|no)?[:\s]*)?([A-Z0-9-]{3,20})', re.IGNORECASE),
            
            # Date patterns (DD/MM/YYYY or variations)
            "date": re.compile(r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b'),
            
            # Currency amounts
            "amount": re.compile(r'£?\s*(\d{1,3}(?:,\d{3})*\.?\d{0,2})'),
            
            # VAT amount
            "vat": re.compile(r'(?:vat|tax)[:\s]*£?\s*(\d+\.?\d{0,2})', re.IGNORECASE),
            
            # CIS deduction
            "cis": re.compile(r'(?:cis|deduction)[:\s]*£?\s*(\d+\.?\d{0,2})', re.IGNORECASE),
            
            # Subtotal/Total patterns
            "subtotal": re.compile(r'(?:subtotal|sub-total|net)[:\s]*£?\s*(\d+\.?\d{0,2})', re.IGNORECASE),
            "total": re.compile(r'(?:total|amount\s*due|grand\s*total)[:\s]*£?\s*(\d+\.?\d{0,2})', re.IGNORECASE),
        }
    
    async def process_document(self, file_path: str, mime_type: str) -> InvoiceData:
        """
        Process a document and extract invoice data.
        
        Args:
            file_path: Path to the downloaded file
            mime_type: MIME type of the file
            
        Returns:
            InvoiceData object with extracted information
        """
        logger.info(f"Processing document: {file_path}, MIME: {mime_type}")
        
        # Extract text from document
        text = await self._extract_text(file_path, mime_type)
        
        if not text:
            logger.warning("No text extracted from document")
            return InvoiceData()
        
        logger.info(f"Extracted text length: {len(text)}")
        
        # Parse invoice data from text
        invoice_data = self._parse_invoice_data(text)
        
        return invoice_data
    
    async def _extract_text(self, file_path: str, mime_type: str) -> str:
        """Extract text from various document types."""
        try:
            if mime_type == "application/pdf":
                return await self._extract_from_pdf(file_path)
            elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                return await self._extract_from_docx(file_path)
            elif mime_type.startswith("image/"):
                return await self._extract_from_image(file_path)
            else:
                logger.warning(f"Unsupported MIME type: {mime_type}")
                return ""
        except Exception as e:
            logger.error(f"Text extraction error: {e}")
            return ""
    
    async def _extract_from_pdf(self, file_path: str) -> str:
        """Extract text from PDF file."""
        try:
            # Try PyPDF2 first
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        except ImportError:
            logger.warning("PyPDF2 not available, trying pdfplumber")
        
        try:
            # Fallback to pdfplumber
            import pdfplumber
            text = ""
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() + "\n"
            return text
        except ImportError:
            logger.warning("pdfplumber not available")
        
        # Last resort: OCR with pdf2image
        try:
            from pdf2image import convert_from_path
            import pytesseract
            
            images = convert_from_path(file_path)
            text = ""
            for image in images:
                text += pytesseract.image_to_string(image) + "\n"
            return text
        except ImportError:
            logger.error("No PDF extraction library available")
            return ""
    
    async def _extract_from_docx(self, file_path: str) -> str:
        """Extract text from DOCX file."""
        try:
            from docx import Document
            doc = Document(file_path)
            text = ""
            for para in doc.paragraphs:
                text += para.text + "\n"
            
            # Also extract from tables
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        text += cell.text + " "
                    text += "\n"
            
            return text
        except ImportError:
            logger.error("python-docx not available")
            return ""
    
    async def _extract_from_image(self, file_path: str) -> str:
        """Extract text from image using OCR."""
        try:
            import pytesseract
            from PIL import Image
            
            image = Image.open(file_path)
            text = pytesseract.image_to_string(image)
            return text
        except ImportError:
            logger.error("pytesseract or PIL not available")
            return ""
    
    def _parse_invoice_data(self, text: str) -> InvoiceData:
        """Parse invoice data from extracted text."""
        invoice = InvoiceData()
        invoice.source = "upload"
        
        lines = text.split('\n')
        
        # Extract email
        email_match = self.patterns["email"].search(text)
        if email_match:
            invoice.contractor_email = email_match.group(0)
        
        # Extract UTR
        utr_match = self.patterns["utr"].search(text)
        if utr_match:
            invoice.contractor_utr = utr_match.group(0)
        
        # Extract NI number
        ni_match = self.patterns["ni_number"].search(text)
        if ni_match:
            invoice.contractor_ni = ni_match.group(0)
        
        # Extract sort code
        sort_match = self.patterns["sort_code"].search(text)
        if sort_match:
            invoice.sort_code = sort_match.group(0)
        
        # Extract bank account
        bank_match = self.patterns["bank_account"].search(text)
        if bank_match:
            invoice.bank_account = bank_match.group(0)
        
        # Extract invoice number
        inv_match = self.patterns["invoice_number"].search(text)
        if inv_match:
            invoice.invoice_number = inv_match.group(1)
        
        # Extract dates
        dates = self.patterns["date"].findall(text)
        if len(dates) >= 1:
            invoice.invoice_date = f"{dates[0][0]}/{dates[0][1]}/{dates[0][2]}"
        if len(dates) >= 2:
            invoice.work_start_date = f"{dates[1][0]}/{dates[1][1]}/{dates[1][2]}"
        if len(dates) >= 3:
            invoice.work_end_date = f"{dates[2][0]}/{dates[2][1]}/{dates[2][2]}"
        
        # Extract financial amounts
        subtotal_match = self.patterns["subtotal"].search(text)
        if subtotal_match:
            invoice.subtotal = float(subtotal_match.group(1).replace(',', ''))
        
        vat_match = self.patterns["vat"].search(text)
        if vat_match:
            invoice.vat_amount = float(vat_match.group(1).replace(',', ''))
        
        cis_match = self.patterns["cis"].search(text)
        if cis_match:
            invoice.cis_amount = float(cis_match.group(1).replace(',', ''))
        
        total_match = self.patterns["total"].search(text)
        if total_match:
            invoice.total = float(total_match.group(1).replace(',', ''))
        
        # Try to extract contractor name and address
        invoice.contractor_name = self._extract_contractor_name(lines)
        invoice.contractor_address = self._extract_address(lines)
        
        # Extract work items
        invoice.work_items = self._extract_work_items(text, lines)
        
        # Calculate total if not found
        if invoice.total == 0:
            invoice.calculate_total()
        
        return invoice
    
    def _extract_contractor_name(self, lines: List[str]) -> str:
        """Extract contractor name from document."""
        # Look for common patterns
        for i, line in enumerate(lines[:20]):  # Check first 20 lines
            line_lower = line.lower().strip()
            
            # Skip header lines
            if any(skip in line_lower for skip in ['invoice', 'date', 'from:', 'to:', 'bill to']):
                continue
            
            # Look for company indicators
            if any(indicator in line for indicator in ['Ltd', 'Limited', 'LLP', 'Inc', 'Company']):
                return line.strip()
            
            # Look for name patterns (2-3 words, capitalized)
            words = line.strip().split()
            if 2 <= len(words) <= 4:
                if all(w[0].isupper() for w in words if w and w[0].isalpha()):
                    return line.strip()
        
        # Fallback: return first non-empty line that's not a header
        for line in lines:
            stripped = line.strip()
            if stripped and len(stripped) > 3:
                if not any(skip in stripped.lower() for skip in ['invoice', 'date', 'page']):
                    return stripped
        
        return ""
    
    def _extract_address(self, lines: List[str]) -> str:
        """Extract address from document."""
        address_lines = []
        in_address = False
        
        for line in lines[:30]:
            stripped = line.strip()
            
            # Start of address section
            if any(marker in stripped.lower() for marker in ['address:', 'from:', 'contractor address']):
                in_address = True
                continue
            
            if in_address:
                # End of address (empty line or new section)
                if not stripped:
                    if address_lines:
                        break
                    continue
                
                # Check for address indicators
                if any(indicator in stripped for indicator in ['Street', 'Road', 'Lane', 'Avenue', 'Drive']):
                    address_lines.append(stripped)
                elif self.patterns["postcode"].search(stripped):
                    address_lines.append(stripped)
                    break
                elif len(stripped) > 5 and not any(skip in stripped.lower() for skip in ['invoice', 'date', 'email']):
                    address_lines.append(stripped)
        
        return ", ".join(address_lines) if address_lines else ""
    
    def _extract_work_items(self, text: str, lines: List[str]) -> List[WorkItem]:
        """Extract work items from document."""
        work_items = []
        
        # Look for table-like structures or itemized lists
        in_items_section = False
        
        for i, line in enumerate(lines):
            line_lower = line.lower().strip()
            
            # Detect start of items section
            if any(marker in line_lower for marker in ['description', 'items', 'services', 'work performed']):
                in_items_section = True
                continue
            
            if in_items_section:
                # Look for lines with amounts
                amount_match = self.patterns["amount"].search(line)
                if amount_match:
                    amount = float(amount_match.group(1).replace(',', ''))
                    
                    # Extract description (text before amount)
                    description = line[:amount_match.start()].strip()
                    if not description:
                        # Look at previous line for description
                        if i > 0:
                            description = lines[i-1].strip()
                    
                    if description and amount > 0:
                        work_item = WorkItem(
                            description=description,
                            amount=amount
                        )
                        work_items.append(work_item)
                
                # End of items section
                if any(marker in line_lower for marker in ['subtotal', 'total', 'vat', 'thank you']):
                    break
        
        return work_items


class MockDocumentProcessor(DocumentProcessor):
    """Mock processor for testing without OCR dependencies."""
    
    async def process_document(self, file_path: str, mime_type: str) -> InvoiceData:
        """Return sample data for testing."""
        logger.info(f"Mock processing: {file_path}")
        
        # Return sample invoice data
        invoice = InvoiceData(
            contractor_name="ABC Construction Ltd",
            contractor_address="123 Builder Street, London, EC1A 1BB",
            contractor_email="contact@abcconstruction.co.uk",
            contractor_utr="1234567890",
            contractor_ni="AB123456C",
            bank_account="12345678",
            sort_code="12-34-56",
            cardholder_name="John Smith",
            invoice_number="INV-2024-001",
            invoice_date="15/01/2024",
            work_start_date="01/01/2024",
            work_end_date="14/01/2024",
            operative_names="John Smith, Mike Johnson",
            subtotal=2500.00,
            vat_amount=500.00,
            cis_amount=500.00,
            source="upload",
        )
        
        invoice.work_items = [
            WorkItem(
                property_address="45 High Street, London",
                plot="A12",
                description="Kitchen renovation - plumbing and electrics",
                amount=1500.00,
            ),
            WorkItem(
                property_address="45 High Street, London",
                plot="A12",
                description="Bathroom tiling and fixtures",
                amount=1000.00,
            ),
        ]
        
        invoice.calculate_total()
        return invoice
