"""
Invoice Processing Pipeline - PDF Extractor
Handles text and table extraction from PDF files.
"""

import os
import io
import logging
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import re

from ..models import InvoiceData, ExtractionResult, Contractor, Address, BankDetails, Financials, WorkItem, WorkPeriod
from ..utils import (
    clean_text, InvoicePatterns, extract_pattern, parse_date_flexible,
    parse_money, extract_address, parse_date_range, extract_lines
)

logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    logger.warning("pdfplumber not available")

try:
    from PyPDF2 import PdfReader
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    logger.warning("PyPDF2 not available")

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    logger.warning("pdf2image not available")


class PDFTextExtractor:
    """Extract text from PDF using multiple methods."""
    
    def __init__(self):
        self.methods = []
        
        if PDFPLUMBER_AVAILABLE:
            self.methods.append('pdfplumber')
        if PYPDF2_AVAILABLE:
            self.methods.append('pypdf2')
    
    def extract_text(self, file_path: str, method: Optional[str] = None) -> str:
        """
        Extract text from PDF file.
        
        Args:
            file_path: Path to PDF file
            method: Specific method to use (pdfplumber, pypdf2)
            
        Returns:
            Extracted text
        """
        if method:
            if method == 'pdfplumber' and PDFPLUMBER_AVAILABLE:
                return self._extract_with_pdfplumber(file_path)
            elif method == 'pypdf2' and PYPDF2_AVAILABLE:
                return self._extract_with_pypdf2(file_path)
            else:
                raise ValueError(f"Method {method} not available")
        
        # Try all available methods
        texts = []
        errors = []
        
        if PDFPLUMBER_AVAILABLE:
            try:
                text = self._extract_with_pdfplumber(file_path)
                if text.strip():
                    texts.append(('pdfplumber', text))
            except Exception as e:
                errors.append(f"pdfplumber: {e}")
        
        if PYPDF2_AVAILABLE:
            try:
                text = self._extract_with_pypdf2(file_path)
                if text.strip():
                    texts.append(('pypdf2', text))
            except Exception as e:
                errors.append(f"pypdf2: {e}")
        
        if not texts:
            if errors:
                raise RuntimeError(f"All extraction methods failed: {'; '.join(errors)}")
            else:
                raise RuntimeError("No text extracted from PDF")
        
        # Return the longest text (usually most complete)
        texts.sort(key=lambda x: len(x[1]), reverse=True)
        return texts[0][1]
    
    def _extract_with_pdfplumber(self, file_path: str) -> str:
        """Extract text using pdfplumber."""
        all_text = []
        
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_text.append(text)
        
        return '\n\n'.join(all_text)
    
    def _extract_with_pypdf2(self, file_path: str) -> str:
        """Extract text using PyPDF2."""
        all_text = []
        
        with open(file_path, 'rb') as f:
            reader = PdfReader(f)
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    all_text.append(text)
        
        return '\n\n'.join(all_text)
    
    def extract_text_per_page(self, file_path: str) -> List[str]:
        """Extract text from each page separately."""
        pages = []
        
        if PDFPLUMBER_AVAILABLE:
            try:
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        pages.append(text or "")
                return pages
            except Exception as e:
                logger.warning(f"pdfplumber per-page extraction failed: {e}")
        
        if PYPDF2_AVAILABLE:
            try:
                with open(file_path, 'rb') as f:
                    reader = PdfReader(f)
                    for page in reader.pages:
                        text = page.extract_text()
                        pages.append(text or "")
                return pages
            except Exception as e:
                logger.warning(f"pypdf2 per-page extraction failed: {e}")
        
        return pages


