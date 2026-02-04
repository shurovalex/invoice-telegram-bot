"""
Invoice Processing Pipeline - Data Validation and Cleaning
Provides validation and cleaning functions for extracted invoice data.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import date, timedelta
from decimal import Decimal

from .models import InvoiceData, Contractor, Financials, WorkItem, WorkPeriod

logger = logging.getLogger(__name__)


class DataValidator:
    """Validate extracted invoice data."""
    
    @staticmethod
    def validate_invoice_number(invoice_number: Optional[str]) -> Tuple[bool, List[str]]:
        """Validate invoice number format."""
        errors = []
        
        if not invoice_number:
            return True, []  # Optional field
        
        # Check length
        if len(invoice_number) < 3:
            errors.append("Invoice number seems too short")
        
        if len(invoice_number) > 50:
            errors.append("Invoice number seems too long")
        
        # Check for suspicious characters
        if re.search(r'[^A-Z0-9\-/]', invoice_number, re.IGNORECASE):
            errors.append("Invoice number contains unusual characters")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_date(invoice_date: Optional[date], 
                     field_name: str = "date") -> Tuple[bool, List[str]]:
        """Validate invoice date."""
        errors = []
        
        if not invoice_date:
            return True, []  # Optional field
        
        today = date.today()
        
        # Check if date is in the future
        if invoice_date > today:
            errors.append(f"{field_name} is in the future")
        
        # Check if date is too old (more than 5 years)
        if invoice_date < today - timedelta(days=365*5):
            errors.append(f"{field_name} is more than 5 years old")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_utr(utr: Optional[str]) -> Tuple[bool, List[str]]:
        """Validate UTR format."""
        errors = []
        
        if not utr:
            return True, []  # Optional field
        
        # Remove non-digits
        utr_clean = re.sub(r'\D', '', utr)
        
        if len(utr_clean) != 10:
            errors.append(f"UTR should be 10 digits, got {len(utr_clean)}")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_ni_number(ni: Optional[str]) -> Tuple[bool, List[str]]:
        """Validate National Insurance number format."""
        errors = []
        
        if not ni:
            return True, []  # Optional field
        
        ni_clean = ni.upper().replace(' ', '')
        
        # Check format: 2 letters, 6 digits, 1 letter
        if not re.match(r'^[A-Z]{2}\d{6}[A-Z]$', ni_clean):
            errors.append("NI number format is invalid (should be XX123456X)")
        
        # Check for invalid prefix letters
        invalid_prefixes = ['BG', 'GB', 'NK', 'KN', 'TN', 'NT', 'ZZ']
        if ni_clean[:2] in invalid_prefixes:
            errors.append(f"NI number has invalid prefix: {ni_clean[:2]}")
        
        # Check suffix (D, A, B, C, or E for current system)
        valid_suffixes = 'ABCEHDJMPRSTX'
        if ni_clean[-1] not in valid_suffixes:
            errors.append(f"NI number has invalid suffix: {ni_clean[-1]}")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_email(email: Optional[str]) -> Tuple[bool, List[str]]:
        """Validate email format."""
        errors = []
        
        if not email:
            return True, []  # Optional field
        
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            errors.append("Email format is invalid")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_postcode(postcode: Optional[str]) -> Tuple[bool, List[str]]:
        """Validate UK postcode format."""
        errors = []
        
        if not postcode:
            return True, []  # Optional field
        
        postcode_clean = postcode.upper().replace(' ', '')
        
        # UK postcode pattern
        pattern = r'^[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}$'
        if not re.match(pattern, postcode_clean):
            errors.append("Postcode format is invalid")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_sort_code(sort_code: Optional[str]) -> Tuple[bool, List[str]]:
        """Validate sort code format."""
        errors = []
        
        if not sort_code:
            return True, []  # Optional field
        
        sort_clean = re.sub(r'[^\d]', '', sort_code)
        
        if len(sort_clean) != 6:
            errors.append(f"Sort code should be 6 digits, got {len(sort_clean)}")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_account_number(account_number: Optional[str]) -> Tuple[bool, List[str]]:
        """Validate account number format."""
        errors = []
        
        if not account_number:
            return True, []  # Optional field
        
        account_clean = re.sub(r'[^\d]', '', account_number)
        
        if len(account_clean) < 6 or len(account_clean) > 8:
            errors.append(f"Account number should be 6-8 digits, got {len(account_clean)}")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_financials(financials: Optional[Financials]) -> Tuple[bool, List[str], List[str]]:
        """Validate financial data."""
        errors = []
        warnings = []
        
        if not financials:
            return True, [], []
        
        # Check for negative amounts
        if financials.subtotal is not None and financials.subtotal < 0:
            errors.append("Subtotal is negative")
        
        if financials.total_due is not None and financials.total_due < 0:
            errors.append("Total due is negative")
        
        if financials.vat_amount is not None and financials.vat_amount < 0:
            errors.append("VAT amount is negative")
        
        # Check VAT calculation
        if financials.subtotal is not None and financials.vat_amount is not None:
            expected_vat = financials.subtotal * (financials.vat_rate or Decimal('20')) / 100
            vat_diff = abs(financials.vat_amount - expected_vat)
            
            # Allow for rounding differences
            if vat_diff > Decimal('0.10'):
                warnings.append(f"VAT amount doesn't match expected ({expected_vat:.2f})")
        
        # Check total calculation
        if financials.subtotal is not None and financials.total_due is not None:
            vat = financials.vat_amount or Decimal('0')
            cis = financials.cis_deduction or Decimal('0')
            expected_total = financials.subtotal + vat - cis
            
            total_diff = abs(financials.total_due - expected_total)
            if total_diff > Decimal('0.10'):
                warnings.append(f"Total doesn't match expected calculation ({expected_total:.2f})")
        
        # Check for unusually large amounts
        if financials.total_due is not None and financials.total_due > Decimal('1000000'):
            warnings.append("Total amount seems unusually large")
        
        return len(errors) == 0, errors, warnings
    
    @classmethod
    def validate_invoice(cls, invoice: InvoiceData) -> Tuple[bool, List[str], List[str]]:
        """
        Validate complete invoice data.
        
        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        all_errors = []
        all_warnings = []
        
        # Validate invoice number
        valid, errors = cls.validate_invoice_number(invoice.invoice_number)
        all_errors.extend(errors)
        
        # Validate dates
        valid, errors = cls.validate_date(invoice.invoice_date, "invoice date")
        all_errors.extend(errors)
        
        if invoice.work_period:
            valid, errors = cls.validate_date(invoice.work_period.start_date, "period start")
            all_errors.extend(errors)
            valid, errors = cls.validate_date(invoice.work_period.end_date, "period end")
            all_errors.extend(errors)
            
            # Check period consistency
            if (invoice.work_period.start_date and invoice.work_period.end_date and
                invoice.work_period.start_date > invoice.work_period.end_date):
                all_errors.append("Period start date is after end date")
        
        # Validate contractor
        if invoice.contractor:
            valid, errors = cls.validate_utr(invoice.contractor.utr)
            all_errors.extend(errors)
            
            valid, errors = cls.validate_ni_number(invoice.contractor.ni_number)
            all_errors.extend(errors)
            
            valid, errors = cls.validate_email(invoice.contractor.email)
            all_errors.extend(errors)
            
            if invoice.contractor.address and invoice.contractor.address.postcode:
                valid, errors = cls.validate_postcode(invoice.contractor.address.postcode)
                all_errors.extend(errors)
            
            if invoice.contractor.bank_details:
                valid, errors = cls.validate_sort_code(invoice.contractor.bank_details.sort_code)
                all_errors.extend(errors)
                
                valid, errors = cls.validate_account_number(invoice.contractor.bank_details.account_number)
                all_errors.extend(errors)
        
        # Validate financials
        valid, errors, warnings = cls.validate_financials(invoice.financials)
        all_errors.extend(errors)
        all_warnings.extend(warnings)
        
        return len(all_errors) == 0, all_errors, all_warnings


