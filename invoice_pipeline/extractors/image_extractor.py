"""
Invoice Processing Pipeline - Image OCR Extractor
Handles OCR extraction from JPEG/PNG images using Tesseract.
"""

import os
import io
import logging
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract

from ..models import InvoiceData, ExtractionResult, Contractor, Address, BankDetails, Financials, WorkItem, WorkPeriod
from ..utils import (
    clean_text, InvoicePatterns, extract_pattern, parse_date_flexible,
    parse_money, extract_address, parse_date_range
)

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """Preprocess images to improve OCR accuracy."""
    
    @staticmethod
    def enhance_contrast(image: Image.Image, factor: float = 2.0) -> Image.Image:
        """Enhance image contrast."""
        enhancer = ImageEnhance.Contrast(image)
        return enhancer.enhance(factor)
    
    @staticmethod
    def enhance_sharpness(image: Image.Image, factor: float = 2.0) -> Image.Image:
        """Enhance image sharpness."""
        enhancer = ImageEnhance.Sharpness(image)
        return enhancer.enhance(factor)
    
    @staticmethod
    def convert_to_grayscale(image: Image.Image) -> Image.Image:
        """Convert image to grayscale."""
        return image.convert('L')
    
    @staticmethod
    def apply_threshold(image: Image.Image, threshold: int = 128) -> Image.Image:
        """Apply binary threshold to image."""
        return image.point(lambda x: 0 if x < threshold else 255, '1')
    
    @staticmethod
    def denoise(image: Image.Image) -> Image.Image:
        """Apply denoising filter."""
        return image.filter(ImageFilter.MedianFilter(size=3))
    
    @staticmethod
    def deskew(image: Image.Image) -> Image.Image:
        """Attempt to deskew the image."""
        # Convert to numpy array for processing
        img_array = np.array(image.convert('L'))
        
        # Detect skew angle using projection profile
        # This is a simplified version - more sophisticated methods exist
        try:
            from scipy import ndimage
            
            # Find edges
            edges = ndimage.sobel(img_array)
            
            # Calculate angle with maximum variance
            angles = range(-15, 16)
            best_angle = 0
            max_variance = 0
            
            for angle in angles:
                rotated = ndimage.rotate(edges, angle, reshape=False)
                variance = np.var(np.sum(rotated, axis=1))
                if variance > max_variance:
                    max_variance = variance
                    best_angle = angle
            
            if best_angle != 0:
                rotated = ndimage.rotate(img_array, best_angle, reshape=False, cval=255)
                return Image.fromarray(rotated)
        except ImportError:
            pass
        
        return image
    
    @staticmethod
    def resize_for_ocr(image: Image.Image, min_dpi: int = 300) -> Image.Image:
        """Resize image to optimal size for OCR."""
        # Calculate current DPI
        width, height = image.size
        
        # If image is too small, scale it up
        if width < 1000 or height < 1000:
            scale_factor = max(1000 / width, 1000 / height)
            new_size = (int(width * scale_factor), int(height * scale_factor))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        
        return image
    
    @classmethod
    def preprocess_pipeline(cls, image: Image.Image, aggressive: bool = False) -> List[Image.Image]:
        """Run full preprocessing pipeline and return multiple variants."""
        variants = []
        
        # Original
        variants.append(image.copy())
        
        # Grayscale
        gray = cls.convert_to_grayscale(image)
        variants.append(gray)
        
        # Enhanced contrast
        enhanced = cls.enhance_contrast(gray, factor=2.0)
        variants.append(enhanced)
        
        # Threshold
        threshold = cls.apply_threshold(enhanced, threshold=150)
        variants.append(threshold)
        
        if aggressive:
            # More aggressive processing
            denoised = cls.denoise(enhanced)
            variants.append(denoised)
            
            sharp = cls.enhance_sharpness(denoised, factor=2.5)
            variants.append(sharp)
        
        return variants