class PDFTableExtractor:
    """Extract tables from PDF files."""
    
    def __init__(self):
        if not PDFPLUMBER_AVAILABLE:
            raise RuntimeError("pdfplumber is required for table extraction")
    
    def extract_tables(self, file_path: str) -> List[List[List[str]]]:
        """
        Extract all tables from PDF.
        
        Args:
            file_path: Path to PDF file
            
        Returns:
            List of tables, each table is a list of rows
        """
        all_tables = []
        
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                if tables:
                    all_tables.extend(tables)
        
        return all_tables
    
    def extract_tables_with_settings(self, file_path: str, 
                                     table_settings: Optional[Dict] = None) -> List[List[List[str]]]:
        """Extract tables with custom settings."""
        all_tables = []
        
        default_settings = {
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "intersection_y_tolerance": 5,
            "intersection_x_tolerance": 5,
        }
        
        settings = table_settings or default_settings
        
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables(table_settings=settings)
                if tables:
                    all_tables.extend(tables)
        
        return all_tables
    
    def find_invoice_table(self, tables: List[List[List[str]]]) -> Optional[List[List[str]]]:
        """Find the most likely invoice table from extracted tables."""
        if not tables:
            return None
        
        best_table = None
        best_score = 0
        
        for table in tables:
            score = 0
            
            # Check for money amounts
            for row in table:
                for cell in row:
                    if cell and re.search(r'[£$€]\s*[\d,.]+', str(cell)):
                        score += 1
            
            # Check for description-like content
            for row in table:
                for cell in row:
                    if cell and len(str(cell)) > 20:
                        score += 0.5
            
            # Check for quantity/price columns
            header_row = table[0] if table else []
            header_text = ' '.join(str(c) for c in header_row if c).lower()
            
            invoice_keywords = ['description', 'qty', 'quantity', 'price', 'amount', 'total', 'item']
            for keyword in invoice_keywords:
                if keyword in header_text:
                    score += 2
            
            if score > best_score:
                best_score = score
                best_table = table
        
        return best_table


class PDFImageExtractor:
    """Extract images from PDF and OCR them."""
    
    def __init__(self):
        if not PDF2IMAGE_AVAILABLE:
            raise RuntimeError("pdf2image is required for image extraction")
        
        # Import OCR extractor
        try:
            from .image_extractor import ImageOCRExtractor
            self.ocr = ImageOCRExtractor()
            self.ocr_available = True
        except Exception as e:
            logger.warning(f"OCR not available: {e}")
            self.ocr_available = False
    
    def extract_text_from_images(self, file_path: str, dpi: int = 300) -> str:
        """
        Convert PDF pages to images and OCR them.
        
        Args:
            file_path: Path to PDF file
            dpi: DPI for image conversion
            
        Returns:
            Extracted text from all pages
        """
        if not self.ocr_available:
            raise RuntimeError("OCR not available")
        
        all_text = []
        
        try:
            images = convert_from_path(file_path, dpi=dpi)
            
            for i, image in enumerate(images):
                try:
                    text = self.ocr.extract_text_from_image(image, preprocess=True)
                    if text.strip():
                        all_text.append(f"--- Page {i+1} ---\n{text}")
                except Exception as e:
                    logger.warning(f"OCR failed for page {i+1}: {e}")
            
        except Exception as e:
            raise RuntimeError(f"PDF to image conversion failed: {e}")
        
        return '\n\n'.join(all_text)


