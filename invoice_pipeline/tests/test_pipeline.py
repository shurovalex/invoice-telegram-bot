"""
Invoice Processing Pipeline - Tests and Examples
Demonstrates usage of the pipeline with various scenarios.
"""

import os
import sys
import tempfile
from decimal import Decimal
from datetime import date

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from invoice_pipeline import (
    process_invoice, process_invoices, PipelineConfig,
    InvoiceData, Contractor, Address, BankDetails, Financials, WorkItem, WorkPeriod,
    DataValidator, DataCleaner, validate_and_clean
)


def create_sample_text_invoice():
    """Create a sample text invoice for testing."""
    invoice_text = """
    ABC CONSTRUCTION LTD
    123 Builder Street
    London, EC1A 1BB
    
    INVOICE
    Invoice Number: INV-2024-001
    Invoice Date: 15/01/2024
    
    Contractor Details:
    Name: John Smith
    UTR: 1234567890
    NI Number: AB123456C
    Email: john.smith@example.com
    Phone: 07700 900123
    
    Bank Details:
    Sort Code: 12-34-56
    Account Number: 12345678
    
    Work Period: 01/01/2024 to 14/01/2024
    
    Work Items:
    Plot 15 - Foundation work - £2,500.00
    Plot 16 - Bricklaying - £3,200.00
    Plot 17 - Roofing - £1,800.00
    
    Operatives: Mike Johnson, Dave Williams
    
    Subtotal: £7,500.00
    VAT @ 20%: £1,500.00
    CIS Deduction: £1,500.00
    Total Due: £7,500.00
    """
    return invoice_text


def test_text_extraction():
    """Test text file extraction."""
    print("=" * 60)
    print("TEST: Text File Extraction")
    print("=" * 60)
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(create_sample_text_invoice())
        temp_path = f.name
    
    try:
        # Process the file
        result = process_invoice(temp_path)
        
        print(f"Success: {result.success}")
        print(f"File Type: {result.file_type}")
        print(f"Best Method: {result.best_method}")
        print(f"Processing Time: {result.total_processing_time_ms}ms")
        
        if result.success and result.invoice_data:
            data = result.invoice_data
            print(f"\n--- Extracted Data ---")
            print(f"Invoice Number: {data.invoice_number}")
            print(f"Invoice Date: {data.invoice_date}")
            
            if data.contractor:
                print(f"Contractor Name: {data.contractor.name}")
                print(f"Contractor UTR: {data.contractor.utr}")
                print(f"Contractor NI: {data.contractor.ni_number}")
                print(f"Contractor Email: {data.contractor.email}")
            
            if data.work_period:
                print(f"Work Period: {data.work_period.start_date} to {data.work_period.end_date}")
            
            print(f"Work Items: {len(data.work_items)}")
            for item in data.work_items:
                print(f"  - Plot {item.plot_number}: {item.description}")
            
            if data.financials:
                print(f"Subtotal: £{data.financials.subtotal}")
                print(f"VAT: £{data.financials.vat_amount}")
                print(f"CIS Deduction: £{data.financials.cis_deduction}")
                print(f"Total Due: £{data.financials.total_due}")
            
            print(f"\nConfidence Score: {data.extraction_confidence:.2%}")
        
        if result.errors:
            print(f"\nErrors: {result.errors}")
        
        return result
        
    finally:
        os.unlink(temp_path)


def test_validation():
    """Test data validation."""
    print("\n" + "=" * 60)
    print("TEST: Data Validation")
    print("=" * 60)
    
    # Create sample invoice data
    invoice = InvoiceData(
        invoice_number="INV-001",
        invoice_date=date(2024, 1, 15),
        contractor=Contractor(
            name="Test Contractor Ltd",
            utr="1234567890",
            ni_number="AB123456C",
            email="test@example.com",
            address=Address(
                street="123 Test Street",
                city="London",
                postcode="EC1A 1BB"
            ),
            bank_details=BankDetails(
                sort_code="12-34-56",
                account_number="12345678"
            )
        ),
        work_period=WorkPeriod(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 14)
        ),
        work_items=[
            WorkItem(
                plot_number="15",
                description="Foundation work",
                amount=Decimal("2500.00")
            ),
            WorkItem(
                plot_number="16",
                description="Bricklaying",
                amount=Decimal("3200.00")
            )
        ],
        financials=Financials(
            subtotal=Decimal("7500.00"),
            vat_amount=Decimal("1500.00"),
            vat_rate=Decimal("20.00"),
            cis_deduction=Decimal("1500.00"),
            total_due=Decimal("7500.00")
        )
    )
    
    # Validate and clean
    cleaned_invoice, errors, warnings = validate_and_clean(invoice)
    
    print(f"Validation Errors: {errors}")
    print(f"Validation Warnings: {warnings}")
    
    # Test individual validators
    print("\n--- Individual Validations ---")
    
    # Valid UTR
    valid, errs = DataValidator.validate_utr("1234567890")
    print(f"Valid UTR '1234567890': {valid}, Errors: {errs}")
    
    # Invalid UTR
    valid, errs = DataValidator.validate_utr("12345")
    print(f"Invalid UTR '12345': {valid}, Errors: {errs}")
    
    # Valid NI
    valid, errs = DataValidator.validate_ni_number("AB123456C")
    print(f"Valid NI 'AB123456C': {valid}, Errors: {errs}")
    
    # Invalid NI
    valid, errs = DataValidator.validate_ni_number("INVALID")
    print(f"Invalid NI 'INVALID': {valid}, Errors: {errs}")
    
    # Valid email
    valid, errs = DataValidator.validate_email("test@example.com")
    print(f"Valid Email 'test@example.com': {valid}, Errors: {errs}")
    
    # Invalid email
    valid, errs = DataValidator.validate_email("not-an-email")
    print(f"Invalid Email 'not-an-email': {valid}, Errors: {errs}")