class ImageOCRExtractor:
    """Extract text from images using OCR."""
    
    def __init__(self, lang: str = 'eng', psm_mode: int = 6):
        """
        Initialize OCR extractor.
        
        Args:
            lang: Tesseract language code
            psm_mode: Page segmentation mode (6 = assume single uniform block of text)
        """
        self.lang = lang
        self.psm_mode = psm_mode
        self.preprocessor = ImagePreprocessor()
        
        # Verify Tesseract is available
        try:
            pytesseract.get_tesseract_version()
            self.tesseract_available = True
        except Exception as e:
            logger.warning(f"Tesseract not available: {e}")
            self.tesseract_available = False
    
    def extract_text(self, image_path: str, preprocess: bool = True) -> str:
        """
        Extract text from image file.
        
        Args:
            image_path: Path to image file
            preprocess: Whether to apply preprocessing
            
        Returns:
            Extracted text
        """
        if not self.tesseract_available:
            raise RuntimeError("Tesseract OCR is not available")
        
        # Load image
        image = Image.open(image_path)
        
        return self.extract_text_from_image(image, preprocess)
    
    def extract_text_from_image(self, image: Image.Image, preprocess: bool = True) -> str:
        """
        Extract text from PIL Image object.
        
        Args:
            image: PIL Image object
            preprocess: Whether to apply preprocessing
            
        Returns:
            Extracted text
        """
        if not self.tesseract_available:
            raise RuntimeError("Tesseract OCR is not available")
        
        all_text = []
        
        if preprocess:
            # Try multiple preprocessing variants
            variants = self.preprocessor.preprocess_pipeline(image, aggressive=True)
            
            for variant in variants:
                text = self._ocr_image(variant)
                if text.strip():
                    all_text.append(text)
        else:
            text = self._ocr_image(image)
            all_text.append(text)
        
        # Combine and deduplicate text
        combined_text = self._merge_ocr_results(all_text)
        
        return clean_text(combined_text)
    
    def _ocr_image(self, image: Image.Image) -> str:
        """Run OCR on a single image."""
        custom_config = f'--psm {self.psm_mode} --oem 3'
        
        try:
            text = pytesseract.image_to_string(
                image,
                lang=self.lang,
                config=custom_config
            )
            return text
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return ""
    
    def _merge_ocr_results(self, texts: List[str]) -> str:
        """Merge multiple OCR results, keeping unique content."""
        if not texts:
            return ""
        
        if len(texts) == 1:
            return texts[0]
        
        # Start with the longest result (usually most complete)
        texts.sort(key=len, reverse=True)
        merged_lines = set()
        
        for text in texts:
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if line and len(line) > 3:
                    merged_lines.add(line)
        
        return '\n'.join(sorted(merged_lines, key=len, reverse=True))
    
    def extract_with_data(self, image_path: str) -> Dict[str, Any]:
        """
        Extract text with structured data from image.
        
        Args:
            image_path: Path to image file
            
        Returns:
            Dictionary with extracted text and metadata
        """
        if not self.tesseract_available:
            raise RuntimeError("Tesseract OCR is not available")
        
        image = Image.open(image_path)
        
        # Get detailed OCR data
        custom_config = f'--psm {self.psm_mode} --oem 3'
        data = pytesseract.image_to_data(
            image,
            lang=self.lang,
            config=custom_config,
            output_type=pytesseract.Output.DICT
        )
        
        # Extract text with confidence scores
        text_parts = []
        confidences = []
        
        for i, text in enumerate(data['text']):
            if text.strip():
                conf = int(data['conf'][i])
                if conf > 30:  # Filter low confidence
                    text_parts.append(text)
                    confidences.append(conf)
        
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        return {
            'text': ' '.join(text_parts),
            'confidence': avg_confidence,
            'word_count': len(text_parts),
            'raw_data': data
        }