class DataCleaner:
    """Clean and normalize extracted invoice data."""
    
    @staticmethod
    def clean_invoice_number(value: Optional[str]) -> Optional[str]:
        """Clean invoice number."""
        if not value:
            return None
        
        # Remove extra whitespace
        value = ' '.join(value.split())
        
        # Remove common prefixes
        value = re.sub(r'^(Invoice|Inv|No|Number|#)\s*[:\-]?\s*', '', value, flags=re.IGNORECASE)
        
        return value.upper() if value else None
    
    @staticmethod
    def clean_name(value: Optional[str]) -> Optional[str]:
        """Clean person/company name."""
        if not value:
            return None
        
        # Remove extra whitespace
        value = ' '.join(value.split())
        
        # Title case
        value = value.title()
        
        return value
    
    @staticmethod
    def clean_address(value: Optional[str]) -> Optional[str]:
        """Clean address string."""
        if not value:
            return None
        
        # Remove extra whitespace
        value = ' '.join(value.split())
        
        # Normalize commas
        value = re.sub(r'\s*,\s*', ', ', value)
        
        return value
    
    @staticmethod
    def clean_email(value: Optional[str]) -> Optional[str]:
        """Clean email address."""
        if not value:
            return None
        
        # Lowercase and strip
        value = value.lower().strip()
        
        # Remove mailto: prefix if present
        value = re.sub(r'^mailto:', '', value)
        
        return value
    
    @staticmethod
    def clean_phone(value: Optional[str]) -> Optional[str]:
        """Clean phone number."""
        if not value:
            return None
        
        # Remove all non-digit characters except +
        value = re.sub(r'[^\d+]', '', value)
        
        # Format UK numbers
        if value.startswith('44') and len(value) == 12:
            value = '+' + value
        
        if value.startswith('0') and len(value) == 11:
            value = '+44' + value[1:]
        
        return value
    
    @staticmethod
    def clean_postcode(value: Optional[str]) -> Optional[str]:
        """Clean and normalize postcode."""
        if not value:
            return None
        
        # Remove whitespace and uppercase
        value = value.upper().replace(' ', '')
        
        # Insert space in correct position
        if len(value) >= 5:
            # Find where to insert space (before last 3 characters)
            inward = value[-3:]
            outward = value[:-3]
            value = f"{outward} {inward}"
        
        return value
    
    @staticmethod
    def clean_utr(value: Optional[str]) -> Optional[str]:
        """Clean UTR."""
        if not value:
            return None
        
        # Remove non-digits
        return re.sub(r'\D', '', value)
    
    @staticmethod
    def clean_ni_number(value: Optional[str]) -> Optional[str]:
        """Clean National Insurance number."""
        if not value:
            return None
        
        # Remove whitespace and uppercase
        value = value.upper().replace(' ', '')
        
        return value
    
    @staticmethod
    def clean_sort_code(value: Optional[str]) -> Optional[str]:
        """Clean and format sort code."""
        if not value:
            return None
        
        # Remove non-digits
        digits = re.sub(r'\D', '', value)
        
        # Format as XX-XX-XX
        if len(digits) == 6:
            return f"{digits[:2]}-{digits[2:4]}-{digits[4:]}"
        
        return digits
    
    @staticmethod
    def clean_account_number(value: Optional[str]) -> Optional[str]:
        """Clean account number."""
        if not value:
            return None
        
        # Remove non-digits
        return re.sub(r'\D', '', value)
    
    @staticmethod
    def clean_money(value: Optional[Decimal]) -> Optional[Decimal]:
        """Clean monetary amount."""
        if value is None:
            return None
        
        # Round to 2 decimal places
        return value.quantize(Decimal('0.01'))
    
    @classmethod
    def clean_invoice(cls, invoice: InvoiceData) -> InvoiceData:
        """Clean all fields in invoice data."""
        # Clean invoice number
        invoice.invoice_number = cls.clean_invoice_number(invoice.invoice_number)
        
        # Clean contractor
        if invoice.contractor:
            invoice.contractor.name = cls.clean_name(invoice.contractor.name)
            invoice.contractor.email = cls.clean_email(invoice.contractor.email)
            invoice.contractor.phone = cls.clean_phone(invoice.contractor.phone)
            invoice.contractor.utr = cls.clean_utr(invoice.contractor.utr)
            invoice.contractor.ni_number = cls.clean_ni_number(invoice.contractor.ni_number)
            
            if invoice.contractor.address:
                invoice.contractor.address.postcode = cls.clean_postcode(invoice.contractor.address.postcode)
            
            if invoice.contractor.bank_details:
                invoice.contractor.bank_details.sort_code = cls.clean_sort_code(
                    invoice.contractor.bank_details.sort_code
                )
                invoice.contractor.bank_details.account_number = cls.clean_account_number(
                    invoice.contractor.bank_details.account_number
                )
        
        # Clean financials
        if invoice.financials:
            invoice.financials.subtotal = cls.clean_money(invoice.financials.subtotal)
            invoice.financials.vat_amount = cls.clean_money(invoice.financials.vat_amount)
            invoice.financials.cis_deduction = cls.clean_money(invoice.financials.cis_deduction)
            invoice.financials.total_due = cls.clean_money(invoice.financials.total_due)
        
        # Clean work items
        for item in invoice.work_items:
            item.amount = cls.clean_money(item.amount)
            item.unit_price = cls.clean_money(item.unit_price)
        
        return invoice