class PDFInvoiceExtractor:
    """Main PDF invoice extractor with multiple strategies."""
    
    def __init__(self):
        self.text_extractor = PDFTextExtractor()
        self.table_extractor = PDFTableExtractor() if PDFPLUMBER_AVAILABLE else None
        self.image_extractor = None
        
        if PDF2IMAGE_AVAILABLE:
            try:
                self.image_extractor = PDFImageExtractor()
            except Exception as e:
                logger.warning(f"PDF image extractor not available: {e}")
    
    def extract(self, file_path: str, use_ocr_fallback: bool = True) -> ExtractionResult:
        """
        Extract invoice data from PDF with multiple fallback strategies.
        
        Args:
            file_path: Path to PDF file
            use_ocr_fallback: Whether to try OCR if text extraction fails
            
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
                    method='pdf_extraction',
                    error_message=f"File not found: {file_path}"
                )
            
            # Try 1: Direct text extraction
            try:
                text = self.text_extractor.extract_text(file_path)
                if text.strip():
                    invoice_data = self._parse_invoice_text(text)
                    invoice_data.raw_text = text[:5000]
                    
                    # Also try to extract tables
                    if self.table_extractor:
                        try:
                            tables = self.table_extractor.extract_tables(file_path)
                            invoice_table = self.table_extractor.find_invoice_table(tables)
                            if invoice_table:
                                self._merge_table_data(invoice_data, invoice_table)
                        except Exception as e:
                            logger.warning(f"Table extraction failed: {e}")
                    
                    processing_time = int((time.time() - start_time) * 1000)
                    
                    return ExtractionResult(
                        success=True,
                        method='pdf_text_extraction',
                        data=invoice_data,
                        confidence=invoice_data.extraction_confidence,
                        processing_time_ms=processing_time,
                        raw_text=text[:2000]
                    )
            except Exception as e:
                logger.warning(f"Direct text extraction failed: {e}")
            
            # Try 2: OCR fallback for scanned PDFs
            if use_ocr_fallback and self.image_extractor and self.image_extractor.ocr_available:
                try:
                    text = self.image_extractor.extract_text_from_images(file_path)
                    if text.strip():
                        invoice_data = self._parse_invoice_text(text)
                        invoice_data.raw_text = text[:5000]
                        
                        processing_time = int((time.time() - start_time) * 1000)
                        
                        return ExtractionResult(
                            success=True,
                            method='pdf_ocr_extraction',
                            data=invoice_data,
                            confidence=invoice_data.extraction_confidence,
                            processing_time_ms=processing_time,
                            raw_text=text[:2000]
                        )
                except Exception as e:
                    logger.warning(f"OCR extraction failed: {e}")
            
            # All methods failed
            return ExtractionResult(
                success=False,
                method='pdf_extraction',
                error_message="All extraction methods failed"
            )
            
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            processing_time = int((time.time() - start_time) * 1000)
            
            return ExtractionResult(
                success=False,
                method='pdf_extraction',
                error_message=str(e),
                processing_time_ms=processing_time
            )
    
    def _parse_invoice_text(self, text: str) -> InvoiceData:
        """Parse invoice data from extracted text."""
        invoice_data = InvoiceData(extraction_method='pdf_extraction')
        
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
        contractor_patterns = [
            r'(?:From|Contractor|Subcontractor|Supplier)[:\s]*\n?\s*([A-Z][A-Za-z0-9\s&.,]+(?:Ltd|Limited|LLP|Inc|Co|Company)?)',
            r'^([A-Z][A-Za-z\s&.,]+(?:Ltd|Limited|LLP|Inc|Co|Company)?)',
        ]
        
        for pattern in contractor_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                contractor.name = match.group(1).strip()
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
    
    def _merge_table_data(self, invoice_data: InvoiceData, table: List[List[str]]):
        """Merge data from extracted table into invoice data."""
        if not table or len(table) < 2:
            return
        
        # Try to identify columns
        headers = [str(h).lower().strip() if h else '' for h in table[0]]
        
        # Find column indices
        desc_idx = next((i for i, h in enumerate(headers) if 'desc' in h or 'item' in h), None)
        qty_idx = next((i for i, h in enumerate(headers) if 'qty' in h or 'quantity' in h), None)
        price_idx = next((i for i, h in enumerate(headers) if 'price' in h or 'rate' in h), None)
        amount_idx = next((i for i, h in enumerate(headers) if 'amount' in h or 'total' in h), None)
        plot_idx = next((i for i, h in enumerate(headers) if 'plot' in h or 'property' in h), None)
        
        # Process data rows
        for row in table[1:]:
            if not any(row):
                continue
            
            work_item = WorkItem()
            
            if plot_idx is not None and plot_idx < len(row):
                work_item.plot_number = str(row[plot_idx]).strip()
            
            if desc_idx is not None and desc_idx < len(row):
                work_item.description = str(row[desc_idx]).strip()
            
            if qty_idx is not None and qty_idx < len(row):
                try:
                    work_item.quantity = parse_money(str(row[qty_idx]))
                except:
                    pass
            
            if price_idx is not None and price_idx < len(row):
                try:
                    work_item.unit_price = parse_money(str(row[price_idx]))
                except:
                    pass
            
            if amount_idx is not None and amount_idx < len(row):
                try:
                    work_item.amount = parse_money(str(row[amount_idx]))
                except:
                    pass
            
            if any([work_item.description, work_item.plot_number, work_item.amount]):
                invoice_data.work_items.append(work_item)
    
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


def extract_from_pdf(file_path: str, use_ocr_fallback: bool = True) -> ExtractionResult:
    """Convenience function for PDF extraction."""
    extractor = PDFInvoiceExtractor()
    return extractor.extract(file_path, use_ocr_fallback)
