"""
Invoice Processing Pipeline - Main Orchestrator
Coordinates multi-strategy extraction with fallback mechanisms.
"""

import os
import logging
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
import time

from .models import InvoiceData, ExtractionResult, PipelineResult
from .utils import clean_text, calculate_extraction_confidence

# Import extractors
from .extractors.image_extractor import ImageInvoiceExtractor
from .extractors.pdf_extractor import PDFInvoiceExtractor
from .extractors.docx_extractor import DOCXInvoiceExtractor
from .extractors.text_extractor import TextFileExtractor

logger = logging.getLogger(__name__)


class FileType(Enum):
    """Supported file types."""
    PDF = 'pdf'
    IMAGE = 'image'
    DOCX = 'docx'
    TEXT = 'text'
    UNKNOWN = 'unknown'


@dataclass
class PipelineConfig:
    """Configuration for the processing pipeline."""
    # Extraction settings
    use_ocr_for_scanned_pdfs: bool = True
    try_multiple_strategies: bool = True
    min_confidence_threshold: float = 0.3
    
    # OCR settings
    ocr_language: str = 'eng'
    ocr_dpi: int = 300
    
    # Validation settings
    validate_output: bool = True
    require_invoice_number: bool = False
    require_contractor_name: bool = False
    
    # Error handling
    max_retries: int = 2
    continue_on_error: bool = True
    
    # Logging
    log_level: str = 'INFO'
    log_extraction_details: bool = True


class FileTypeDetector:
    """Detect file type from extension and content."""
    
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp'}
    PDF_EXTENSIONS = {'.pdf'}
    DOCX_EXTENSIONS = {'.docx', '.doc'}
    TEXT_EXTENSIONS = {'.txt', '.csv', '.tsv', '.json', '.xml', '.md', '.rtf'}
    
    @classmethod
    def from_extension(cls, file_path: str) -> FileType:
        """Detect file type from extension."""
        ext = Path(file_path).suffix.lower()
        
        if ext in cls.IMAGE_EXTENSIONS:
            return FileType.IMAGE
        elif ext in cls.PDF_EXTENSIONS:
            return FileType.PDF
        elif ext in cls.DOCX_EXTENSIONS:
            return FileType.DOCX
        elif ext in cls.TEXT_EXTENSIONS:
            return FileType.TEXT
        else:
            return FileType.UNKNOWN
    
    @classmethod
    def from_content(cls, file_path: str) -> FileType:
        """Detect file type from file content (magic numbers)."""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(8)
            
            # PDF signature
            if header.startswith(b'%PDF'):
                return FileType.PDF
            
            # Image signatures
            if header.startswith(b'\xff\xd8\xff'):  # JPEG
                return FileType.IMAGE
            if header.startswith(b'\x89PNG'):  # PNG
                return FileType.IMAGE
            if header.startswith(b'GIF87a') or header.startswith(b'GIF89a'):  # GIF
                return FileType.IMAGE
            if header.startswith(b'BM'):  # BMP
                return FileType.IMAGE
            
            # ZIP signature (DOCX is a ZIP file)
            if header.startswith(b'PK\x03\x04'):
                # Check if it's a DOCX by looking for word/document.xml
                try:
                    import zipfile
                    with zipfile.ZipFile(file_path, 'r') as z:
                        if 'word/document.xml' in z.namelist():
                            return FileType.DOCX
                except:
                    pass
            
            # Try to detect as text
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read(1024)
                    # If we can read it as text and it contains printable characters
                    if all(ord(c) < 128 and (c.isprintable() or c in '\n\r\t') for c in content):
                        return FileType.TEXT
            except:
                pass
            
        except Exception as e:
            logger.warning(f"Content detection failed: {e}")
        
        return FileType.UNKNOWN
    
    @classmethod
    def detect(cls, file_path: str) -> FileType:
        """Detect file type using both extension and content."""
        # First try extension
        ext_type = cls.from_extension(file_path)
        if ext_type != FileType.UNKNOWN:
            return ext_type
        
        # Fall back to content detection
        return cls.from_content(file_path)