class DataEnricher:
    """Enrich invoice data with calculated fields."""
    
    @staticmethod
    def calculate_missing_financials(invoice: InvoiceData) -> InvoiceData:
        """Calculate missing financial values."""
        if not invoice.financials:
            return invoice
        
        fin = invoice.financials
        
        # Calculate subtotal from work items
        if fin.subtotal is None and invoice.work_items:
            item_total = sum(
                (item.amount or Decimal('0')) for item in invoice.work_items
            )
            if item_total > 0:
                fin.subtotal = item_total
        
        # Calculate VAT if missing
        if fin.vat_amount is None and fin.subtotal is not None:
            vat_rate = fin.vat_rate or Decimal('20')
            fin.vat_amount = (fin.subtotal * vat_rate / 100).quantize(Decimal('0.01'))
        
        # Calculate total if missing
        if fin.total_due is None and fin.subtotal is not None:
            vat = fin.vat_amount or Decimal('0')
            cis = fin.cis_deduction or Decimal('0')
            fin.total_due = fin.subtotal + vat - cis
        
        return invoice
    
    @staticmethod
    def infer_vat_code(invoice: InvoiceData) -> InvoiceData:
        """Infer VAT code from context."""
        if not invoice.financials:
            return invoice
        
        fin = invoice.financials
        
        if fin.vat_code is None:
            if fin.vat_amount is not None and fin.vat_amount > 0:
                fin.vat_code = 'S'  # Standard rate
            elif fin.vat_amount is not None and fin.vat_amount == 0:
                fin.vat_code = 'Z'  # Zero rate
            else:
                fin.vat_code = 'N'  # Not applicable
        
        return invoice
    
    @staticmethod
    def infer_cis_code(invoice: InvoiceData) -> InvoiceData:
        """Infer CIS code from context."""
        if not invoice.financials:
            return invoice
        
        fin = invoice.financials
        
        if fin.cis_code is None and fin.cis_deduction is not None and fin.cis_deduction > 0:
            # Default to Labour (L) if CIS deduction present
            fin.cis_code = 'L'
        
        return invoice
    
    @classmethod
    def enrich(cls, invoice: InvoiceData) -> InvoiceData:
        """Apply all enrichment methods."""
        invoice = cls.calculate_missing_financials(invoice)
        invoice = cls.infer_vat_code(invoice)
        invoice = cls.infer_cis_code(invoice)
        return invoice


def validate_and_clean(invoice: InvoiceData, 
                       do_clean: bool = True, 
                       do_validate: bool = True,
                       do_enrich: bool = True) -> Tuple[InvoiceData, List[str], List[str]]:
    """
    Validate, clean, and enrich invoice data.
    
    Args:
        invoice: Invoice data to process
        do_clean: Whether to clean the data
        do_validate: Whether to validate the data
        do_enrich: Whether to enrich with calculated fields
        
    Returns:
        Tuple of (processed_invoice, errors, warnings)
    """
    errors = []
    warnings = []
    
    # Clean
    if do_clean:
        invoice = DataCleaner.clean_invoice(invoice)
    
    # Validate
    if do_validate:
        valid, val_errors, val_warnings = DataValidator.validate_invoice(invoice)
        errors.extend(val_errors)
        warnings.extend(val_warnings)
    
    # Enrich
    if do_enrich:
        invoice = DataEnricher.enrich(invoice)
    
    return invoice, errors, warnings
