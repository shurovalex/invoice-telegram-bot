"""
Invoice Data Models

Pydantic models for invoice data validation and serialization.
Provides type safety and automatic validation for all invoice-related data.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, ConfigDict


class InvoiceStatus(str, Enum):
    """Invoice status enumeration."""
    DRAFT = "draft"
    PENDING = "pending"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class PaymentTerms(str, Enum):
    """Common payment terms."""
    DUE_ON_RECEIPT = "Due on Receipt"
    NET_15 = "Net 15"
    NET_30 = "Net 30"
    NET_60 = "Net 60"


class InvoiceItem(BaseModel):
    """
    Individual line item on an invoice.
    
    Attributes:
        description: Item description
        quantity: Number of units
        unit_price: Price per unit
        amount: Total amount (quantity * unit_price)
        tax_rate: Optional tax rate percentage
    """
    model_config = ConfigDict(populate_by_name=True)
    
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    description: str = Field(..., min_length=1, max_length=500)
    quantity: Decimal = Field(default=Decimal("1"), ge=Decimal("0"))
    unit_price: Decimal = Field(..., ge=Decimal("0"))
    amount: Optional[Decimal] = Field(default=None)
    tax_rate: Optional[Decimal] = Field(default=None, ge=Decimal("0"), le=Decimal("100"))
    
    @field_validator("amount", mode="before")
    @classmethod
    def calculate_amount(cls, v: Optional[Decimal], info) -> Decimal:
        """Calculate amount from quantity and unit_price if not provided."""
        if v is not None:
            return v
        data = info.data
        quantity = data.get("quantity", Decimal("1"))
        unit_price = data.get("unit_price", Decimal("0"))
        return quantity * unit_price


class CustomerInfo(BaseModel):
    """
    Customer information for invoice.
    
    Attributes:
        name: Customer name
        email: Customer email address
        phone: Customer phone number
        address: Customer billing address
        tax_id: Customer tax ID (if applicable)
    """
    model_config = ConfigDict(populate_by_name=True)
    
    name: str = Field(..., min_length=1, max_length=200)
    email: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)
    address: Optional[str] = Field(default=None, max_length=500)
    tax_id: Optional[str] = Field(default=None, max_length=50)
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        """Basic email validation."""
        if v and "@" not in v:
            raise ValueError("Invalid email address")
        return v.lower() if v else v


class CompanyInfo(BaseModel):
    """
    Company information for invoice header.
    
    Attributes:
        name: Company name
        address: Company address
        email: Company email
        phone: Company phone
        tax_id: Company tax ID
        logo_url: URL to company logo
    """
    model_config = ConfigDict(populate_by_name=True)
    
    name: str = Field(..., min_length=1, max_length=200)
    address: Optional[str] = Field(default=None, max_length=500)
    email: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)
    tax_id: Optional[str] = Field(default=None, max_length=50)
    logo_url: Optional[str] = Field(default=None)


class InvoiceData(BaseModel):
    """
    Complete invoice data model.
    
    This is the main model used throughout the application
    for invoice creation, storage, and generation.
    
    Attributes:
        invoice_number: Unique invoice identifier
        issue_date: Date invoice was issued
        due_date: Payment due date
        customer: Customer information
        items: List of invoice line items
        subtotal: Sum of all line items
        tax_total: Total tax amount
        total: Final invoice total
        currency: Currency code (ISO 4217)
        notes: Additional notes or terms
        status: Current invoice status
    """
    model_config = ConfigDict(populate_by_name=True)
    
    # Invoice identification
    id: str = Field(default_factory=lambda: str(uuid4()))
    invoice_number: Optional[str] = Field(default=None)
    
    # Dates
    issue_date: date = Field(default_factory=date.today)
    due_date: Optional[date] = Field(default=None)
    
    # Parties
    company: Optional[CompanyInfo] = Field(default=None)
    customer: CustomerInfo = Field(...)
    
    # Line items
    items: List[InvoiceItem] = Field(default_factory=list)
    
    # Totals (auto-calculated)
    subtotal: Optional[Decimal] = Field(default=None)
    tax_total: Optional[Decimal] = Field(default=None)
    discount: Optional[Decimal] = Field(default=Decimal("0"))
    total: Optional[Decimal] = Field(default=None)
    
    # Payment info
    currency: str = Field(default="USD", min_length=3, max_length=3)
    payment_terms: PaymentTerms = Field(default=PaymentTerms.NET_30)
    
    # Additional info
    notes: Optional[str] = Field(default=None, max_length=2000)
    terms: Optional[str] = Field(default=None, max_length=2000)
    
    # Status and tracking
    status: InvoiceStatus = Field(default=InvoiceStatus.DRAFT)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default=None)
    sent_at: Optional[datetime] = Field(default=None)
    paid_at: Optional[datetime] = Field(default=None)
    
    # Metadata
    user_id: Optional[int] = Field(default=None)
    chat_id: Optional[int] = Field(default=None)
    source_document: Optional[str] = Field(default=None)
    
    @field_validator("subtotal", mode="before")
    @classmethod
    def calculate_subtotal(cls, v: Optional[Decimal], info) -> Decimal:
        """Calculate subtotal from items."""
        if v is not None:
            return v
        data = info.data
        items = data.get("items", [])
        return sum(item.amount or Decimal("0") for item in items)
    
    @field_validator("tax_total", mode="before")
    @classmethod
    def calculate_tax(cls, v: Optional[Decimal], info) -> Decimal:
        """Calculate total tax from items."""
        if v is not None:
            return v
        data = info.data
        items = data.get("items", [])
        tax = Decimal("0")
        for item in items:
            if item.tax_rate and item.amount:
                tax += item.amount * (item.tax_rate / Decimal("100"))
        return tax
    
    @field_validator("total", mode="before")
    @classmethod
    def calculate_total(cls, v: Optional[Decimal], info) -> Decimal:
        """Calculate final total including tax and discount."""
        if v is not None:
            return v
        data = info.data
        subtotal = data.get("subtotal") or Decimal("0")
        tax_total = data.get("tax_total") or Decimal("0")
        discount = data.get("discount") or Decimal("0")
        return subtotal + tax_total - discount
    
    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, v: str) -> str:
        """Normalize currency to uppercase."""
        return v.upper()
    
    def add_item(self, item: InvoiceItem) -> "InvoiceData":
        """Add a line item and recalculate totals."""
        self.items.append(item)
        self._recalculate_totals()
        return self
    
    def remove_item(self, item_id: str) -> bool:
        """Remove a line item by ID."""
        for i, item in enumerate(self.items):
            if item.id == item_id:
                self.items.pop(i)
                self._recalculate_totals()
                return True
        return False
    
    def _recalculate_totals(self) -> None:
        """Recalculate all totals after item changes."""
        self.subtotal = sum(item.amount or Decimal("0") for item in self.items)
        self.tax_total = Decimal("0")
        for item in self.items:
            if item.tax_rate and item.amount:
                self.tax_total += item.amount * (item.tax_rate / Decimal("100"))
        self.total = self.subtotal + self.tax_total - (self.discount or Decimal("0"))
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump(mode="json")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InvoiceData":
        """Create from dictionary."""
        return cls.model_validate(data)


class ExtractedData(BaseModel):
    """
    Data extracted from a document by AI.
    
    Used as an intermediate representation before
    creating a full InvoiceData object.
    """
    model_config = ConfigDict(populate_by_name=True)
    
    raw_text: Optional[str] = Field(default=None)
    confidence_score: Optional[float] = Field(default=None, ge=0, le=1)
    extracted_fields: Dict[str, Any] = Field(default_factory=dict)
    missing_fields: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    
    def to_invoice_data(self) -> InvoiceData:
        """Convert extracted data to InvoiceData."""
        fields = self.extracted_fields
        
        # Build customer info
        customer = CustomerInfo(
            name=fields.get("customer_name", "Unknown Customer"),
            email=fields.get("customer_email"),
            phone=fields.get("customer_phone"),
            address=fields.get("customer_address"),
            tax_id=fields.get("customer_tax_id"),
        )
        
        # Build items
        items = []
        item_data = fields.get("items", [])
        if isinstance(item_data, list):
            for item in item_data:
                if isinstance(item, dict):
                    items.append(InvoiceItem(
                        description=item.get("description", "Item"),
                        quantity=Decimal(str(item.get("quantity", 1))),
                        unit_price=Decimal(str(item.get("unit_price", 0))),
                        tax_rate=Decimal(str(item.get("tax_rate", 0))) if item.get("tax_rate") else None,
                    ))
        
        return InvoiceData(
            invoice_number=fields.get("invoice_number"),
            issue_date=fields.get("issue_date") or date.today(),
            due_date=fields.get("due_date"),
            customer=customer,
            items=items,
            currency=fields.get("currency", "USD"),
            notes=fields.get("notes"),
            terms=fields.get("terms"),
        )


class DocumentMetadata(BaseModel):
    """Metadata for uploaded documents."""
    model_config = ConfigDict(populate_by_name=True)
    
    file_id: str = Field(...)
    file_name: str = Field(...)
    file_type: str = Field(...)
    file_size: int = Field(..., ge=0)
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    user_id: int = Field(...)
    chat_id: int = Field(...)
    local_path: Optional[str] = Field(default=None)
    processed: bool = Field(default=False)
    processing_error: Optional[str] = Field(default=None)