class ImageInvoiceExtractor:
    """Extract invoice data from images."""
    
    def __init__(self):
        self.ocr = ImageOCRExtractor()
    
    def extract(self, file_path: str) -> ExtractionResult:
        """
        Extract invoice data from image file.
        
        Args:
            file_path: Path to image file
            
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
                    method='image_ocr',
                    error_message=f"File not found: {file_path}"
                )
            
            # Verify file is an image
            try:
                Image.open(file_path).verify()
            except Exception as e:
                return ExtractionResult(
                    success=False,
                    method='image_ocr',
                    error_message=f"Invalid image file: {e}"
                )
            
            # Extract text using OCR
            raw_text = self.ocr.extract_text(file_path, preprocess=True)
            
            if not raw_text.strip():
                return ExtractionResult(
                    success=False,
                    method='image_ocr',
                    error_message="No text extracted from image"
                )
            
            # Parse invoice data from text
            invoice_data = self._parse_invoice_text(raw_text)
            invoice_data.raw_text = raw_text[:5000]  # Store first 5000 chars
            
            processing_time = int((time.time() - start_time) * 1000)
            
            return ExtractionResult(
                success=True,
                method='image_ocr',
                data=invoice_data,
                confidence=invoice_data.extraction_confidence,
                processing_time_ms=processing_time,
                raw_text=raw_text[:2000]
            )
            
        except Exception as e:
            logger.error(f"Image extraction failed: {e}")
            processing_time = int((time.time() - start_time) * 1000)
            
            return ExtractionResult(
                success=False,
                method='image_ocr',
                error_message=str(e),
                processing_time_ms=processing_time
            )
    
    def _parse_invoice_text(self, text: str) -> InvoiceData:
        """Parse invoice data from extracted text."""
        from ..models import Contractor, Address, BankDetails, Financials, WorkItem, WorkPeriod
        
        invoice_data = InvoiceData(extraction_method='image_ocr')
        
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
            # Try to extract date range
            start, end = parse_date_range(text)
            if start or end:
                invoice_data.work_period = WorkPeriod(start_date=start, end_date=end)
        
        # Extract contractor information
        contractor = Contractor()
        
        # UTR
        utr = extract_pattern(text, InvoicePatterns.UTR)
        if utr:
            contractor.utr = utr
        
        # NI Number
        ni = extract_pattern(text, InvoicePatterns.NI_NUMBER)
        if ni:
            contractor.ni_number = ni
        
        # VAT Number
        vat = extract_pattern(text, InvoicePatterns.VAT_NUMBER)
        if vat:
            contractor.vat_number = vat
        
        # Company Number
        company = extract_pattern(text, InvoicePatterns.COMPANY_NUMBER)
        if company:
            contractor.company_number = company
        
        # Email
        email = extract_pattern(text, InvoicePatterns.EMAIL)
        if email:
            contractor.email = email.lower()
        
        # Phone
        phone = extract_pattern(text, InvoicePatterns.PHONE)
        if phone:
            contractor.phone = phone
        
        # Bank details
        bank = BankDetails()
        sort_code = extract_pattern(text, InvoicePatterns.SORT_CODE)
        if sort_code:
            bank.sort_code = sort_code
        
        account = extract_pattern(text, InvoicePatterns.ACCOUNT_NUMBER)
        if account:
            bank.account_number = account
        
        if sort_code or account:
            contractor.bank_details = bank
        
        # Address
        address_info = extract_address(text)
        if any(address_info.values()):
            contractor.address = Address(**address_info)
        
        # Try to find contractor name (look for patterns)
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
    
    def _extract_work_items(self, text: str) -> List[WorkItem]:
        """Extract work items from text."""
        work_items = []
        
        # Look for plot/property references
        plots = InvoicePatterns.PLOT_NUMBER.findall(text)
        
        for plot in plots:
            item = WorkItem(plot_number=plot)
            
            # Try to find associated description
            # Look for text near the plot number
            pattern = re.compile(
                rf'(?:Plot|Property)[:\s#]*{re.escape(plot)}.*?\n(.{{50,200}})',
                re.IGNORECASE | re.DOTALL
            )
            match = pattern.search(text)
            if match:
                item.description = match.group(1).strip()
            
            work_items.append(item)
        
        # If no plots found, look for operative names as indicators of work items
        if not work_items:
            operatives = InvoicePatterns.OPERATIVE.findall(text)
            for op in operatives:
                item = WorkItem(operative_names=[op])
                work_items.append(item)
        
        return work_items


def extract_from_image(file_path: str) -> ExtractionResult:
    """Convenience function for image extraction."""
    extractor = ImageInvoiceExtractor()
    return extractor.extract(file_path)