def test_data_cleaning():
    """Test data cleaning functions."""
    print("\n" + "=" * 60)
    print("TEST: Data Cleaning")
    print("=" * 60)
    
    cleaner = DataCleaner()
    
    # Test invoice number cleaning
    print("\n--- Invoice Number Cleaning ---")
    test_cases = [
        "Invoice # INV-001",
        "Inv: ABC123",
        "No: 12345",
        "  INV-2024-001  "
    ]
    for test in test_cases:
        cleaned = cleaner.clean_invoice_number(test)
        print(f"'{test}' -> '{cleaned}'")
    
    # Test postcode cleaning
    print("\n--- Postcode Cleaning ---")
    postcodes = ["ec1a1bb", "EC1A 1BB", "EC1A1BB", "  ec1a 1bb  "]
    for pc in postcodes:
        cleaned = cleaner.clean_postcode(pc)
        print(f"'{pc}' -> '{cleaned}'")
    
    # Test sort code cleaning
    print("\n--- Sort Code Cleaning ---")
    sort_codes = ["123456", "12-34-56", "12 34 56"]
    for sc in sort_codes:
        cleaned = cleaner.clean_sort_code(sc)
        print(f"'{sc}' -> '{cleaned}'")
    
    # Test email cleaning
    print("\n--- Email Cleaning ---")
    emails = ["  Test@Example.COM  ", "mailto:test@example.com"]
    for email in emails:
        cleaned = cleaner.clean_email(email)
        print(f"'{email}' -> '{cleaned}'")


def test_pipeline_config():
    """Test pipeline with different configurations."""
    print("\n" + "=" * 60)
    print("TEST: Pipeline Configuration")
    print("=" * 60)
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(create_sample_text_invoice())
        temp_path = f.name
    
    try:
        # Test with default config
        print("\n--- Default Config ---")
        result = process_invoice(temp_path)
        print(f"Success: {result.success}, Confidence: {result.invoice_data.extraction_confidence if result.invoice_data else 0:.2%}")
        
        # Test with custom config
        print("\n--- Custom Config (High Confidence Threshold) ---")
        config = PipelineConfig(min_confidence_threshold=0.8)
        result = process_invoice(temp_path, config=config)
        print(f"Success: {result.success}, Confidence: {result.invoice_data.extraction_confidence if result.invoice_data else 0:.2%}")
        
        # Test with OCR disabled for PDFs
        print("\n--- Config (OCR Disabled) ---")
        config = PipelineConfig(use_ocr_for_scanned_pdfs=False)
        result = process_invoice(temp_path, config=config)
        print(f"Success: {result.success}")
        
    finally:
        os.unlink(temp_path)


def test_batch_processing():
    """Test batch processing."""
    print("\n" + "=" * 60)
    print("TEST: Batch Processing")
    print("=" * 60)
    
    # Create multiple temporary files
    temp_files = []
    for i in range(3):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            invoice_text = create_sample_text_invoice().replace("INV-2024-001", f"INV-2024-{i+1:03d}")
            f.write(invoice_text)
            temp_files.append(f.name)
    
    try:
        # Process all files
        results = process_invoices(temp_files)
        
        print(f"Processed {len(results)} files")
        
        for i, result in enumerate(results):
            print(f"\nFile {i+1}: {os.path.basename(result.source_file)}")
            print(f"  Success: {result.success}")
            if result.success and result.invoice_data:
                print(f"  Invoice #: {result.invoice_data.invoice_number}")
                print(f"  Confidence: {result.invoice_data.extraction_confidence:.2%}")
        
        # Get statistics
        from invoice_pipeline.pipeline import InvoiceProcessingPipeline
        pipeline = InvoiceProcessingPipeline()
        stats = pipeline.get_statistics(results)
        
        print(f"\n--- Batch Statistics ---")
        print(f"Total Files: {stats['total_files']}")
        print(f"Successful: {stats['successful']}")
        print(f"Failed: {stats['failed']}")
        print(f"Success Rate: {stats['success_rate']:.1%}")
        print(f"Average Confidence: {stats['average_confidence']:.2%}")
        print(f"Total Processing Time: {stats['total_processing_time_ms']}ms")
        
    finally:
        for temp_path in temp_files:
            os.unlink(temp_path)