class InvoiceProcessingPipeline:
    """
    Main invoice processing pipeline with multi-strategy extraction.
    
    This pipeline provides:
    - Automatic file type detection
    - Multiple extraction strategies per file type
    - Fallback mechanisms when primary methods fail
    - Data validation and cleaning
    - Comprehensive error handling
    """
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        """
        Initialize the pipeline.
        
        Args:
            config: Pipeline configuration
        """
        self.config = config or PipelineConfig()
        
        # Initialize extractors
        self._extractors = {}
        self._init_extractors()
        
        # Setup logging
        logging.basicConfig(level=getattr(logging, self.config.log_level))
    
    def _init_extractors(self):
        """Initialize all extractors."""
        # Image extractor
        try:
            self._extractors['image'] = ImageInvoiceExtractor()
            logger.info("Image extractor initialized")
        except Exception as e:
            logger.warning(f"Image extractor not available: {e}")
            self._extractors['image'] = None
        
        # PDF extractor
        try:
            self._extractors['pdf'] = PDFInvoiceExtractor()
            logger.info("PDF extractor initialized")
        except Exception as e:
            logger.warning(f"PDF extractor not available: {e}")
            self._extractors['pdf'] = None
        
        # DOCX extractor
        try:
            self._extractors['docx'] = DOCXInvoiceExtractor()
            logger.info("DOCX extractor initialized")
        except Exception as e:
            logger.warning(f"DOCX extractor not available: {e}")
            self._extractors['docx'] = None
        
        # Text extractor
        try:
            self._extractors['text'] = TextFileExtractor()
            logger.info("Text extractor initialized")
        except Exception as e:
            logger.warning(f"Text extractor not available: {e}")
            self._extractors['text'] = None
    
    def process(self, file_path: str, config: Optional[PipelineConfig] = None) -> PipelineResult:
        """
        Process a file and extract invoice data.
        
        Args:
            file_path: Path to the file to process
            config: Optional override configuration
            
        Returns:
            PipelineResult with extracted data
        """
        pipeline_config = config or self.config
        start_time = time.time()
        
        # Detect file type
        file_type = FileTypeDetector.detect(file_path)
        
        if file_type == FileType.UNKNOWN:
            return PipelineResult(
                success=False,
                source_file=file_path,
                file_type='unknown',
                errors=["Could not determine file type"]
            )
        
        logger.info(f"Processing {file_path} (type: {file_type.value})")
        
        # Route to appropriate handler
        if file_type == FileType.IMAGE:
            return self._process_image(file_path, pipeline_config, start_time)
        elif file_type == FileType.PDF:
            return self._process_pdf(file_path, pipeline_config, start_time)
        elif file_type == FileType.DOCX:
            return self._process_docx(file_path, pipeline_config, start_time)
        elif file_type == FileType.TEXT:
            return self._process_text(file_path, pipeline_config, start_time)
        
        return PipelineResult(
            success=False,
            source_file=file_path,
            file_type=file_type.value,
            errors=["Unsupported file type"]
        )
    
    def _process_image(self, file_path: str, config: PipelineConfig, start_time: float) -> PipelineResult:
        """Process image file with multiple strategies."""
        attempts = []
        
        if self._extractors['image']:
            # Try primary OCR extraction
            result = self._extractors['image'].extract(file_path)
            attempts.append(result)
            
            if result.success and result.confidence >= config.min_confidence_threshold:
                return self._build_success_result(file_path, 'image', attempts, result, start_time)
        
        return self._build_result(file_path, 'image', attempts, start_time)
    
    def _process_pdf(self, file_path: str, config: PipelineConfig, start_time: float) -> PipelineResult:
        """Process PDF file with multiple strategies."""
        attempts = []
        
        if self._extractors['pdf']:
            # Try primary extraction (text + tables)
            result = self._extractors['pdf'].extract(file_path, use_ocr_fallback=False)
            attempts.append(result)
            
            if result.success and result.confidence >= config.min_confidence_threshold:
                return self._build_success_result(file_path, 'pdf', attempts, result, start_time)
            
            # Try with OCR fallback for scanned PDFs
            if config.use_ocr_for_scanned_pdfs:
                result_ocr = self._extractors['pdf'].extract(file_path, use_ocr_fallback=True)
                attempts.append(result_ocr)
                
                if result_ocr.success and result_ocr.confidence >= config.min_confidence_threshold:
                    return self._build_success_result(file_path, 'pdf', attempts, result_ocr, start_time)
        
        return self._build_result(file_path, 'pdf', attempts, start_time)
    
    def _process_docx(self, file_path: str, config: PipelineConfig, start_time: float) -> PipelineResult:
        """Process DOCX file."""
        attempts = []
        
        if self._extractors['docx']:
            result = self._extractors['docx'].extract(file_path)
            attempts.append(result)
            
            if result.success and result.confidence >= config.min_confidence_threshold:
                return self._build_success_result(file_path, 'docx', attempts, result, start_time)
        
        return self._build_result(file_path, 'docx', attempts, start_time)
    
    def _process_text(self, file_path: str, config: PipelineConfig, start_time: float) -> PipelineResult:
        """Process text file."""
        attempts = []
        
        if self._extractors['text']:
            result = self._extractors['text'].extract(file_path)
            attempts.append(result)
            
            if result.success and result.confidence >= config.min_confidence_threshold:
                return self._build_success_result(file_path, 'text', attempts, result, start_time)
        
        return self._build_result(file_path, 'text', attempts, start_time)
    
    def _build_success_result(self, file_path: str, file_type: str, 
                             attempts: List[ExtractionResult], 
                             best_result: ExtractionResult, 
                             start_time: float) -> PipelineResult:
        """Build successful pipeline result."""
        total_time = int((time.time() - start_time) * 1000)
        
        return PipelineResult(
            success=True,
            source_file=file_path,
            file_type=file_type,
            invoice_data=best_result.data,
            all_attempts=attempts,
            best_method=best_result.method,
            total_processing_time_ms=total_time
        )
    
    def _build_result(self, file_path: str, file_type: str, 
                     attempts: List[ExtractionResult], 
                     start_time: float) -> PipelineResult:
        """Build pipeline result from all attempts."""
        total_time = int((time.time() - start_time) * 1000)
        
        # Find best attempt
        best_attempt = None
        best_confidence = 0
        
        for attempt in attempts:
            if attempt.success and attempt.confidence > best_confidence:
                best_confidence = attempt.confidence
                best_attempt = attempt
        
        if best_attempt:
            return PipelineResult(
                success=True,
                source_file=file_path,
                file_type=file_type,
                invoice_data=best_attempt.data,
                all_attempts=attempts,
                best_method=best_attempt.method,
                total_processing_time_ms=total_time,
                warnings=["Low confidence extraction"]
            )
        
        # All attempts failed
        errors = [a.error_message for a in attempts if a.error_message]
        
        return PipelineResult(
            success=False,
            source_file=file_path,
            file_type=file_type,
            all_attempts=attempts,
            total_processing_time_ms=total_time,
            errors=errors if errors else ["All extraction methods failed"]
        )
    
    def batch_process(self, file_paths: List[str], 
                     config: Optional[PipelineConfig] = None) -> List[PipelineResult]:
        """
        Process multiple files.
        
        Args:
            file_paths: List of file paths to process
            config: Optional configuration override
            
        Returns:
            List of PipelineResult objects
        """
        results = []
        
        for file_path in file_paths:
            try:
                result = self.process(file_path, config)
                results.append(result)
            except Exception as e:
                logger.error(f"Batch processing failed for {file_path}: {e}")
                results.append(PipelineResult(
                    success=False,
                    source_file=file_path,
                    file_type='unknown',
                    errors=[str(e)]
                ))
        
        return results
    
    def get_statistics(self, results: List[PipelineResult]) -> Dict[str, Any]:
        """Get statistics from batch processing results."""
        total = len(results)
        successful = sum(1 for r in results if r.success)
        failed = total - successful
        
        by_type = {}
        for r in results:
            ft = r.file_type
            if ft not in by_type:
                by_type[ft] = {'total': 0, 'success': 0}
            by_type[ft]['total'] += 1
            if r.success:
                by_type[ft]['success'] += 1
        
        avg_confidence = 0
        confidences = [r.invoice_data.extraction_confidence for r in results if r.success and r.invoice_data]
        if confidences:
            avg_confidence = sum(confidences) / len(confidences)
        
        total_time = sum(r.total_processing_time_ms or 0 for r in results)
        
        return {
            'total_files': total,
            'successful': successful,
            'failed': failed,
            'success_rate': successful / total if total > 0 else 0,
            'by_file_type': by_type,
            'average_confidence': avg_confidence,
            'total_processing_time_ms': total_time,
            'average_processing_time_ms': total_time / total if total > 0 else 0
        }


# Convenience functions
def process_invoice(file_path: str, config: Optional[PipelineConfig] = None) -> PipelineResult:
    """
    Process a single invoice file.
    
    Args:
        file_path: Path to the invoice file
        config: Optional configuration
        
    Returns:
        PipelineResult with extracted data
    """
    pipeline = InvoiceProcessingPipeline(config)
    return pipeline.process(file_path)


def process_invoices(file_paths: List[str], config: Optional[PipelineConfig] = None) -> List[PipelineResult]:
    """
    Process multiple invoice files.
    
    Args:
        file_paths: List of file paths
        config: Optional configuration
        
    Returns:
        List of PipelineResult objects
    """
    pipeline = InvoiceProcessingPipeline(config)
    return pipeline.batch_process(file_paths, config)
