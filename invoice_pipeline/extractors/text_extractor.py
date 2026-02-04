"""
Invoice Processing Pipeline - Text File Extractor
Handles plain text files.
"""

import os
import logging
from typing import Optional, List
from pathlib import Path
import re

from ..models import InvoiceData, ExtractionResult, Contractor, Address, BankDetails, Financials, WorkItem, WorkPeriod
from ..utils import (
    clean_text, InvoicePatterns, extract_pattern, parse_date_flexible,
    parse_money, extract_address, parse_date_range
)

logger = logging.getLogger(__name__)


class TextFileExtractor:
    """Extract invoice data from plain text files."""
    
    def __init__(self, encoding: str = 'utf-8'):
        """
        Initialize text file extractor.
        
        Args:
            encoding: Default text encoding
        """
        self.encoding = encoding
        self.encodings_to_try = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1', 'ascii']
    
    def extract_text(self, file_path: str) -> str:
        """
        Extract text from file with automatic encoding detection.
        
        Args:
            file_path: Path to text file
            
        Returns:
            Extracted text
        """
        # Try different encodings
        for encoding in self.encodings_to_try:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    text = f.read()
                    logger.info(f"Successfully read file with {encoding} encoding")
                    return text
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.warning(f"Failed to read with {encoding}: {e}")
                continue
        
        # Last resort: read as binary and decode with errors ignored
        try:
            with open(file_path, 'rb') as f:
                raw = f.read()
                return raw.decode('utf-8', errors='ignore')
        except Exception as e:
            raise RuntimeError(f"Failed to read file: {e}")
    
    def extract(self, file_path: str) -> ExtractionResult:
        """
        Extract invoice data from text file.
        
        Args:
            file_path: Path to text file
            
        Returns:
            ExtractionResult with invoice data
        """
        import time
        start_time = time.time()
        
        try:
            # Verify file exists
            if not os.path.exists(file_path):
                return ExtractionResult(
                    success=False,
                    method='text_extraction',
                    error_message=f"File not found: {file_path}"
                )
            
            # Extract text
            text = self.extract_text(file_path)
            
            if not text.strip():
                return ExtractionResult(
                    success=False,
                    method='text_extraction',
                    error_message="No text extracted from file"
                )
            
            # Parse invoice data
            invoice_data = self._parse_invoice_text(text)
            invoice_data.raw_text = text[:5000]
            
            processing_time = int((time.time() - start_time) * 1000)
            
            return ExtractionResult(
                success=True,
                method='text_extraction',
                data=invoice_data,
                confidence=invoice_data.extraction_confidence,
                processing_time_ms=processing_time,
                raw_text=text[:2000]
            )
            
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")
            processing_time = int((time.time() - start_time) * 1000)
            
            return ExtractionResult(
                success=False,
                method='text_extraction',
                error_message=str(e),
                processing_time_ms=processing_time
            )
    
    def _parse_invoice_text(self, text: str) -> InvoiceData:
        """Parse invoice data from extracted text."""
        invoice_data = InvoiceData(extraction_method='text_extraction')
        
        # Clean the text
        text = clean_text(text)
        
        # Extract invoice number
        invoice_number = extract_pattern(text, InvoicePatterns.INVOICE_NUMBER)
        if invoice_number:
            invoice_data.invoice_number = invoice_number
        
        # Extract invoice date
        for pattern in InvoicePatterns.DATE_PATTERNS:
            date_str = extract_pattern(text, pattern)
            if date_str:
                invoice_data.invoice_date = parse_date_flexible(date_str)
                if invoice_data.invoice_date:
                    break
        
        # Extract work period
        period_start = extract_pattern(text, InvoicePatterns.PERIOD_START)
        period_end = extract_pattern(text, InvoicePatterns.PERIOD_END)
        
        if period_start or period_end:
            invoice_data.work_period = WorkPeriod(
                start_date=parse_date_flexible(period_start) if period_start else None,
                end_date=parse_date_flexible(period_end) if period_end else None
            )
        else:
            start, end = parse_date_range(text)
            if start or end:
                invoice_data.work_period = WorkPeriod(start_date=start, end_date=end)
        
        # Extract contractor information
        contractor = Contractor()
        
        utr = extract_pattern(text, InvoicePatterns.UTR)
        if utr:
            contractor.utr = utr
        
        ni = extract_pattern(text, InvoicePatterns.NI_NUMBER)
        if ni:
            contractor.ni_number = ni
        
        vat = extract_pattern(text, InvoicePatterns.VAT_NUMBER)
        if vat:
            contractor.vat_number = vat
        
        company = extract_pattern(text, InvoicePatterns.COMPANY_NUMBER)
        if company:
            contractor.company_number = company
        
        email = extract_pattern(text, InvoicePatterns.EMAIL)
        if email:
            contractor.email = email.lower()
        
        phone = extract_pattern(text, InvoicePatterns.PHONE)
        if phone:
            contractor.phone = phone
        
        bank = BankDetails()
        sort_code = extract_pattern(text, InvoicePatterns.SORT_CODE)
        if sort_code:
            bank.sort_code = sort_code
        
        account = extract_pattern(text, InvoicePatterns.ACCOUNT_NUMBER)
        if account:
            bank.account_number = account
        
        if sort_code or account:
            contractor.bank_details = bank
        
        address_info = extract_address(text)
        if any(address_info.values()):
            contractor.address = Address(**address_info)
        
        # Try to find contractor name
        # First try to find company name at the top of the document
        lines = text.strip().split('\n')
        for line in lines[:5]:  # Check first 5 lines
            line = line.strip()
            # Look for company indicators
            if re.search(r'(?:Ltd|Limited|LLP|Inc|Company|Co\.)', line, re.IGNORECASE):
                if len(line) > 3 and not line.lower().startswith('invoice'):
                    contractor.name = line
                    break
        
        # If not found, try patterns
        if not contractor.name:
            contractor_patterns = [
                r'(?:From)[:\s]*\n?\s*([A-Z][A-Za-z0-9\s&.,]+(?:Ltd|Limited|LLP|Inc|Co|Company)?)',
                r'(?:Contractor|Subcontractor|Supplier)[:\s]*\n?\s*Name[:\s]*([A-Z][A-Za-z0-9\s&.,]+)',
                r'^([A-Z][A-Za-z\s&.,]+(?:Ltd|Limited|LLP|Inc|Co|Company)?)',
            ]
            
            for pattern in contractor_patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    name = match.group(1).strip()
                    # Exclude common non-name words
                    exclude_words = ['details', 'information', 'info', 'name', 'address']
                    if not any(word in name.lower() for word in exclude_words):
                        contractor.name = name
                        break
        
        if any([contractor.name, contractor.utr, contractor.email]):
            invoice_data.contractor = contractor
        
        # Extract financials
        financials = Financials()
        
        subtotal = extract_pattern(text, InvoicePatterns.SUBTOTAL)
        if subtotal:
            financials.subtotal = parse_money(subtotal)
        
        vat_amount = extract_pattern(text, InvoicePatterns.VAT_AMOUNT)
        if vat_amount:
            financials.vat_amount = parse_money(vat_amount)
        
        vat_rate = extract_pattern(text, InvoicePatterns.VAT_RATE)
        if vat_rate:
            try:
                financials.vat_rate = parse_money(vat_rate)
            except:
                pass
        
        cis = extract_pattern(text, InvoicePatterns.CIS_DEDUCTION)
        if cis:
            financials.cis_deduction = parse_money(cis)
        
        total = extract_pattern(text, InvoicePatterns.TOTAL_DUE)
        if total:
            financials.total_due = parse_money(total)
        
        if any([financials.subtotal, financials.total_due]):
            invoice_data.financials = financials
        
        # Extract work items
        work_items = self._extract_work_items(text)
        if work_items:
            invoice_data.work_items = work_items
        
        # Calculate confidence
        invoice_data.extraction_confidence = invoice_data.completeness_score()
        
        return invoice_data
    
    def _extract_work_items(self, text: str) -> List[WorkItem]:
        """Extract work items from text."""
        work_items = []
        
        # Look for plot/property references
        plots = InvoicePatterns.PLOT_NUMBER.findall(text)
        
        for plot in plots:
            item = WorkItem(plot_number=plot)
            
            # Try to find associated description
            pattern = re.compile(
                rf'(?:Plot|Property)[:\s#]*{re.escape(plot)}.*?\n(.{{50,200}})',
                re.IGNORECASE | re.DOTALL
            )
            match = pattern.search(text)
            if match:
                item.description = match.group(1).strip()
            
            work_items.append(item)
        
        # If no plots found, look for operative names
        if not work_items:
            operatives = InvoicePatterns.OPERATIVE.findall(text)
            for op in operatives:
                item = WorkItem(operative_names=[op])
                work_items.append(item)
        
        return work_items


def extract_from_text(file_path: str) -> ExtractionResult:
    """Convenience function for text file extraction."""
    extractor = TextFileExtractor()
    return extractor.extract(file_path)
