"""
Invoice Processing Pipeline - Data Models
Defines the schema for extracted invoice data using Pydantic for validation.
"""

from typing import List, Optional, Dict, Any, Union
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, validator, field_validator
import re


class Address(BaseModel):
    """Address model for contractor or property locations."""
    street: Optional[str] = None
    city: Optional[str] = None
    postcode: Optional[str] = None
    country: Optional[str] = "UK"
    
    @field_validator('postcode')
    @classmethod
    def validate_postcode(cls, v):
        if v:
            # Basic UK postcode validation
            pattern = r'^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$'
            v = v.upper().strip()
            if re.match(pattern, v):
                return v
        return v


class BankDetails(BaseModel):
    """Bank account details for contractor."""
    account_name: Optional[str] = None
    account_number: Optional[str] = None
    sort_code: Optional[str] = None
    iban: Optional[str] = None
    swift: Optional[str] = None
    
    @field_validator('sort_code')
    @classmethod
    def validate_sort_code(cls, v):
        if v:
            # Normalize sort code format
            v = re.sub(r'[^\d]', '', v)
            if len(v) == 6:
                return f"{v[:2]}-{v[2:4]}-{v[4:]}"
        return v
    
    @field_validator('account_number')
    @classmethod
    def validate_account_number(cls, v):
        if v:
            v = re.sub(r'[^\d]', '', v)
            if len(v) <= 8:
                return v
        return v


class Contractor(BaseModel):
    """Contractor information extracted from invoice."""
    name: Optional[str] = None
    address: Optional[Address] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    utr: Optional[str] = None  # Unique Taxpayer Reference
    ni_number: Optional[str] = None  # National Insurance Number
    vat_number: Optional[str] = None
    company_number: Optional[str] = None
    bank_details: Optional[BankDetails] = None
    
    @field_validator('utr')
    @classmethod
    def validate_utr(cls, v):
        if v:
            v = re.sub(r'[^\d]', '', v)
            if len(v) == 10:
                return v
        return v
    
    @field_validator('ni_number')
    @classmethod
    def validate_ni(cls, v):
        if v:
            v = v.upper().replace(' ', '')
            pattern = r'^[A-Z]{2}\d{6}[A-Z]$'
            if re.match(pattern, v):
                return v
        return v
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if v:
            v = v.lower().strip()
            pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if re.match(pattern, v):
                return v
        return v