def test_file_type_detection():
    """Test file type detection."""
    print("\n" + "=" * 60)
    print("TEST: File Type Detection")
    print("=" * 60)
    
    from invoice_pipeline.pipeline import FileTypeDetector, FileType
    
    test_files = [
        ("invoice.pdf", FileType.PDF),
        ("invoice.jpg", FileType.IMAGE),
        ("invoice.jpeg", FileType.IMAGE),
        ("invoice.png", FileType.IMAGE),
        ("invoice.docx", FileType.DOCX),
        ("invoice.txt", FileType.TEXT),
        ("invoice.unknown", FileType.UNKNOWN),
    ]
    
    print("\n--- Extension-based Detection ---")
    for filename, expected in test_files:
        detected = FileTypeDetector.from_extension(filename)
        status = "✓" if detected == expected else "✗"
        print(f"{status} {filename}: {detected.value}")


def demonstrate_complete_workflow():
    """Demonstrate a complete invoice processing workflow."""
    print("\n" + "=" * 60)
    print("DEMO: Complete Invoice Processing Workflow")
    print("=" * 60)
    
    # Create sample invoice
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(create_sample_text_invoice())
        temp_path = f.name
    
    try:
        print("\nStep 1: Process the invoice file")
        print("-" * 40)
        result = process_invoice(temp_path)
        
        if not result.success:
            print(f"Processing failed: {result.errors}")
            return
        
        print(f"✓ File processed successfully")
        print(f"  Method used: {result.best_method}")
        print(f"  Processing time: {result.total_processing_time_ms}ms")
        
        print("\nStep 2: Validate and clean the extracted data")
        print("-" * 40)
        invoice_data = result.invoice_data
        cleaned_invoice, errors, warnings = validate_and_clean(invoice_data)
        
        if errors:
            print(f"⚠ Validation errors: {errors}")
        if warnings:
            print(f"⚠ Validation warnings: {warnings}")
        if not errors and not warnings:
            print("✓ Data validation passed")
        
        print("\nStep 3: Access extracted information")
        print("-" * 40)
        
        # Contractor info
        if cleaned_invoice.contractor:
            c = cleaned_invoice.contractor
            print(f"Contractor: {c.name}")
            print(f"  UTR: {c.utr}")
            print(f"  NI: {c.ni_number}")
            print(f"  Email: {c.email}")
            if c.bank_details:
                print(f"  Bank: Sort {c.bank_details.sort_code}, Acc {c.bank_details.account_number}")
        
        # Invoice details
        print(f"\nInvoice: {cleaned_invoice.invoice_number}")
        print(f"  Date: {cleaned_invoice.invoice_date}")
        
        # Work period
        if cleaned_invoice.work_period:
            print(f"  Period: {cleaned_invoice.work_period.start_date} to {cleaned_invoice.work_period.end_date}")
        
        # Work items
        print(f"\nWork Items ({len(cleaned_invoice.work_items)}):")
        for i, item in enumerate(cleaned_invoice.work_items, 1):
            print(f"  {i}. Plot {item.plot_number}: {item.description}")
            if item.amount:
                print(f"     Amount: £{item.amount}")
        
        # Financials
        if cleaned_invoice.financials:
            f = cleaned_invoice.financials
            print(f"\nFinancials:")
            print(f"  Subtotal: £{f.subtotal}")
            print(f"  VAT ({f.vat_rate}%): £{f.vat_amount}")
            print(f"  CIS Deduction: £{f.cis_deduction}")
            print(f"  Total Due: £{f.total_due}")
        
        print("\nStep 4: Export data")
        print("-" * 40)
        
        # Convert to dictionary
        data_dict = cleaned_invoice.to_dict()
        print("✓ Data exported to dictionary format")
        print(f"  Keys: {list(data_dict.keys())}")
        
        # Check completeness
        completeness = cleaned_invoice.completeness_score()
        print(f"\nData Completeness: {completeness:.1%}")
        
    finally:
        os.unlink(temp_path)


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("INVOICE PROCESSING PIPELINE - TEST SUITE")
    print("=" * 60)
    
    tests = [
        ("File Type Detection", test_file_type_detection),
        ("Text Extraction", test_text_extraction),
        ("Data Validation", test_validation),
        ("Data Cleaning", test_data_cleaning),
        ("Pipeline Configuration", test_pipeline_config),
        ("Batch Processing", test_batch_processing),
        ("Complete Workflow", demonstrate_complete_workflow),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            test_func()
            results.append((name, "PASSED", None))
            print(f"\n✓ {name}: PASSED")
        except Exception as e:
            results.append((name, "FAILED", str(e)))
            print(f"\n✗ {name}: FAILED - {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, status, _ in results if status == "PASSED")
    failed = sum(1 for _, status, _ in results if status == "FAILED")
    
    for name, status, error in results:
        symbol = "✓" if status == "PASSED" else "✗"
        print(f"{symbol} {name}: {status}")
        if error:
            print(f"  Error: {error}")
    
    print(f"\nTotal: {len(results)} tests, {passed} passed, {failed} failed")


if __name__ == '__main__':
    run_all_tests()
