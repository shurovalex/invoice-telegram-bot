"""
Invoice Processing Pipeline
===========================

A robust, multi-strategy document processing pipeline for extracting invoice data
from various file formats including images, PDFs, Word documents, and text files.

Features:
- Multi-format support (JPEG, PNG, PDF, DOCX, TXT)
- OCR for images and scanned documents
- Automatic file type detection
- Fallback extraction strategies
- Data validation and cleaning
- Structured output with confidence scores

Quick Start:
    from invoice_pipeline import process_invoice, PipelineConfig
    
    # Process a single file
    result = process_invoice('path/to/invoice.pdf')
    
    if result.success:
        print(result.invoice_data.invoice_number)
        print(result.invoice_data.financials.total_due)
    
    # Process with custom configuration
    config = PipelineConfig(
        use_ocr_for_scanned_pdfs=True,
        min_confidence_threshold=0.5
    )
    result = process_invoice('path/to/invoice.jpg', config=config)

Batch Processing:
    from invoice_pipeline import process_invoices
    
    files = ['invoice1.pdf', 'invoice2.jpg', 'invoice3.docx']
    results = process_invoices(files)
    
    for result in results:
        print(f"{result.source_file}: {'Success' if result.success else 'Failed'}")
"""

from .models import (
    InvoiceData, Contractor, Address, BankDetails, 
    Financials, WorkItem, WorkPeriod,
    ExtractionResult, PipelineResult
)
from .pipeline import (
    InvoiceProcessingPipeline, PipelineConfig,
    process_invoice, process_invoices
)
from .validators import (
    DataValidator, DataCleaner, DataEnricher,
    validate_and_clean
)
from .utils import (
    InvoicePatterns, clean_text, parse_date_flexible,
    parse_money, extract_address
)

__version__ = '1.0.0'
__all__ = [
    # Models
    'InvoiceData',
    'Contractor',
    'Address',
    'BankDetails',
    'Financials',
    'WorkItem',
    'WorkPeriod',
    'ExtractionResult',
    'PipelineResult',
    
    # Pipeline
    'InvoiceProcessingPipeline',
    'PipelineConfig',
    'process_invoice',
    'process_invoices',
    
    # Validation
    'DataValidator',
    'DataCleaner',
    'DataEnricher',
    'validate_and_clean',
    
    # Utilities
    'InvoicePatterns',
    'clean_text',
    'parse_date_flexible',
    'parse_money',
    'extract_address',
]