class WorkItem(BaseModel):
    """Individual work item on the invoice."""
    property_address: Optional[str] = None
    plot_number: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    operative_names: List[str] = Field(default_factory=list)
    
    @field_validator('amount', 'unit_price', 'quantity', mode='before')
    @classmethod
    def parse_decimal(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            # Remove currency symbols and commas
            v = re.sub(r'[£$,]', '', v).strip()
            try:
                return Decimal(v)
            except:
                return None
        return v


class WorkPeriod(BaseModel):
    """Work period covered by the invoice."""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    
    @field_validator('start_date', 'end_date', mode='before')
    @classmethod
    def parse_date(cls, v):
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            # Try multiple date formats
            formats = [
                '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y',
                '%Y/%m/%d', '%Y-%m-%d', '%Y.%m.%d',
                '%d/%m/%y', '%d-%m-%y', '%d.%m.%y',
                '%B %d, %Y', '%b %d, %Y',
                '%d %B %Y', '%d %b %Y',
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(v.strip(), fmt).date()
                except ValueError:
                    continue
        return v


class Financials(BaseModel):
    """Financial summary of the invoice."""
    subtotal: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    vat_code: Optional[str] = None  # e.g., 'S' for standard, 'Z' for zero
    vat_rate: Optional[Decimal] = Field(default=Decimal('20.00'))
    cis_deduction: Optional[Decimal] = None
    cis_code: Optional[str] = None  # e.g., 'L' for labour, 'M' for materials
    total_due: Optional[Decimal] = None
    currency: str = Field(default='GBP')
    
    @field_validator('subtotal', 'vat_amount', 'cis_deduction', 'total_due', 'vat_rate', mode='before')
    @classmethod
    def parse_decimal(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            v = re.sub(r'[£$,]', '', v).strip()
            try:
                return Decimal(v)
            except:
                return None
        return v
    
    @field_validator('vat_code')
    @classmethod
    def normalize_vat_code(cls, v):
        if v:
            v = v.upper().strip()
            valid_codes = {'S': 'Standard', 'Z': 'Zero', 'E': 'Exempt', 'N': 'None'}
            return v if v in valid_codes else v
        return v
    
    @field_validator('cis_code')
    @classmethod
    def normalize_cis_code(cls, v):
        if v:
            v = v.upper().strip()
            valid_codes = {'L': 'Labour', 'M': 'Materials'}
            return v if v in valid_codes else v
        return v


class InvoiceData(BaseModel):
    """Complete invoice data structure."""
    # Source information
    source_file: Optional[str] = None
    extraction_method: Optional[str] = None
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # Invoice identification
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    
    # Parties
    contractor: Optional[Contractor] = None
    client_name: Optional[str] = None
    client_address: Optional[Address] = None
    
    # Work details
    work_period: Optional[WorkPeriod] = None
    work_items: List[WorkItem] = Field(default_factory=list)
    
    # Financials
    financials: Optional[Financials] = None
    
    # Additional metadata
    raw_text: Optional[str] = None
    processing_errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    
    @field_validator('invoice_date', mode='before')
    @classmethod
    def parse_date(cls, v):
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            formats = [
                '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y',
                '%Y/%m/%d', '%Y-%m-%d', '%Y.%m.%d',
                '%d/%m/%y', '%d-%m-%y', '%d.%m.%y',
                '%B %d, %Y', '%b %d, %Y',
                '%d %B %Y', '%d %b %Y',
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(v.strip(), fmt).date()
                except ValueError:
                    continue
        return v
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with proper serialization."""
        return self.model_dump()
    
    def is_valid(self) -> bool:
        """Check if invoice has minimum required fields."""
        has_invoice_number = self.invoice_number is not None
        has_contractor = self.contractor is not None and self.contractor.name is not None
        has_financials = self.financials is not None and (
            self.financials.subtotal is not None or 
            self.financials.total_due is not None
        )
        return has_invoice_number or (has_contractor and has_financials)
    
    def completeness_score(self) -> float:
        """Calculate completeness score (0-1) based on filled fields."""
        score = 0.0
        total_fields = 0
        
        # Invoice basics
        if self.invoice_number: score += 1
        if self.invoice_date: score += 1
        total_fields += 2
        
        # Contractor
        if self.contractor:
            if self.contractor.name: score += 1
            if self.contractor.address and self.contractor.address.street: score += 0.5
            if self.contractor.utr: score += 0.5
            total_fields += 2
        
        # Work items
        if self.work_items:
            score += min(len(self.work_items) * 0.5, 2)
            total_fields += 2
        
        # Financials
        if self.financials:
            if self.financials.subtotal: score += 1
            if self.financials.vat_amount is not None: score += 0.5
            if self.financials.total_due: score += 1
            total_fields += 2.5
        
        return score / total_fields if total_fields > 0 else 0.0


class ExtractionResult(BaseModel):
    """Result from a single extraction attempt."""
    success: bool
    method: str
    data: Optional[InvoiceData] = None
    confidence: float = 0.0
    error_message: Optional[str] = None
    processing_time_ms: Optional[int] = None
    raw_text: Optional[str] = None


class PipelineResult(BaseModel):
    """Final result from the complete pipeline."""
    success: bool
    source_file: str
    file_type: str
    invoice_data: Optional[InvoiceData] = None
    all_attempts: List[ExtractionResult] = Field(default_factory=list)
    best_method: Optional[str] = None
    total_processing_time_ms: Optional[int] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
